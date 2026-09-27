/*
 * RC channels -> pilot commands.
 *
 * Default channel order AETR (ch1 aileron/roll, ch2 elevator/pitch,
 * ch3 throttle, ch4 rudder/yaw), the EdgeTX / ExpressLRS default; AUX1 (ch5)
 * arms, AUX2 (ch6) picks the flight mode.  All of it is configurable.
 */
#ifndef RC_MAP_H
#define RC_MAP_H

#include <stdint.h>

typedef struct {
    int ch_roll, ch_pitch, ch_throttle, ch_yaw, ch_arm, ch_mode;  /* 0-based */
    int arm_on_us;            /* arm switch counts as on above this */
    int mode_low_us;          /* below: mode_low */
    int mode_high_us;         /* above: mode_high, between: mode_mid */
    int mode_low, mode_mid, mode_high;   /* flight_mode values */
} rc_map_params;

typedef struct {
    float roll, pitch, yaw;   /* -1..1, + = right / forward / right */
    float throttle;           /* 0..1 */
    int arm_switch;
    int mode;
} rc_command;

void rc_map_default(rc_map_params *p);
void rc_map_apply(const rc_map_params *p, const uint16_t ticks[16], rc_command *out);

#endif
