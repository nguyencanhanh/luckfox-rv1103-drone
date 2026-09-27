/*
 * Cascaded flight controller (plan section 7):
 *
 *   ALT_HOLD  100 Hz  height -> climb-rate setpoint -> climb-rate PID -> collective
 *   ANGLE     250 Hz  angle error x P -> body-rate setpoint (limited)
 *   rate     1000 Hz  body-rate PID per axis -> roll / pitch / yaw demand
 *   mixer    1000 Hz  demand -> 4 motors
 *
 * ACRO uses the rate loop only, sticks map to body rates.  Every number lives
 * in control_params; nothing is hard-coded in the algorithm (plan section 10).
 */
#ifndef CONTROL_H
#define CONTROL_H

#include <stdint.h>
#include "pid.h"
#include "../common/fc_math.h"

typedef enum { MODE_ACRO = 0, MODE_ANGLE = 1, MODE_ALT_HOLD = 2 } flight_mode;

typedef struct {
    pid_params rate[3];          /* roll, pitch, yaw: rad/s in, mixer units out */
    float angle_kp;              /* (rad/s) per rad */
    float max_angle;             /* rad, ANGLE / ALT_HOLD full stick */
    float max_angle_rate;        /* rad/s the angle loop may ask for */
    float acro_rate;             /* rad/s, ACRO full stick roll/pitch */
    float yaw_rate;              /* rad/s, full yaw stick */
    float stick_expo;            /* 0..1 */
    float stick_deadband;        /* fraction of full stick */
    pid_params climb;            /* m/s in, collective out */
    float alt_kp;                /* (m/s) per m */
    float max_climb, max_descent;/* m/s */
    float hover_throttle;        /* collective that holds height, first guess */
    float thr_min;               /* idle collective while armed */
    float thr_max;
    float tilt_comp_max;         /* cap on 1/cos(tilt) collective boost */
    float fs_descent_rate;       /* m/s, failsafe landing */
    float fs_throttle;           /* collective used when height is unknown */
    float land_vz;               /* |climb rate| below this ... */
    float land_s;                /* ... for this long, at low collective = landed */
    uint32_t angle_div;          /* angle loop runs every angle_div rate ticks */
    uint32_t alt_div;            /* altitude loop every alt_div rate ticks */
    float iterm_relax_rate;      /* rad/s^2: faster setpoint change freezes I */
    float iterm_relax_hz;        /* low-pass on the setpoint rate of change */
} control_params;

typedef struct {
    float roll, pitch, yaw;      /* -1..1 */
    float throttle;              /* 0..1 */
    flight_mode mode;
} control_sticks;

typedef struct {
    int armed;
    int failsafe;                /* 0 none, 1 hold level, 2 land */
    int mixer_saturated;         /* from the previous mix */
    int alt_valid;
    float height, climb;         /* estimate, m and m/s up */
    quat q;
    vec3 euler;                  /* estimate, rad */
    vec3 rate;                   /* filtered body rate, rad/s */
} control_state;

typedef struct {
    control_params p;
    pid_ctrl rate_pid[3];
    pid_ctrl climb_pid;
    vec3 rate_sp;                /* rad/s */
    vec3 angle_sp;               /* rad */
    float climb_sp, height_sp;
    float collective;            /* before tilt compensation */
    float collective_out;        /* to the mixer */
    int alt_engaged;
    float fs_hold_collective;
    float land_timer;
    int landed;
    uint32_t tick;
    vec3 demand;                 /* roll, pitch, yaw to the mixer */
    vec3 prev_rate_sp;
    pt1_filter sp_slope[3];
} controller;

void control_init(controller *c, const control_params *p, float dt);
void control_reset(controller *c);
/* call at the rate-loop rate (1 kHz); runs the slower loops by division */
void control_step(controller *c, const control_sticks *s, const control_state *st, float dt);
float stick_shape(float x, float expo, float deadband);

#endif
