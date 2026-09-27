/*
 * The one boundary between the flight code and where its data comes from.
 *
 * REAL_SENSOR (the ICM-42688-P / BMP390 drivers, milestones 06-07) and
 * SIM_SENSOR (simulator/sim_sensors.c) both fill these structs; fc_step()
 * never knows which one it is talking to (plan section 26: "Không thay đổi
 * controller algorithm giữa hai mode").
 */
#ifndef SENSOR_IF_H
#define SENSOR_IF_H

#include <stdint.h>
#include "../common/fc_math.h"

typedef struct {
    uint32_t t_us;   /* sample time, microseconds, wraps */
    vec3 gyro;       /* body rate, rad/s, FRD */
    vec3 acc;        /* specific force, m/s^2, FRD (level and still: z = -g) */
} imu_sample;

typedef struct {
    uint32_t t_us;
    float pressure_pa;
    float temp_c;
} baro_sample;

typedef enum { SENSOR_REAL = 0, SENSOR_SIM = 1 } sensor_mode;

typedef struct sensor_source {
    sensor_mode mode;
    const char *name;
    void *ctx;
    /* 1 = a new sample was written, 0 = none yet, <0 = device error */
    int (*read_imu)(void *ctx, imu_sample *out);
    int (*read_baro)(void *ctx, baro_sample *out);
} sensor_source;

#endif
