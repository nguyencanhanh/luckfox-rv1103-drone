/*
 * Attitude estimator, stage 1/2 of plan section 9: Mahony's explicit
 * complementary filter (quaternion, gyro + accelerometer, PI correction with
 * on-line gyro bias).  Reference: Mahony, Hamel, Pflimlin, "Nonlinear
 * Complementary Filters on the Special Orthogonal Group", IEEE TAC 2008; see
 * also https://ahrs.readthedocs.io/en/latest/filters/mahony.html
 *
 * No magnetometer: yaw is gyro-integrated and drifts.  Flight modes only use
 * yaw rate, so that is acceptable until a compass or GPS heading exists.
 */
#ifndef ATTITUDE_H
#define ATTITUDE_H

#include "../common/fc_math.h"

typedef struct {
    float kp;            /* rad/s per unit of gravity-direction error */
    float ki;            /* rad/s^2 per unit error (gyro bias learning) */
    float acc_gate;      /* trust the accelerometer only if | |a|/g - 1 | < gate */
} attitude_params;

typedef struct {
    attitude_params p;
    quat q;              /* body -> world */
    vec3 bias_i;         /* integral correction (residual gyro bias), rad/s */
    vec3 rate;           /* bias-corrected body rate, rad/s */
    vec3 euler;          /* roll, pitch, yaw, rad */
    int initialised;
} attitude_est;

void attitude_init(attitude_est *e, const attitude_params *p);
/* level the estimate from one accelerometer sample (yaw = 0) */
void attitude_reset_from_acc(attitude_est *e, vec3 acc);
void attitude_update(attitude_est *e, vec3 gyro, vec3 acc, float dt);

#endif
