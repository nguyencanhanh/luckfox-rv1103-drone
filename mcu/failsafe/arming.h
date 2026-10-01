/*
 * Arming and failsafe state machine (plan sections 29 and 18-ish: "Never
 * enable ARMED motor output automatically after boot.  Default: DISARMED").
 *
 * Arming needs ALL of: a rising edge on the arm switch (a switch that is
 * already on at boot does nothing until it is cycled), throttle stick low,
 * a live RC link, a live IMU, a finished gyro calibration, and a nearly level
 * craft.  Disarm is immediate on the switch.
 *
 * Failsafe, in stages:
 *   RC lost > rc_timeout      stage 1: hold level, hold throttle, for
 *                             fs_hold_s (TBS: wait ~1 s before acting,
 *                             github.com/tbs-fpv/tbs-crsf-spec)
 *   still lost                stage 2: level, descend at fs_descent_rate
 *                             with the altitude estimate, or a fixed
 *                             fs_throttle without one; disarm when landed,
 *                             or when the time is up: fs_land_s plus the
 *                             time the descent itself needs from the height
 *                             at which the landing began (a fixed limit would
 *                             cut the motors in mid-air above ~14 m)
 *   IMU silent > imu_timeout  motors off at once (nothing to fly with)
 *   tilt > crash_tilt for crash_s while armed in a self-levelling mode:
 *                             motors off (crashed / flipped)
 * The link coming back during stage 1 hands control back; after stage 2 has
 * begun the pilot must disarm and re-arm.
 */
#ifndef ARMING_H
#define ARMING_H

#include <stdint.h>

typedef enum {
    FC_DISARMED = 0,
    FC_ARMED,
    FC_FAILSAFE_HOLD,
    FC_FAILSAFE_LAND,
} fc_state;

typedef enum {
    ARM_OK = 0,
    ARM_BLOCK_SWITCH_NOT_CYCLED = 1 << 0,
    ARM_BLOCK_THROTTLE = 1 << 1,
    ARM_BLOCK_RC = 1 << 2,
    ARM_BLOCK_IMU = 1 << 3,
    ARM_BLOCK_CALIB = 1 << 4,
    ARM_BLOCK_TILT = 1 << 5,
    ARM_BLOCK_FAILSAFE = 1 << 6,
} arm_block;

typedef enum {
    DISARM_NONE = 0,
    DISARM_SWITCH,
    DISARM_IMU_LOST,
    DISARM_CRASH,
    DISARM_FAILSAFE_LANDED,
    DISARM_FAILSAFE_TIMEOUT,
} disarm_reason;

typedef struct {
    float rc_timeout_s;
    float imu_timeout_s;
    float arm_max_tilt;        /* rad */
    float arm_max_throttle;    /* stick 0..1 */
    float fs_hold_s;
    float fs_land_s;
    float crash_tilt;          /* rad */
    float crash_s;
} arming_params;

typedef struct {
    int rc_ok, imu_ok, calib_ok;
    int arm_switch;            /* 0/1 */
    float throttle_stick;      /* 0..1 */
    float tilt;                /* rad from level */
    int landed;                /* from the controller's land detector */
    int crash_check;           /* 0 in ACRO: a flip is not a crash */
    float fs_descent_s;        /* time to descend from here (0 = height unknown) */
} arming_inputs;

typedef struct {
    arming_params p;
    fc_state state;
    int prev_switch;
    int switch_seen_off;       /* the switch has been off since boot/disarm */
    float rc_lost_s, imu_lost_s, crash_timer, fs_timer;
    float fs_budget;           /* landing time allowed, fixed when the landing began */
    uint32_t blocks;           /* why the last arm attempt (or now) is refused */
    disarm_reason last_disarm;
} arming_sm;

void arming_init(arming_sm *a, const arming_params *p);
/* dt in seconds; returns the new state */
fc_state arming_update(arming_sm *a, const arming_inputs *in, float dt);
const char *fc_state_name(fc_state s);

#endif
