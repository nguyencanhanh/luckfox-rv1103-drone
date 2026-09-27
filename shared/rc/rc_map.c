#include "rc_map.h"
#include "crsf.h"

void rc_map_default(rc_map_params *p)
{
    p->ch_roll = 0;
    p->ch_pitch = 1;
    p->ch_throttle = 2;
    p->ch_yaw = 3;
    p->ch_arm = 4;
    p->ch_mode = 5;
    p->arm_on_us = 1700;
    p->mode_low_us = 1300;
    p->mode_high_us = 1700;
    p->mode_low = 1;      /* MODE_ANGLE: self-level is the safe default */
    p->mode_mid = 2;      /* MODE_ALT_HOLD */
    p->mode_high = 0;     /* MODE_ACRO */
}

static float centred(uint16_t t)
{
    float v = (float)(crsf_ticks_to_us(t) - 1500) / 500.0f;
    return v < -1.0f ? -1.0f : (v > 1.0f ? 1.0f : v);
}

void rc_map_apply(const rc_map_params *p, const uint16_t ticks[16], rc_command *out)
{
    out->roll = centred(ticks[p->ch_roll]);
    out->pitch = centred(ticks[p->ch_pitch]);
    out->yaw = centred(ticks[p->ch_yaw]);
    float thr = (float)(crsf_ticks_to_us(ticks[p->ch_throttle]) - 1000) / 1000.0f;
    out->throttle = thr < 0.0f ? 0.0f : (thr > 1.0f ? 1.0f : thr);
    out->arm_switch = crsf_ticks_to_us(ticks[p->ch_arm]) > p->arm_on_us;
    int m = crsf_ticks_to_us(ticks[p->ch_mode]);
    out->mode = m < p->mode_low_us ? p->mode_low : (m > p->mode_high_us ? p->mode_high : p->mode_mid);
}
