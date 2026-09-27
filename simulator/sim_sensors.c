#include "sim_sensors.h"
#include <string.h>

static float randu(uint32_t *s)
{
    /* xorshift32 */
    uint32_t x = *s;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *s = x;
    return (float)(x >> 8) * (1.0f / 16777216.0f);
}

float sim_randn(uint32_t *s)
{
    /* Box-Muller */
    float u1 = randu(s), u2 = randu(s);
    if (u1 < 1e-7f)
        u1 = 1e-7f;
    return sqrtf(-2.0f * logf(u1)) * cosf(2.0f * FC_PI * u2);
}

void sim_sensor_default_params(sim_sensor_params *p, int datasheet_only)
{
    const float ug = 1e-6f * FC_GRAVITY;
    p->gyro_nd = 0.0028f * FC_DEG2RAD;
    p->acc_nd_xy = 65.0f * ug;
    p->acc_nd_z = 70.0f * ug;
    p->bandwidth_hz = 250.0f;                /* ASSUMED UI filter setting */
    p->gyro_bias_max = 0.5f * FC_DEG2RAD;
    p->acc_bias_max = 0.020f * FC_GRAVITY;
    p->vib_gyro = datasheet_only ? 0.0f : 3.0f * FC_DEG2RAD;   /* ASSUMED */
    p->vib_acc = datasheet_only ? 0.0f : 1.5f;                 /* ASSUMED */
    p->imu_delay = 1;                        /* ASSUMED: 1 ms SPI + filter */
    p->baro_hz = 50.0f;
    p->baro_noise_pa = 2.0f;
    p->baro_delay = 1;                       /* ASSUMED: one conversion */
}

void sim_sensors_init(sim_sensors *s, const sim_sensor_params *p, const quad_model *m,
                      uint32_t seed)
{
    memset(s, 0, sizeof(*s));
    s->p = *p;
    s->model = m;
    s->rng = seed ? seed : 0x1234567u;
    float gb = p->gyro_bias_max, ab = p->acc_bias_max;
    s->gyro_bias = v3((randu(&s->rng) * 2.0f - 1.0f) * gb, (randu(&s->rng) * 2.0f - 1.0f) * gb,
                      (randu(&s->rng) * 2.0f - 1.0f) * gb);
    s->acc_bias = v3((randu(&s->rng) * 2.0f - 1.0f) * ab, (randu(&s->rng) * 2.0f - 1.0f) * ab,
                     (randu(&s->rng) * 2.0f - 1.0f) * ab);
    s->ground_pressure = 101325.0f;
}

static float pressure_at(float ground_pa, float height_m)
{
    /* inverse of altitude_from_pressure(): ISA troposphere */
    return ground_pa * powf(1.0f - height_m / 44330.0f, 5.255f);
}

void sim_sensors_sample(sim_sensors *s, uint32_t t_us, float dt)
{
    const quad_model *m = s->model;
    const sim_sensor_params *p = &s->p;
    float sq = sqrtf(p->bandwidth_hz);
    float spin = 0.0f;
    for (int i = 0; i < QUAD_MOTORS; i++)
        spin += m->motor_w[i] * 0.25f;

    imu_sample x;
    x.t_us = t_us;
    float gn = p->gyro_nd * sq, vg = p->vib_gyro * spin;
    x.gyro = v3(m->w.x + s->gyro_bias.x + gn * sim_randn(&s->rng) + vg * sim_randn(&s->rng),
                m->w.y + s->gyro_bias.y + gn * sim_randn(&s->rng) + vg * sim_randn(&s->rng),
                m->w.z + s->gyro_bias.z + gn * sim_randn(&s->rng) + vg * sim_randn(&s->rng));
    float axy = p->acc_nd_xy * sq, az = p->acc_nd_z * sq, va = p->vib_acc * spin;
    x.acc = v3(m->acc_body.x + s->acc_bias.x + axy * sim_randn(&s->rng) + va * sim_randn(&s->rng),
               m->acc_body.y + s->acc_bias.y + axy * sim_randn(&s->rng) + va * sim_randn(&s->rng),
               m->acc_body.z + s->acc_bias.z + az * sim_randn(&s->rng) + va * sim_randn(&s->rng));

    /* delay line: push now, release the one imu_delay samples old */
    if (s->imu_failed) {
        s->imu_count = 0;            /* a dead IMU delivers nothing, ever */
        s->imu_ready = 0;
    } else {
        s->imu_q[(s->imu_head + s->imu_count) % SIM_DELAY_MAX] = x;
        s->imu_count++;
        s->imu_ready = s->imu_count > p->imu_delay;
    }

    s->baro_timer += dt;
    s->baro_ready = 0;
    if (s->baro_timer >= 1.0f / p->baro_hz) {
        s->baro_timer -= 1.0f / p->baro_hz;
        baro_sample b;
        b.t_us = t_us;
        b.pressure_pa = pressure_at(s->ground_pressure, -m->pos.z)
                        + p->baro_noise_pa * sim_randn(&s->rng);
        b.temp_c = 25.0f;
        s->baro_q[(s->baro_head + s->baro_count) % SIM_DELAY_MAX] = b;
        if (s->baro_count < SIM_DELAY_MAX)
            s->baro_count++;
        s->baro_ready = s->baro_count > p->baro_delay;
    }
}

static int read_imu(void *ctx, imu_sample *out)
{
    sim_sensors *s = ctx;
    if (!s->imu_ready)
        return 0;
    *out = s->imu_q[s->imu_head];
    s->imu_head = (s->imu_head + 1) % SIM_DELAY_MAX;
    s->imu_count--;
    s->imu_ready = 0;
    return 1;
}

static int read_baro(void *ctx, baro_sample *out)
{
    sim_sensors *s = ctx;
    if (!s->baro_ready)
        return 0;
    *out = s->baro_q[s->baro_head];
    s->baro_head = (s->baro_head + 1) % SIM_DELAY_MAX;
    s->baro_count--;
    s->baro_ready = 0;
    return 1;
}

sensor_source sim_sensors_source(sim_sensors *s)
{
    sensor_source src;
    src.mode = SENSOR_SIM;
    src.name = "SIM_SENSOR (ICM-42688-P + BMP390 model)";
    src.ctx = s;
    src.read_imu = read_imu;
    src.read_baro = read_baro;
    return src;
}
