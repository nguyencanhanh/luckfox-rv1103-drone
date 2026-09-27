#include "fc.h"
#include <string.h>

void fc_init(fc_t *fc, const fc_params *p)
{
    memset(fc, 0, sizeof(*fc));
    fc->p = *p;
    fc->dt = 1.0f / p->loop_hz;
    gyro_calib_init(&fc->calib, p->calib_samples, p->calib_max_dev);
    for (int i = 0; i < 3; i++) {
        biquad_lpf_init(&fc->gyro_f[i], p->gyro_lpf_hz, p->loop_hz);
        pt1_init(&fc->acc_f[i], p->acc_lpf_hz, fc->dt);
    }
    attitude_init(&fc->att, &p->att);
    altitude_init(&fc->alt, &p->alt);
    control_init(&fc->ctl, &p->ctl, fc->dt);
    mixer_quadx_table(&fc->mix_tab, p->spin_cw);
    arming_init(&fc->arm, &p->arm);
    fc->state = FC_DISARMED;
}

static vec3 filt3(pt1_filter f[3], vec3 v)
{
    return v3(pt1_apply(&f[0], v.x), pt1_apply(&f[1], v.y), pt1_apply(&f[2], v.z));
}

void fc_step(fc_t *fc, const imu_sample *imu, const baro_sample *baro,
             const fc_rc_input *rc, float motor_out[MIXER_MOTORS])
{
    const float dt = fc->dt;
    fc->ticks++;

    /* ---- sensors ---- */
    if (imu) {
        fc->imu = *imu;
        if (!fc->have_imu) {
            for (int i = 0; i < 3; i++)
                pt1_reset(&fc->acc_f[i], (&imu->acc.x)[i] - (&fc->p.acc_offset.x)[i]);
        }
        fc->have_imu = 1;
        if (fc->state == FC_DISARMED)
            gyro_calib_feed(&fc->calib, imu->gyro);
        if (fc->acc_cal_active) {
            fc->acc_cal_sum = v3_add(fc->acc_cal_sum, imu->acc);
            if (++fc->acc_cal_n >= fc->p.acc_cal_samples) {
                vec3 mean = v3_scale(fc->acc_cal_sum, 1.0f / (float)fc->acc_cal_n);
                fc->p.acc_offset = v3_sub(mean, v3(0.0f, 0.0f, -FC_GRAVITY));
                fc->acc_cal_active = 0;
                attitude_reset_from_acc(&fc->att, v3_sub(mean, fc->p.acc_offset));
            }
        }
        vec3 acc = v3_sub(imu->acc, fc->p.acc_offset);
        vec3 g = v3_sub(imu->gyro, fc->calib.bias);
        fc->gyro_filt = v3(biquad_apply(&fc->gyro_f[0], g.x),
                           biquad_apply(&fc->gyro_f[1], g.y),
                           biquad_apply(&fc->gyro_f[2], g.z));
        fc->acc_filt = filt3(fc->acc_f, acc);
        attitude_update(&fc->att, g, fc->acc_filt, dt);
        altitude_predict(&fc->alt, fc->att.q, fc->acc_filt, dt);
    } else {
        fc->imu_missed++;
    }
    if (baro) {
        fc->last_pressure = baro->pressure_pa;
        fc->have_baro = 1;
        altitude_baro(&fc->alt, baro->pressure_pa);
    }
    if (rc && rc->valid) {
        fc->rc = *rc;
        fc->have_rc = 1;
    }

    /* ---- arming / failsafe ---- */
    arming_inputs ai;
    ai.rc_ok = rc && rc->valid;
    ai.imu_ok = imu != NULL;
    ai.calib_ok = fc->calib.done && !fc->acc_cal_active;
    ai.arm_switch = fc->have_rc ? fc->rc.arm_switch : 0;
    ai.throttle_stick = fc->have_rc ? fc->rc.sticks.throttle : 1.0f;
    ai.tilt = acosf(constrainf(q_cos_tilt(fc->att.q), -1.0f, 1.0f));
    ai.landed = fc->ctl.landed;
    ai.crash_check = fc->rc.sticks.mode != MODE_ACRO || fc->state == FC_FAILSAFE_HOLD
                     || fc->state == FC_FAILSAFE_LAND;
    fc_state prev = fc->state;
    fc->state = arming_update(&fc->arm, &ai, dt);
    if (prev == FC_DISARMED && fc->state != FC_DISARMED && fc->have_baro) {
        /* take-off point is height 0 */
        altitude_rezero(&fc->alt, fc->last_pressure);
        fc->alt.v = 0.0f;
    }

    /* ---- control ---- */
    control_state cs;
    cs.armed = fc->state != FC_DISARMED;
    cs.failsafe = fc->state == FC_FAILSAFE_HOLD ? 1 : (fc->state == FC_FAILSAFE_LAND ? 2 : 0);
    cs.mixer_saturated = fc->mix.saturated;
    cs.alt_valid = fc->alt.valid;
    cs.height = fc->alt.h;
    cs.climb = fc->alt.v;
    cs.q = fc->att.q;
    cs.euler = fc->att.euler;
    cs.rate = fc->gyro_filt;
    control_step(&fc->ctl, &fc->rc.sticks, &cs, dt);

    if (cs.armed) {
        mixer_mix(&fc->mix_tab, fc->ctl.collective_out, fc->ctl.demand.x,
                  fc->ctl.demand.y, fc->ctl.demand.z, &fc->mix);
        for (int i = 0; i < MIXER_MOTORS; i++)
            fc->motor[i] = constrainf(fc->mix.motor[i], fc->p.ctl.thr_min, 1.0f);
    } else {
        fc->mix.saturated = 0;
        for (int i = 0; i < MIXER_MOTORS; i++)
            fc->motor[i] = 0.0f;
    }
    for (int i = 0; i < MIXER_MOTORS; i++)
        motor_out[i] = fc->motor[i];
}

int fc_request_acc_calibration(fc_t *fc)
{
    if (fc->state != FC_DISARMED)
        return 0;
    fc->acc_cal_active = 1;
    fc->acc_cal_n = 0;
    fc->acc_cal_sum = v3(0.0f, 0.0f, 0.0f);
    return 1;
}

void fc_tick(fc_t *fc, const sensor_source *src, const fc_rc_input *rc,
             float motor_out[MIXER_MOTORS])
{
    imu_sample imu;
    baro_sample baro;
    int got_imu = src->read_imu ? src->read_imu(src->ctx, &imu) : 0;
    int got_baro = src->read_baro ? src->read_baro(src->ctx, &baro) : 0;
    fc_step(fc, got_imu > 0 ? &imu : NULL, got_baro > 0 ? &baro : NULL, rc, motor_out);
}
