/*
 * Rigid-body quadcopter for software-in-the-loop (plan section 26: dynamics,
 * gravity, motor thrust, roll / pitch / yaw torque).
 *
 * Model (Gibiansky, "Quadcopter Dynamics and Simulation";
 * PX4 SITL motor model, github.com/PX4/sitl_gazebo/issues/110):
 *   motor:   first-order lag on normalised speed w, dw/dt = (u - w) / tau
 *   thrust:  T = T_max * w^2          (thrust ~ rotor speed squared)
 *   drag torque about body z:  Q = k_q * T, sign set by spin direction
 *   body:    m dv/dt = R (0, 0, -sum T) + m g - c_lin (v - v_wind)   (NED)
 *            c_lin is rotor drag, linear in airspeed (Faessler, Franchi,
 *            Scaramuzza, "Differential Flatness of Quadrotor Dynamics Subject
 *            to Rotor Drag", RA-L 2018), plus a small quadratic body drag
 *            I dw/dt = tau - w x I w - c_rot w
 *   ground:  z = 0 plane; resting on it cancels downward motion
 *
 * The airframe numbers are ASSUMED (no frame is chosen yet): a ~0.6 kg quad,
 * 225 mm motor-to-motor, 6 N per motor (thrust/weight ~4).  Put measured
 * values in quad_params when a craft exists.
 */
#ifndef QUAD_MODEL_H
#define QUAD_MODEL_H

#include "../mcu/common/fc_math.h"

#define QUAD_MOTORS 4

typedef struct {
    float mass;                  /* kg */
    float arm;                   /* m, centre to motor */
    vec3 inertia;                /* kg m^2, principal axes */
    float t_max;                 /* N per motor at full command */
    float motor_tau;             /* s */
    float k_q;                   /* m: drag torque / thrust */
    float drag_lin;              /* N per m/s of airspeed (rotor drag) */
    float drag_quad;             /* N per (m/s)^2 (body) */
    float drag_rot;              /* N m per rad/s */
    int spin_cw[QUAD_MOTORS];    /* seen from above */
    float crash_speed;           /* m/s into the ground = crashed */
} quad_params;

typedef struct {
    quad_params p;
    vec3 pos, vel;               /* NED world, m and m/s */
    quat q;                      /* body -> world */
    vec3 w;                      /* body rate, rad/s */
    vec3 acc_body;               /* specific force the IMU would feel, m/s^2 */
    float motor_w[QUAD_MOTORS];  /* normalised speed 0..1 */
    float thrust[QUAD_MOTORS];   /* N */
    int on_ground;
    int crashed;
    float time;
} quad_model;

void quad_default_params(quad_params *p);
void quad_init(quad_model *m, const quad_params *p);
/* u: 0..1 per motor; wind: world-frame air velocity, m/s */
void quad_step(quad_model *m, const float u[QUAD_MOTORS], vec3 wind, float dt);
/* hover command for this airframe: sqrt(m g / (4 T_max)) */
float quad_hover_command(const quad_params *p);

#endif
