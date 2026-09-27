/*
 * Height and climb rate from the barometer and the vertical accelerometer:
 * a third-order complementary filter (height, velocity, accelerometer bias).
 * The accelerometer carries the fast part, the barometer pins the slow part.
 *
 *   err = h_baro - h
 *   h  += (v + k1 err) dt
 *   v  += (a_up - b + k2 err) dt
 *   b  -= k3 err dt
 *
 * Choosing the three gains from one crossover w (rad/s) as k1 = 3w, k2 = 3w^2,
 * k3 = w^3 puts all three poles at -w.
 */
#ifndef ALTITUDE_H
#define ALTITUDE_H

#include "../common/fc_math.h"

typedef struct {
    float crossover;        /* rad/s */
    float baro_timeout_s;   /* no baro for this long: estimate invalid */
} altitude_params;

typedef struct {
    altitude_params p;
    float k1, k2, k3;
    float h, v, acc_bias;   /* metres above the reference, m/s up, m/s^2 */
    float p0;               /* reference pressure (Pa), taken at the first sample */
    float since_baro;
    int have_ref;
    int valid;
} altitude_est;

void altitude_init(altitude_est *e, const altitude_params *p);
/* ISA barometric formula, metres above the level where pressure is p0 */
float altitude_from_pressure(float pa, float p0);
/* re-zero: the current height becomes 0 (done at arming) */
void altitude_rezero(altitude_est *e, float pressure_pa);
void altitude_predict(altitude_est *e, quat q, vec3 acc_body, float dt);
void altitude_baro(altitude_est *e, float pressure_pa);

#endif
