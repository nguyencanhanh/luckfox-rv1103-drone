#include "altitude.h"

void altitude_init(altitude_est *e, const altitude_params *p)
{
    e->p = *p;
    float w = p->crossover;
    e->k1 = 3.0f * w;
    e->k2 = 3.0f * w * w;
    e->k3 = w * w * w;
    e->h = e->v = e->acc_bias = 0.0f;
    e->p0 = 101325.0f;
    e->since_baro = 1e6f;
    e->have_ref = 0;
    e->valid = 0;
}

float altitude_from_pressure(float pa, float p0)
{
    /* ICAO standard atmosphere, troposphere */
    return 44330.0f * (1.0f - powf(pa / p0, 0.190295f));
}

void altitude_rezero(altitude_est *e, float pressure_pa)
{
    e->p0 = pressure_pa;
    e->h = 0.0f;
    e->have_ref = 1;
}

void altitude_predict(altitude_est *e, quat q, vec3 acc_body, float dt)
{
    /* world specific force + gravity = kinematic acceleration (NED) */
    vec3 f = q_rotate(q, acc_body);
    float a_up = -(f.z + FC_GRAVITY);
    e->h += e->v * dt;
    e->v += (a_up - e->acc_bias) * dt;
    e->since_baro += dt;
    if (e->since_baro > e->p.baro_timeout_s)
        e->valid = 0;
}

void altitude_baro(altitude_est *e, float pressure_pa)
{
    if (!e->have_ref) {
        altitude_rezero(e, pressure_pa);
        e->v = 0.0f;
    }
    float dt = e->since_baro < 1.0f ? e->since_baro : 1.0f;
    float err = altitude_from_pressure(pressure_pa, e->p0) - e->h;
    e->h += e->k1 * err * dt;
    e->v += e->k2 * err * dt;
    e->acc_bias -= e->k3 * err * dt;
    e->since_baro = 0.0f;
    e->valid = 1;
}
