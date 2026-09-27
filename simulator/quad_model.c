#include "quad_model.h"
#include <string.h>

/* motor positions, same order as mcu/mixer: M1 RR, M2 FR, M3 RL, M4 FL */
static const float POS_X[QUAD_MOTORS] = {-1.0f, 1.0f, -1.0f, 1.0f};
static const float POS_Y[QUAD_MOTORS] = { 1.0f, 1.0f, -1.0f, -1.0f};

void quad_default_params(quad_params *p)
{
    /* ASSUMED airframe, see the header */
    p->mass = 0.60f;
    p->arm = 0.1125f;
    p->inertia = v3(0.0025f, 0.0025f, 0.0045f);
    p->t_max = 6.0f;
    p->motor_tau = 0.030f;
    p->k_q = 0.016f;
    p->drag_lin = 0.30f;         /* ASSUMED, ~2 s velocity time constant */
    p->drag_quad = 0.01f;        /* ASSUMED */
    p->drag_rot = 0.0005f;
    p->spin_cw[0] = 1;
    p->spin_cw[1] = 0;
    p->spin_cw[2] = 0;
    p->spin_cw[3] = 1;
    p->crash_speed = 4.0f;
}

float quad_hover_command(const quad_params *p)
{
    return sqrtf(p->mass * FC_GRAVITY / (4.0f * p->t_max));
}

void quad_init(quad_model *m, const quad_params *p)
{
    memset(m, 0, sizeof(*m));
    m->p = *p;
    m->q = q_identity();
    m->on_ground = 1;
    m->acc_body = v3(0.0f, 0.0f, -FC_GRAVITY);
}

void quad_step(quad_model *m, const float u[QUAD_MOTORS], vec3 wind, float dt)
{
    const quad_params *p = &m->p;
    float l = p->arm * 0.70710678f;          /* arm projected on x and y */
    float t_sum = 0.0f;
    vec3 tau = v3(0.0f, 0.0f, 0.0f);

    for (int i = 0; i < QUAD_MOTORS; i++) {
        float cmd = m->crashed ? 0.0f : constrainf(u[i], 0.0f, 1.0f);
        m->motor_w[i] += (cmd - m->motor_w[i]) * (dt / p->motor_tau);
        float t = p->t_max * m->motor_w[i] * m->motor_w[i];
        m->thrust[i] = t;
        t_sum += t;
        /* force (0, 0, -t) at (x, y, 0): r x F = (-y t, x t, 0) */
        tau.x += -POS_Y[i] * l * t;
        tau.y += POS_X[i] * l * t;
        /* CW prop (spin along +z) drags the body the other way: -z */
        tau.z += (p->spin_cw[i] ? -1.0f : 1.0f) * p->k_q * t;
    }

    /* rotation */
    vec3 I = p->inertia;
    vec3 Iw = v3(I.x * m->w.x, I.y * m->w.y, I.z * m->w.z);
    vec3 net = v3_sub(v3_sub(tau, v3_cross(m->w, Iw)), v3_scale(m->w, p->drag_rot));
    vec3 wdot = v3(net.x / I.x, net.y / I.y, net.z / I.z);

    /* translation, NED */
    vec3 thrust_w = q_rotate(m->q, v3(0.0f, 0.0f, -t_sum));
    vec3 air = v3_sub(m->vel, m->on_ground ? m->vel : wind);
    vec3 f = v3_add(thrust_w, v3_scale(air, -(p->drag_lin + p->drag_quad * v3_norm(air))));
    vec3 acc = v3_add(v3_scale(f, 1.0f / p->mass), v3(0.0f, 0.0f, FC_GRAVITY));

    /* ground contact: the plane pushes back when resting on it */
    if (m->on_ground && acc.z > 0.0f) {
        acc = v3(0.0f, 0.0f, 0.0f);
        m->vel = v3(0.0f, 0.0f, 0.0f);
        wdot = v3(0.0f, 0.0f, 0.0f);
        m->w = v3(0.0f, 0.0f, 0.0f);
    }

    /* semi-implicit Euler */
    m->vel = v3_add(m->vel, v3_scale(acc, dt));
    m->pos = v3_add(m->pos, v3_scale(m->vel, dt));
    m->w = v3_add(m->w, v3_scale(wdot, dt));
    m->q = q_integrate(m->q, m->w, dt);

    if (m->pos.z >= 0.0f) {
        if (!m->on_ground) {
            float cos_tilt = q_cos_tilt(m->q);
            if (m->vel.z > p->crash_speed || cos_tilt < 0.5f)
                m->crashed = 1;
            /* land flat, keep heading */
            vec3 e = q_to_euler(m->q);
            m->q = q_from_euler(0.0f, 0.0f, e.z);
        }
        m->pos.z = 0.0f;
        if (m->vel.z > 0.0f)
            m->vel = v3(0.0f, 0.0f, 0.0f);
        m->on_ground = 1;
        m->w = v3(0.0f, 0.0f, 0.0f);
    } else {
        m->on_ground = 0;
    }

    /* what an IMU at the centre of mass reads: specific force in body axes */
    vec3 kin = m->on_ground ? v3(0.0f, 0.0f, 0.0f) : acc;
    m->acc_body = q_rotate_inv(m->q, v3_sub(kin, v3(0.0f, 0.0f, FC_GRAVITY)));
    m->time += dt;
}
