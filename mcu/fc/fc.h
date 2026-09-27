/*
 * Flight core: one call per rate-loop tick (1 kHz target, plan section 7).
 *
 *   IMU -> calibration -> filtering -> attitude / height estimate
 *       -> arming + failsafe -> controller -> quad-X mixer -> 4 x 0..1
 *
 * Motor outputs are numbers only ("virtual motors", plan milestone 2).  Nothing
 * in here touches hardware; a board or the simulator supplies samples through
 * sensor_if.h and turns the four numbers into PWM / DShot, or into thrust.
 */
#ifndef FC_H
#define FC_H

#include <stdint.h>
#include "../sensors/sensor_if.h"
#include "../sensors/filters.h"
#include "../sensors/gyro_calib.h"
#include "../estimator/attitude.h"
#include "../estimator/altitude.h"
#include "../control/control.h"
#include "../mixer/mixer.h"
#include "../failsafe/arming.h"

typedef struct {
    float loop_hz;
    float gyro_lpf_hz;         /* biquad on the rate-loop gyro */
    float acc_lpf_hz;          /* PT1 on the accelerometer for the estimators */
    uint32_t calib_samples;
    float calib_max_dev;       /* rad/s */
    vec3 acc_offset;           /* m/s^2, subtracted from every sample */
    uint32_t acc_cal_samples;  /* level calibration window */
    int spin_cw[MIXER_MOTORS];
    attitude_params att;
    altitude_params alt;
    control_params ctl;
    arming_params arm;
} fc_params;

/* pilot input as the flight core wants it (see shared/rc/rc_map.h) */
typedef struct {
    int valid;                 /* a fresh, CRC-good frame arrived this tick */
    control_sticks sticks;
    int arm_switch;
} fc_rc_input;

typedef struct {
    fc_params p;
    float dt;
    gyro_calib calib;
    biquad_filter gyro_f[3];
    pt1_filter acc_f[3];
    attitude_est att;
    altitude_est alt;
    controller ctl;
    mixer_table mix_tab;
    mixer_out mix;
    arming_sm arm;

    /* latest inputs */
    imu_sample imu;
    int have_imu;
    float last_pressure;
    int have_baro;
    fc_rc_input rc;            /* last valid pilot input, held between frames */
    int have_rc;

    /* outputs and telemetry */
    fc_state state;
    vec3 gyro_filt, acc_filt;
    float motor[MIXER_MOTORS];
    uint32_t ticks, imu_missed;

    /* accelerometer level calibration (disarmed, craft on a level surface) */
    int acc_cal_active;
    uint32_t acc_cal_n;
    vec3 acc_cal_sum;
} fc_t;

void fc_default_params(fc_params *p);
void fc_init(fc_t *fc, const fc_params *p);
/*
 * imu / baro / rc may be NULL when nothing new arrived this tick.  A NULL IMU
 * counts toward the IMU timeout; a NULL rc toward the RC timeout.
 */
void fc_step(fc_t *fc, const imu_sample *imu, const baro_sample *baro,
             const fc_rc_input *rc, float motor_out[MIXER_MOTORS]);
/* the same, pulling samples from a REAL or SIM sensor_source */
void fc_tick(fc_t *fc, const sensor_source *src, const fc_rc_input *rc,
             float motor_out[MIXER_MOTORS]);
/*
 * Level calibration: with the craft still on a level surface, average the
 * accelerometer for acc_cal_samples and store its offset from (0, 0, -g).
 * Corrects the +-20 mg board-level zero-g offset (DS-000347), which would
 * otherwise read as ~1 deg of tilt.  Refused while armed; returns 1 if started.
 */
int fc_request_acc_calibration(fc_t *fc);

#endif
