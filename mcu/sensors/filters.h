/*
 * Low-pass filters for the sensor path (plan section 7: Filtering).
 *   pt1     first order, for D-terms and slow signals
 *   biquad  second order Butterworth low-pass (RBJ cookbook form), for gyro
 */
#ifndef FILTERS_H
#define FILTERS_H

typedef struct { float k, y; } pt1_filter;

typedef struct {
    float b0, b1, b2, a1, a2;
    float x1, x2, y1, y2;
} biquad_filter;

void pt1_init(pt1_filter *f, float cutoff_hz, float dt);
float pt1_apply(pt1_filter *f, float x);
void pt1_reset(pt1_filter *f, float y);

/* cutoff_hz <= 0 or >= 0.45 * sample rate turns the filter into a pass-through */
void biquad_lpf_init(biquad_filter *f, float cutoff_hz, float sample_hz);
float biquad_apply(biquad_filter *f, float x);

#endif
