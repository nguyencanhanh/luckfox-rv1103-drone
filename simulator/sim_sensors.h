/*
 * SIM_SENSOR: the simulated ICM-42688-P and BMP390 (plan section 26: sensor
 * noise, sensor latency).  It implements the same sensor_source interface a
 * real driver will, so the flight core cannot tell the difference.
 *
 * Datasheet numbers (hardware/datasheets):
 *   gyro noise density   0.0028 dps/sqrt(Hz)        DS-000347 v1.7, p.11
 *   gyro initial ZRO     +-0.5 dps (board level)     same table
 *   accel noise density  65 (x, y) / 70 (z) ug/sqrt(Hz)
 *   accel zero-g offset  +-20 mg (board level)
 *   baro RMS noise       2.0 Pa, standard resolution, IIR off
 *                        (BMP390 datasheet table 8)
 * ASSUMED: sensor bandwidth, vibration, latencies.  Real frames vibrate far
 * more than the chips' own noise; the "vibration" terms stand in for that and
 * are off in the datasheet-only profile.
 */
#ifndef SIM_SENSORS_H
#define SIM_SENSORS_H

#include <stdint.h>
#include "quad_model.h"
#include "../mcu/sensors/sensor_if.h"

#define SIM_DELAY_MAX 64

typedef struct {
    float gyro_nd;               /* rad/s/sqrt(Hz) */
    float acc_nd_xy, acc_nd_z;   /* m/s^2/sqrt(Hz) */
    float bandwidth_hz;          /* noise bandwidth of the sampled signal */
    float gyro_bias_max;         /* rad/s, drawn uniformly per axis */
    float acc_bias_max;          /* m/s^2 */
    float vib_gyro, vib_acc;     /* extra rms per unit motor speed (ASSUMED) */
    int imu_delay;               /* samples */
    float baro_hz;
    float baro_noise_pa;
    int baro_delay;              /* baro samples */
} sim_sensor_params;

typedef struct {
    sim_sensor_params p;
    const quad_model *model;
    uint32_t rng;
    vec3 gyro_bias, acc_bias;
    imu_sample imu_q[SIM_DELAY_MAX];
    baro_sample baro_q[SIM_DELAY_MAX];
    int imu_head, imu_count, baro_head, baro_count;
    float baro_timer;
    int imu_ready, baro_ready;
    int imu_failed;              /* fault injection: the IMU stops answering */
    float ground_pressure;
} sim_sensors;

void sim_sensor_default_params(sim_sensor_params *p, int datasheet_only);
void sim_sensors_init(sim_sensors *s, const sim_sensor_params *p, const quad_model *m,
                      uint32_t seed);
/* sample the model once per loop tick (1 kHz) */
void sim_sensors_sample(sim_sensors *s, uint32_t t_us, float dt);
/* the SENSOR_SIM sensor_source backed by this object */
sensor_source sim_sensors_source(sim_sensors *s);
float sim_randn(uint32_t *state);

#endif
