/*
 * Gyro bias at rest (plan section 7: Calibration).
 *
 * Averages the gyro over a window while the craft is disarmed and still.  A
 * window whose spread is too large (someone is holding or moving it) is
 * thrown away and the count starts over, so the bias is never learnt from
 * motion.  Arming is refused until a bias exists.
 */
#ifndef GYRO_CALIB_H
#define GYRO_CALIB_H

#include <stdint.h>
#include "../common/fc_math.h"

typedef struct {
    uint32_t samples_needed;   /* window length, samples */
    float max_dev;             /* rad/s: any axis leaving mean +- this restarts */
    uint32_t n;
    vec3 sum, first;
    vec3 bias;
    int done;
} gyro_calib;

void gyro_calib_init(gyro_calib *c, uint32_t samples_needed, float max_dev);
/* feed one raw sample; returns 1 once a bias is available */
int gyro_calib_feed(gyro_calib *c, vec3 gyro);
void gyro_calib_restart(gyro_calib *c);

#endif
