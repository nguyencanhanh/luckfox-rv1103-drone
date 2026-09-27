/*
 * PID with the pieces plan section 10 asks for: integrator clamp,
 * anti-windup (the integrator freezes while the output - or the mixer
 * downstream - is saturated), output saturation, and a low-passed
 * derivative taken on the measurement so setpoint steps do not kick.
 */
#ifndef PID_H
#define PID_H

#include "../sensors/filters.h"

typedef struct {
    float kp, ki, kd;
    float i_limit;        /* |integral contribution| <= i_limit */
    float out_limit;      /* |output| <= out_limit */
    float d_cutoff_hz;    /* derivative low-pass, 0 = off */
} pid_params;

typedef struct {
    pid_params p;
    float integ;          /* integral contribution (already times ki) */
    float prev_meas;
    int have_prev;
    pt1_filter dlpf;
    float p_term, i_term, d_term, out;
} pid_ctrl;

void pid_init(pid_ctrl *c, const pid_params *p, float dt);
void pid_reset(pid_ctrl *c);
/* freeze_i: external saturation (e.g. the mixer ran out of headroom) */
float pid_update(pid_ctrl *c, float setpoint, float meas, float dt, int freeze_i);

#endif
