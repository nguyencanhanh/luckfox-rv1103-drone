#include "gyro_calib.h"

void gyro_calib_init(gyro_calib *c, uint32_t samples_needed, float max_dev)
{
    c->samples_needed = samples_needed;
    c->max_dev = max_dev;
    c->bias = v3(0.0f, 0.0f, 0.0f);
    c->done = 0;
    gyro_calib_restart(c);
}

void gyro_calib_restart(gyro_calib *c)
{
    c->n = 0;
    c->sum = v3(0.0f, 0.0f, 0.0f);
}

int gyro_calib_feed(gyro_calib *c, vec3 g)
{
    if (c->n == 0)
        c->first = g;
    /* movement check against the first sample of the window: cheap, and a
     * still gyro only shows noise (0.028 dps rms at 100 Hz, DS-000347) */
    vec3 d = v3_sub(g, c->first);
    if (fabsf(d.x) > c->max_dev || fabsf(d.y) > c->max_dev || fabsf(d.z) > c->max_dev) {
        gyro_calib_restart(c);
        return c->done;
    }
    c->sum = v3_add(c->sum, g);
    if (++c->n >= c->samples_needed) {
        c->bias = v3_scale(c->sum, 1.0f / (float)c->n);
        c->done = 1;
        gyro_calib_restart(c);
    }
    return c->done;
}
