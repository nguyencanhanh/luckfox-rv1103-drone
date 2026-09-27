/*
 * Quad-X mixer (plan section 11).
 *
 * Motor order is the board's (hardware/LFX_FC_R1/scripts/design.py:294,
 * Betaflight numbering): M1 rear-right, M2 front-right, M3 rear-left,
 * M4 front-left.  Axis signs, FRD body:
 *   roll  > 0  right side down  -> left motors (M3, M4) up
 *   pitch > 0  nose up          -> front motors (M2, M4) up
 *   yaw   > 0  nose right       -> the motors whose drag torque turns the
 *                                  body right (props spinning CCW seen from
 *                                  above) up
 * Prop spin is a parameter because it depends on how the props are fitted.
 *
 * Saturation: attitude first.  If roll/pitch/yaw need more spread than 0..1
 * allows they are scaled down together; then the collective is shifted so
 * the result fits.  Outputs are always clamped to 0..1.
 */
#ifndef MIXER_H
#define MIXER_H

#define MIXER_MOTORS 4

typedef struct {
    float roll[MIXER_MOTORS];
    float pitch[MIXER_MOTORS];
    float yaw[MIXER_MOTORS];
} mixer_table;

typedef struct {
    float motor[MIXER_MOTORS];   /* 0..1 */
    int saturated;               /* the request did not fit */
} mixer_out;

/* spin_cw[i] = 1 if motor i turns clockwise seen from above */
void mixer_quadx_table(mixer_table *t, const int spin_cw[MIXER_MOTORS]);
/* throttle 0..1, roll/pitch/yaw roughly -1..1 */
void mixer_mix(const mixer_table *t, float throttle, float roll, float pitch,
               float yaw, mixer_out *out);

#endif
