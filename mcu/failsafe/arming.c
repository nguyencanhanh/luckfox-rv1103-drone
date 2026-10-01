#include "arming.h"

void arming_init(arming_sm *a, const arming_params *p)
{
    a->p = *p;
    a->state = FC_DISARMED;
    a->prev_switch = 0;
    a->switch_seen_off = 0;
    a->rc_lost_s = a->imu_lost_s = a->crash_timer = a->fs_timer = 0.0f;
    a->fs_budget = p->fs_land_s;
    a->blocks = 0;
    a->last_disarm = DISARM_NONE;
}

const char *fc_state_name(fc_state s)
{
    switch (s) {
    case FC_DISARMED: return "DISARMED";
    case FC_ARMED: return "ARMED";
    case FC_FAILSAFE_HOLD: return "FAILSAFE_HOLD";
    case FC_FAILSAFE_LAND: return "FAILSAFE_LAND";
    }
    return "?";
}

static void disarm(arming_sm *a, disarm_reason why)
{
    a->state = FC_DISARMED;
    a->last_disarm = why;
    a->switch_seen_off = 0;       /* must see the switch off again */
    a->fs_timer = a->crash_timer = 0.0f;
}

fc_state arming_update(arming_sm *a, const arming_inputs *in, float dt)
{
    a->rc_lost_s = in->rc_ok ? 0.0f : a->rc_lost_s + dt;
    a->imu_lost_s = in->imu_ok ? 0.0f : a->imu_lost_s + dt;
    int rc_live = a->rc_lost_s < a->p.rc_timeout_s;
    int imu_live = a->imu_lost_s < a->p.imu_timeout_s;

    /* the arm switch only counts while the link is up */
    int sw = rc_live ? in->arm_switch : a->prev_switch;
    int rising = sw && !a->prev_switch;
    if (rc_live && !sw)
        a->switch_seen_off = 1;
    a->prev_switch = sw;

    uint32_t b = 0;
    if (!a->switch_seen_off) b |= ARM_BLOCK_SWITCH_NOT_CYCLED;
    if (in->throttle_stick > a->p.arm_max_throttle) b |= ARM_BLOCK_THROTTLE;
    if (!rc_live) b |= ARM_BLOCK_RC;
    if (!imu_live) b |= ARM_BLOCK_IMU;
    if (!in->calib_ok) b |= ARM_BLOCK_CALIB;
    if (in->tilt > a->p.arm_max_tilt) b |= ARM_BLOCK_TILT;
    a->blocks = b;

    switch (a->state) {
    case FC_DISARMED:
        /* the rising edge itself must satisfy every condition; a refused
         * attempt needs the switch cycled again */
        if (rising && (b & ~ARM_BLOCK_SWITCH_NOT_CYCLED) == 0 && a->switch_seen_off) {
            a->state = FC_ARMED;
            a->last_disarm = DISARM_NONE;
        } else if (rising) {
            a->switch_seen_off = 0;
        }
        break;

    case FC_ARMED:
    case FC_FAILSAFE_HOLD:
    case FC_FAILSAFE_LAND:
        if (!imu_live) {
            disarm(a, DISARM_IMU_LOST);
            break;
        }
        a->crash_timer = (in->crash_check && in->tilt > a->p.crash_tilt) ? a->crash_timer + dt : 0.0f;
        if (a->crash_timer > a->p.crash_s) {
            disarm(a, DISARM_CRASH);
            break;
        }
        if (rc_live && !sw) {                       /* pilot kill, any state */
            disarm(a, DISARM_SWITCH);
            break;
        }
        if (a->state == FC_ARMED) {
            if (!rc_live) {
                a->state = FC_FAILSAFE_HOLD;
                a->fs_timer = 0.0f;
            }
        } else if (a->state == FC_FAILSAFE_HOLD) {
            a->fs_timer += dt;
            if (rc_live) {
                a->state = FC_ARMED;
            } else if (a->fs_timer > a->p.fs_hold_s) {
                a->state = FC_FAILSAFE_LAND;
                a->fs_timer = 0.0f;
                a->fs_budget = a->p.fs_land_s + (in->fs_descent_s > 0.0f ? in->fs_descent_s : 0.0f);
            }
        } else {                                    /* FAILSAFE_LAND */
            a->fs_timer += dt;
            if (in->landed)
                disarm(a, DISARM_FAILSAFE_LANDED);
            else if (a->fs_timer > a->fs_budget)
                disarm(a, DISARM_FAILSAFE_TIMEOUT);
        }
        break;
    }
    if (a->state != FC_DISARMED)
        a->blocks = 0;
    return a->state;
}
