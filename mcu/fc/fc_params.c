/*
 * Default parameters.  Every value is either traced to a source or marked
 * ASSUMED: the airframe (frame, motors, props) is not chosen yet, so the
 * gains below are first-cut values tuned in the simulator against the
 * ASSUMED airframe in simulator/quad_model.c.  They are a starting point for
 * a real craft, not a tune.
 */
#include "fc.h"

static const pid_params RATE_RP = {
    .kp = 0.040f, .ki = 0.30f, .kd = 0.0008f,
    .i_limit = 0.30f, .out_limit = 0.60f, .d_cutoff_hz = 60.0f,
};

static const pid_params RATE_YAW = {
    .kp = 0.12f, .ki = 0.30f, .kd = 0.0f,
    .i_limit = 0.30f, .out_limit = 0.40f, .d_cutoff_hz = 0.0f,
};

static const pid_params CLIMB = {
    .kp = 0.10f, .ki = 0.10f, .kd = 0.0f,
    .i_limit = 0.30f, .out_limit = 0.40f, .d_cutoff_hz = 0.0f,
};

void fc_default_params(fc_params *p)
{
    p->loop_hz = 1000.0f;            /* plan section 7; MCU loop verified in M1 */
    p->gyro_lpf_hz = 100.0f;         /* ASSUMED: tune against real vibration */
    p->acc_lpf_hz = 20.0f;           /* ASSUMED */
    p->calib_samples = 1000;         /* 1 s at 1 kHz */
    /* still-gyro noise is 0.028 dps rms at 100 Hz BW (DS-000347 v1.7 p.11);
     * 2 dps is far above it and far below a hand-held wobble */
    p->calib_max_dev = 2.0f * FC_DEG2RAD;
    /* ASSUMED "props in": diagonal pairs M1/M4 CW, M2/M3 CCW.  Must match
     * the props actually fitted - check before the first spin-up. */
    p->spin_cw[0] = 1;
    p->spin_cw[1] = 0;
    p->spin_cw[2] = 0;
    p->spin_cw[3] = 1;

    /* Mahony 2008 uses kP = 1 on a still platform.  In flight the
     * accelerometer also sees acceleration and rotor drag, so it is trusted
     * much less (tuned in the simulator, angle_step / wind scenarios) */
    p->att.kp = 0.25f;
    p->att.ki = 0.02f;
    p->att.acc_gate = 0.15f;
    p->acc_offset = v3(0.0f, 0.0f, 0.0f);   /* set by fc_request_acc_calibration */
    p->acc_cal_samples = 500;

    p->alt.crossover = 1.0f;         /* rad/s; BMP390 2 Pa rms ~ 0.17 m */
    p->alt.baro_timeout_s = 0.5f;

    control_params *c = &p->ctl;
    c->rate[0] = RATE_RP;
    c->rate[1] = RATE_RP;
    c->rate[2] = RATE_YAW;
    c->angle_kp = 6.0f;
    c->max_angle = 30.0f * FC_DEG2RAD;
    c->max_angle_rate = 300.0f * FC_DEG2RAD;
    c->acro_rate = 400.0f * FC_DEG2RAD;
    c->yaw_rate = 200.0f * FC_DEG2RAD;
    c->stick_expo = 0.2f;
    c->stick_deadband = 0.02f;
    c->climb = CLIMB;
    c->alt_kp = 1.0f;
    c->alt_lock_vz = 0.3f;           /* m/s */
    c->max_climb = 2.0f;
    c->max_descent = 1.0f;
    c->hover_throttle = 0.50f;       /* ASSUMED airframe, see quad_model.c */
    c->thr_min = 0.05f;              /* armed idle */
    c->thr_max = 1.0f;
    c->tilt_comp_max = 1.5f;
    c->fs_descent_rate = 0.7f;
    c->fs_throttle = 0.45f;          /* ASSUMED: a slow sink, no height estimate */
    c->land_vz = 0.2f;
    c->land_s = 1.0f;
    c->angle_div = 4;                /* 250 Hz */
    c->alt_div = 10;                 /* 100 Hz */
    c->iterm_relax_rate = 3.0f;      /* rad/s^2, tuned in acro_flip */
    c->iterm_relax_hz = 15.0f;

    arming_params *a = &p->arm;
    a->rc_timeout_s = 0.25f;
    a->imu_timeout_s = 0.02f;        /* 20 missed samples at 1 kHz */
    a->arm_max_tilt = 25.0f * FC_DEG2RAD;
    a->arm_max_throttle = 0.05f;
    a->fs_hold_s = 1.0f;             /* TBS crsf.md: wait ~1 s before failsafe */
    a->fs_land_s = 20.0f;
    a->crash_tilt = 80.0f * FC_DEG2RAD;
    a->crash_s = 0.3f;
}
