#include "control.h"

void control_init(controller *c, const control_params *p, float dt)
{
    c->p = *p;
    for (int i = 0; i < 3; i++) {
        pid_init(&c->rate_pid[i], &p->rate[i], dt);
        pt1_init(&c->sp_slope[i], p->iterm_relax_hz, dt);
    }
    pid_init(&c->climb_pid, &p->climb, dt * (float)p->alt_div);
    control_reset(c);
}

void control_reset(controller *c)
{
    for (int i = 0; i < 3; i++)
        pid_reset(&c->rate_pid[i]);
    pid_reset(&c->climb_pid);
    c->rate_sp = v3(0.0f, 0.0f, 0.0f);
    c->angle_sp = v3(0.0f, 0.0f, 0.0f);
    c->climb_sp = c->height_sp = 0.0f;
    c->collective = 0.0f;
    c->collective_out = 0.0f;
    c->alt_engaged = 0;
    c->alt_locked = 0;
    c->fs_hold_collective = 0.0f;
    c->land_timer = 0.0f;
    c->landed = 1;
    c->tick = 0;
    c->demand = v3(0.0f, 0.0f, 0.0f);
    c->prev_rate_sp = v3(0.0f, 0.0f, 0.0f);
    for (int i = 0; i < 3; i++)
        pt1_reset(&c->sp_slope[i], 0.0f);
}

float stick_shape(float x, float expo, float deadband)
{
    x = constrainf(x, -1.0f, 1.0f);
    float a = fabsf(x);
    if (a <= deadband)
        return 0.0f;
    a = (a - deadband) / (1.0f - deadband);
    a = a * (1.0f - expo) + a * a * a * expo;
    return x < 0.0f ? -a : a;
}

static void angle_loop(controller *c, float roll, float pitch, float yaw, const control_state *st)
{
    const control_params *p = &c->p;
    /* stick forward (+) = nose down = negative pitch */
    c->angle_sp = v3(roll * p->max_angle, -pitch * p->max_angle, 0.0f);
    c->rate_sp.x = constrainf(p->angle_kp * (c->angle_sp.x - st->euler.x),
                              -p->max_angle_rate, p->max_angle_rate);
    c->rate_sp.y = constrainf(p->angle_kp * (c->angle_sp.y - st->euler.y),
                              -p->max_angle_rate, p->max_angle_rate);
    c->rate_sp.z = yaw * p->yaw_rate;
}

static float stick_collective(const control_params *p, float throttle)
{
    return p->thr_min + constrainf(throttle, 0.0f, 1.0f) * (p->thr_max - p->thr_min);
}

