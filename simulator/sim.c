#include "sim.h"
#include <string.h>

void sim_init(sim_t *s, uint32_t seed, int datasheet_only)
{
    memset(s, 0, sizeof(*s));
    quad_params qp;
    quad_default_params(&qp);
    quad_init(&s->quad, &qp);

    sim_sensor_params sp;
    sim_sensor_default_params(&sp, datasheet_only);
    sim_sensors_init(&s->sens, &sp, &s->quad, seed);
    s->src = sim_sensors_source(&s->sens);

    fc_default_params(&s->fcp);
    fc_init(&s->fc, &s->fcp);
    crsf_parser_init(&s->crsf);
    rc_map_default(&s->map);

    s->packet_hz = 250.0f;          /* an ELRS packet rate; ASSUMED setting */
    s->link_latency = 0.005f;       /* ASSUMED: 2.6 ms air+UART, 2 ms Linux/IPC */
    s->mode_pos = 0;                /* ANGLE with the default map */
    s->stick_throttle = 0.0f;
}

void sim_set_pilot(sim_t *s, float roll, float pitch, float yaw, float throttle,
                   int arm_switch, int mode_pos)
{
    s->stick_roll = constrainf(roll, -1.0f, 1.0f);
    s->stick_pitch = constrainf(pitch, -1.0f, 1.0f);
    s->stick_yaw = constrainf(yaw, -1.0f, 1.0f);
    s->stick_throttle = constrainf(throttle, 0.0f, 1.0f);
    s->arm_switch = arm_switch ? 1 : 0;
    s->mode_pos = mode_pos < 0 ? 0 : (mode_pos > 2 ? 2 : mode_pos);
}

void sim_set_faults(sim_t *s, int link_cut, int imu_fail)
{
    s->link_cut = link_cut;
    s->sens.imu_failed = imu_fail;
}

void sim_set_wind(sim_t *s, float north_ms, float east_ms, float gust_ms)
{
    s->wind = v3(north_ms, east_ms, 0.0f);
    s->gust = gust_ms;
}

static uint16_t us_ticks(float us) { return crsf_us_to_ticks((int)(us + 0.5f)); }

static void transmitter(sim_t *s, float dt)
{
    s->packet_timer += dt;
    if (s->packet_timer < 1.0f / s->packet_hz)
        return;
    s->packet_timer -= 1.0f / s->packet_hz;
    if (s->link_cut || s->q_len >= SIM_LINK_QUEUE)
        return;                     /* receiver in "cut" failsafe: no frames */
    uint16_t ch[CRSF_CHANNELS];
    for (int i = 0; i < CRSF_CHANNELS; i++)
        ch[i] = CRSF_TICK_MID;
    ch[s->map.ch_roll] = us_ticks(1500.0f + 500.0f * s->stick_roll);
    ch[s->map.ch_pitch] = us_ticks(1500.0f + 500.0f * s->stick_pitch);
    ch[s->map.ch_yaw] = us_ticks(1500.0f + 500.0f * s->stick_yaw);
    ch[s->map.ch_throttle] = us_ticks(1000.0f + 1000.0f * s->stick_throttle);
    ch[s->map.ch_arm] = us_ticks(s->arm_switch ? 2000.0f : 1000.0f);
    static const float MODE_US[3] = {1000.0f, 1500.0f, 2000.0f};
    ch[s->map.ch_mode] = us_ticks(MODE_US[s->mode_pos]);
    sim_frame *f = &s->q[s->q_len++];
    crsf_pack_channels(ch, f->bytes);
    f->deliver_at = s->t + s->link_latency;
    s->frames_sent++;
}

/* returns 1 if a complete, CRC-good channel frame came out this tick */
static int receiver_side(sim_t *s, fc_rc_input *rc)
{
    int got = 0;
    while (s->q_len > 0 && s->q[0].deliver_at <= s->t) {
        for (int i = 0; i < CRSF_RC_FRAME_LEN; i++)
            if (crsf_feed(&s->crsf, s->q[0].bytes[i]) == CRSF_GOT_CHANNELS)
                got = 1;
        memmove(&s->q[0], &s->q[1], sizeof(sim_frame) * (size_t)(s->q_len - 1));
        s->q_len--;
        s->frames_delivered++;
    }
    if (!got)
        return 0;
    rc_command cmd;
    rc_map_apply(&s->map, s->crsf.channels, &cmd);
    rc->valid = 1;
    rc->sticks.roll = cmd.roll;
    rc->sticks.pitch = cmd.pitch;
    rc->sticks.yaw = cmd.yaw;
    rc->sticks.throttle = cmd.throttle;
    rc->sticks.mode = (flight_mode)cmd.mode;
    rc->arm_switch = cmd.arm_switch;
    return 1;
}

