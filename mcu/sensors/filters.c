#include "filters.h"
#include "../common/fc_math.h"

void pt1_init(pt1_filter *f, float cutoff_hz, float dt)
{
    if (cutoff_hz <= 0.0f) {
        f->k = 1.0f;
    } else {
        float rc = 1.0f / (2.0f * FC_PI * cutoff_hz);
        f->k = dt / (rc + dt);
    }
    f->y = 0.0f;
}

float pt1_apply(pt1_filter *f, float x)
{
    f->y += f->k * (x - f->y);
    return f->y;
}

void pt1_reset(pt1_filter *f, float y) { f->y = y; }

void biquad_lpf_init(biquad_filter *f, float cutoff_hz, float sample_hz)
{
    f->x1 = f->x2 = f->y1 = f->y2 = 0.0f;
    if (cutoff_hz <= 0.0f || cutoff_hz >= 0.45f * sample_hz) {
        f->b0 = 1.0f;
        f->b1 = f->b2 = f->a1 = f->a2 = 0.0f;
        return;
    }
    const float q = 0.70710678f;                 /* Butterworth */
    float w0 = 2.0f * FC_PI * cutoff_hz / sample_hz;
    float cs = cosf(w0), alpha = sinf(w0) / (2.0f * q);
    float a0 = 1.0f + alpha;
    f->b0 = (1.0f - cs) * 0.5f / a0;
    f->b1 = (1.0f - cs) / a0;
    f->b2 = f->b0;
    f->a1 = -2.0f * cs / a0;
    f->a2 = (1.0f - alpha) / a0;
}

float biquad_apply(biquad_filter *f, float x)
{
    float y = f->b0 * x + f->b1 * f->x1 + f->b2 * f->x2 - f->a1 * f->y1 - f->a2 * f->y2;
    f->x2 = f->x1;
    f->x1 = x;
    f->y2 = f->y1;
    f->y1 = y;
    return y;
}
