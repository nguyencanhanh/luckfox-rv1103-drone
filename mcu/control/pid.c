#include "pid.h"
#include "../common/fc_math.h"

void pid_init(pid_ctrl *c, const pid_params *p, float dt)
{
    c->p = *p;
    pt1_init(&c->dlpf, p->d_cutoff_hz, dt);
    pid_reset(c);
}

void pid_reset(pid_ctrl *c)
{
    c->integ = 0.0f;
    c->have_prev = 0;
    c->prev_meas = 0.0f;
    pt1_reset(&c->dlpf, 0.0f);
    c->p_term = c->i_term = c->d_term = c->out = 0.0f;
}

float pid_update(pid_ctrl *c, float setpoint, float meas, float dt, int freeze_i)
{
    float err = setpoint - meas;
    c->p_term = c->p.kp * err;

    float d = 0.0f;
    if (c->have_prev && dt > 0.0f)
        d = -(meas - c->prev_meas) / dt;          /* derivative on measurement */
    c->prev_meas = meas;
    c->have_prev = 1;
    c->d_term = c->p.kd * pt1_apply(&c->dlpf, d);

    float unsat = c->p_term + c->integ + c->d_term;
    int saturated = fabsf(unsat) >= c->p.out_limit;
    /* integrate unless something downstream is saturated in the direction
     * the error would push further (conditional integration) */
    float di = c->p.ki * err * dt;
    int pushes_out = (unsat > 0.0f && di > 0.0f) || (unsat < 0.0f && di < 0.0f);
    if (!((saturated || freeze_i) && pushes_out))
        c->integ = constrainf(c->integ + di, -c->p.i_limit, c->p.i_limit);
    c->i_term = c->integ;

    c->out = constrainf(c->p_term + c->integ + c->d_term, -c->p.out_limit, c->p.out_limit);
    return c->out;
}