void control_step(controller *c, const control_sticks *s, const control_state *st, float dt)
{
    const control_params *p = &c->p;
    if (!st->armed) {
        control_reset(c);
        return;
    }
    c->tick++;

    float roll = stick_shape(s->roll, p->stick_expo, p->stick_deadband);
    float pitch = stick_shape(s->pitch, p->stick_expo, p->stick_deadband);
    float yaw = stick_shape(s->yaw, p->stick_expo, p->stick_deadband);
    flight_mode mode = s->mode;
    if (st->failsafe) {                 /* level, no yaw, pilot sticks ignored */
        roll = pitch = yaw = 0.0f;
        mode = st->alt_valid ? MODE_ALT_HOLD : MODE_ANGLE;
    }
    if (mode == MODE_ALT_HOLD && !st->alt_valid)
        mode = MODE_ANGLE;

    /* ---- attitude ---- */
    if (mode == MODE_ACRO) {
        c->rate_sp = v3(roll * p->acro_rate, -pitch * p->acro_rate, yaw * p->yaw_rate);
    } else if (c->tick % p->angle_div == 0 || c->tick == 1) {
        angle_loop(c, roll, pitch, yaw, st);
    }

    /* ---- collective ---- */
    float cos_tilt = q_cos_tilt(st->q);
    if (mode == MODE_ALT_HOLD) {
        if (!c->alt_engaged) {
            c->alt_engaged = 1;
            c->alt_locked = 0;
            c->height_sp = st->height;
            pid_reset(&c->climb_pid);
            /* take over without a jump: the integrator carries the difference
             * between the current collective and the hover guess */
            float now = c->collective > 0.0f ? c->collective : p->hover_throttle;
            c->climb_pid.integ = constrainf(now - p->hover_throttle,
                                            -p->climb.i_limit, p->climb.i_limit);
        }
        if (c->tick % p->alt_div == 0) {
            float adt = dt * (float)p->alt_div;
            float t = stick_shape((s->throttle - 0.5f) * 2.0f, 0.0f, p->stick_deadband * 2.0f);
            if (st->failsafe == 1)
                t = 0.0f;
            if (st->failsafe == 2) {
                c->climb_sp = -p->fs_descent_rate;
                c->height_sp = st->height;
                c->alt_locked = 0;
            } else if (t != 0.0f) {
                c->climb_sp = t > 0.0f ? t * p->max_climb : t * p->max_descent;
                c->height_sp = st->height;
                c->alt_locked = 0;
            } else if (!c->alt_locked) {
                /* brake first, then hold: engaging (or letting the stick go)
                 * while climbing fast must not lock a height it will overshoot
                 * and then come back down to (PX4 does the same) */
                c->climb_sp = 0.0f;
                c->height_sp = st->height;
                if (fabsf(st->climb) < p->alt_lock_vz)
                    c->alt_locked = 1;
            } else {
                c->climb_sp = constrainf(p->alt_kp * (c->height_sp - st->height),
                                         -p->max_descent, p->max_climb);
            }
            float u = p->hover_throttle + pid_update(&c->climb_pid, c->climb_sp, st->climb,
                                                     adt, st->mixer_saturated);
            c->collective = u;
        }
    } else {
        c->alt_engaged = 0;
        if (st->failsafe == 1)
            c->collective = c->fs_hold_collective;
        else if (st->failsafe == 2)
            c->collective = p->fs_throttle;
        else
            c->collective = stick_collective(p, s->throttle);
    }
    if (!st->failsafe)
        c->fs_hold_collective = c->collective;

    float out_collective = c->collective;
    if (mode != MODE_ACRO) {
        float k = cos_tilt > 1e-3f ? 1.0f / cos_tilt : p->tilt_comp_max;
        out_collective *= constrainf(k, 1.0f, p->tilt_comp_max);
    }
    out_collective = constrainf(out_collective, p->thr_min, p->thr_max);

    /* ---- land detector (only meaningful with a height estimate) ---- */
    if (st->alt_valid && fabsf(st->climb) < p->land_vz && c->collective < p->hover_throttle
        && mode == MODE_ALT_HOLD && c->climb_sp < 0.0f)
        c->land_timer += dt;
    else
        c->land_timer = 0.0f;
    c->landed = c->land_timer > p->land_s;

    /* ---- rate loop ---- */
    int ground_idle = !st->failsafe && mode != MODE_ALT_HOLD && s->throttle < 0.02f;
    float meas[3] = {st->rate.x, st->rate.y, st->rate.z};
    float sp[3] = {c->rate_sp.x, c->rate_sp.y, c->rate_sp.z};
    float prev[3] = {c->prev_rate_sp.x, c->prev_rate_sp.y, c->prev_rate_sp.z};
    float out[3];
    for (int i = 0; i < 3; i++) {
        if (ground_idle)
            c->rate_pid[i].integ = 0.0f;       /* no windup while sitting on the ground */
        /* I-term relax: while the stick moves fast the error is the craft
         * catching up, not a steady disturbance - do not integrate it */
        float slope = fabsf(pt1_apply(&c->sp_slope[i], (sp[i] - prev[i]) / dt));
        int relax = slope > p->iterm_relax_rate;
        out[i] = pid_update(&c->rate_pid[i], sp[i], meas[i], dt, st->mixer_saturated || relax);
    }
    c->prev_rate_sp = c->rate_sp;
    c->demand = v3(out[0], out[1], out[2]);
    c->collective_out = out_collective;      /* tilt-compensated: to the mixer */
}
