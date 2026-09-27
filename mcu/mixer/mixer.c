#include "mixer.h"
#include "../common/fc_math.h"

/* motor positions, sign only: +x front, +y right */
static const float POS_X[MIXER_MOTORS] = {-1.0f, 1.0f, -1.0f, 1.0f};
static const float POS_Y[MIXER_MOTORS] = { 1.0f, 1.0f, -1.0f, -1.0f};

void mixer_quadx_table(mixer_table *t, const int spin_cw[MIXER_MOTORS])
{
    for (int i = 0; i < MIXER_MOTORS; i++) {
        /* thrust at +y rolls the body left, so roll+ needs the -y motors */
        t->roll[i] = -POS_Y[i];
        t->pitch[i] = POS_X[i];
        /* a CW prop's drag turns the body CCW (nose left): lower it for yaw+ */
        t->yaw[i] = spin_cw[i] ? -1.0f : 1.0f;
    }
}

void mixer_mix(const mixer_table *t, float throttle, float roll, float pitch,
               float yaw, mixer_out *out)
{
    float d[MIXER_MOTORS];
    float lo = 1e9f, hi = -1e9f;
    for (int i = 0; i < MIXER_MOTORS; i++) {
        d[i] = t->roll[i] * roll + t->pitch[i] * pitch + t->yaw[i] * yaw;
        lo = d[i] < lo ? d[i] : lo;
        hi = d[i] > hi ? d[i] : hi;
    }
    out->saturated = 0;
    float spread = hi - lo;
    if (spread > 1.0f) {
        float s = 1.0f / spread;
        for (int i = 0; i < MIXER_MOTORS; i++)
            d[i] *= s;
        lo *= s;
        hi *= s;
        out->saturated = 1;
    }
    float thr = throttle;
    if (thr + hi > 1.0f) {
        thr = 1.0f - hi;
        out->saturated = 1;
    }
    if (thr + lo < 0.0f) {
        thr = -lo;
        out->saturated = 1;
    }
    for (int i = 0; i < MIXER_MOTORS; i++)
        out->motor[i] = constrainf(thr + d[i], 0.0f, 1.0f);
}