void sim_step(sim_t *s, int ticks)
{
    float dt = s->fc.dt;
    for (int k = 0; k < ticks; k++) {
        fc_rc_input rc;
        memset(&rc, 0, sizeof(rc));
        int fresh;
        if (s->ipc_mode) {
            fresh = fc_link_poll(&s->link, &rc);
        } else {
            transmitter(s, dt);
            fresh = receiver_side(s, &rc);
        }

        sim_sensors_sample(&s->sens, s->t_us, dt);
        fc_tick(&s->fc, &s->src, fresh ? &rc : NULL, s->motor);
        if (s->ipc_mode)
            fc_link_tick(&s->link, &s->fc, (uint32_t)(s->t * 1000.0f), 0);

        /* gusts: first-order coloured noise, ~1 s correlation */
        if (s->gust > 0.0f) {
            float a = dt / 1.0f, n = s->gust * sqrtf(2.0f * a);
            s->gust_now = v3(s->gust_now.x * (1.0f - a) + n * sim_randn(&s->sens.rng),
                             s->gust_now.y * (1.0f - a) + n * sim_randn(&s->sens.rng),
                             s->gust_now.z * (1.0f - a) + 0.3f * n * sim_randn(&s->sens.rng));
        } else {
            s->gust_now = v3(0.0f, 0.0f, 0.0f);
        }
        vec3 air = v3_add(s->wind, s->gust_now);
        /* physics at 4x the loop rate */
        for (int j = 0; j < 4; j++)
            quad_step(&s->quad, s->motor, air, dt * 0.25f);

        s->t += dt;
        s->t_us += (uint32_t)(dt * 1e6f + 0.5f);
    }
}

void sim_attach_ipc(sim_t *s, void *page)
{
    fc_link_init(&s->link, page, 1, 20);       /* telemetry at 50 Hz */
    s->ipc_mode = 1;
}

int sim_request_level_calibration(sim_t *s) { return fc_request_acc_calibration(&s->fc); }

unsigned long sim_sizeof(void) { return (unsigned long)sizeof(sim_t); }

static const char NAMES[] =
    "t,x,y,z,vx,vy,vz,qw,qx,qy,qz,roll,pitch,yaw,wx,wy,wz,"
    "est_roll,est_pitch,est_yaw,est_h,est_vz,alt_valid,"
    "m1,m2,m3,m4,state,mode,blocks,disarm_reason,crashed,on_ground,"
    "sp_roll,sp_pitch,sp_rate_r,sp_rate_p,sp_rate_y,climb_sp,height_sp,collective,"
    "mixer_sat,link_cut,imu_fail,frames_ok,crc_err,calib_done,"
    "stick_r,stick_p,stick_y,stick_t,arm_sw,mode_pos,wind_n,wind_e";

const char *sim_state_names(void) { return NAMES; }

int sim_get_state(const sim_t *s, float *o, int max)
{
    const quad_model *m = &s->quad;
    const fc_t *f = &s->fc;
    vec3 e = q_to_euler(m->q);
    float v[] = {
        s->t, m->pos.x, m->pos.y, m->pos.z, m->vel.x, m->vel.y, m->vel.z,
        m->q.w, m->q.x, m->q.y, m->q.z, e.x, e.y, e.z, m->w.x, m->w.y, m->w.z,
        f->att.euler.x, f->att.euler.y, f->att.euler.z, f->alt.h, f->alt.v, (float)f->alt.valid,
        s->motor[0], s->motor[1], s->motor[2], s->motor[3],
        (float)f->state, (float)f->rc.sticks.mode, (float)f->arm.blocks,
        (float)f->arm.last_disarm, (float)m->crashed, (float)m->on_ground,
        f->ctl.angle_sp.x, f->ctl.angle_sp.y, f->ctl.rate_sp.x, f->ctl.rate_sp.y,
        f->ctl.rate_sp.z, f->ctl.climb_sp, f->ctl.height_sp, f->ctl.collective_out,
        (float)f->mix.saturated, (float)s->link_cut, (float)s->sens.imu_failed,
        (float)s->crsf.frames_ok, (float)s->crsf.crc_errors, (float)f->calib.done,
        /* what the flight core is being told (in drone mode: by the ground station) */
        s->ipc_mode ? f->rc.sticks.roll : s->stick_roll,
        s->ipc_mode ? f->rc.sticks.pitch : s->stick_pitch,
        s->ipc_mode ? f->rc.sticks.yaw : s->stick_yaw,
        s->ipc_mode ? f->rc.sticks.throttle : s->stick_throttle,
        (float)(s->ipc_mode ? f->rc.arm_switch : s->arm_switch),
        (float)(s->ipc_mode ? (f->rc.sticks.mode == MODE_ANGLE ? 0 : f->rc.sticks.mode == MODE_ALT_HOLD ? 1 : 2)
                            : s->mode_pos),
        s->wind.x, s->wind.y,
    };
    int n = (int)(sizeof(v) / sizeof(v[0]));
    if (n > max)
        n = max;
    memcpy(o, v, sizeof(float) * (size_t)n);
    return n;
}
