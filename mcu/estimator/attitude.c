#include "attitude.h"

void attitude_init(attitude_est *e, const attitude_params *p)
{
    e->p = *p;
    e->q = q_identity();
    e->bias_i = v3(0.0f, 0.0f, 0.0f);
    e->rate = v3(0.0f, 0.0f, 0.0f);
    e->euler = v3(0.0f, 0.0f, 0.0f);
    e->initialised = 0;
}

void attitude_reset_from_acc(attitude_est *e, vec3 acc)
{
    /* still craft: acc = R^T (0, 0, -g), so "down" in body is -acc */
    float roll = atan2f(-acc.y, -acc.z);
    float pitch = atan2f(acc.x, sqrtf(acc.y * acc.y + acc.z * acc.z));
    e->q = q_from_euler(roll, pitch, 0.0f);
    e->euler = q_to_euler(e->q);
    e->bias_i = v3(0.0f, 0.0f, 0.0f);
    e->initialised = 1;
}

void attitude_update(attitude_est *e, vec3 gyro, vec3 acc, float dt)
{
    if (!e->initialised) {
        attitude_reset_from_acc(e, acc);
        return;
    }
    vec3 w = gyro;
    float an = v3_norm(acc);
    float dev = an > 1e-3f ? fabsf(an / FC_GRAVITY - 1.0f) : 1.0f;
    if (dev < e->p.acc_gate) {
        /* the further |a| is from 1 g the less it says about gravity: in
         * flight the accelerometer also sees thrust changes and drag */
        float wgt = 1.0f - dev / e->p.acc_gate;
        /* measured and predicted "down" directions in the body frame */
        vec3 down_meas = v3_scale(acc, -1.0f / an);
        vec3 down_est = q_rotate_inv(e->q, v3(0.0f, 0.0f, 1.0f));
        /* rotating by +err turns the estimate toward the measurement */
        vec3 err = v3_cross(down_est, down_meas);
        err = v3_scale(err, -1.0f);
        err = v3_scale(err, wgt);
        e->bias_i = v3_add(e->bias_i, v3_scale(err, e->p.ki * dt));
        w = v3_add(w, v3_add(v3_scale(err, e->p.kp), e->bias_i));
    } else {
        w = v3_add(w, e->bias_i);
    }
    e->rate = v3_add(gyro, e->bias_i);
    e->q = q_integrate(e->q, w, dt);
    e->euler = q_to_euler(e->q);
}
