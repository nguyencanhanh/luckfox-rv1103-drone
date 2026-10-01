/*
 * The whole software-in-the-loop world, stepped at the flight loop rate:
 *
 *   pilot sticks -> CRSF frames (the byte stream an ELRS receiver sends)
 *     -> link + Linux + IPC latency -> crsf_parser -> rc_map -> fc_rc_input
 *   quad_model -> sim_sensors (SIM_SENSOR) -> fc_tick() -> 4 motor numbers
 *     -> quad_model
 *
 * fc_tick() is the same function the MCU will call with REAL_SENSOR.
 * Fault injection: RC link cut, IMU failure, wind and gusts.
 */
#ifndef SIM_H
#define SIM_H

#include <stdint.h>
#include "quad_model.h"
#include "sim_sensors.h"
#include "../mcu/fc/fc.h"
#include "../shared/rc/crsf.h"
#include "../shared/rc/rc_map.h"
#include "../mcu/link/fc_link.h"

#define SIM_LINK_QUEUE 64

typedef struct {
    uint8_t bytes[CRSF_RC_FRAME_LEN];
    float deliver_at;
} sim_frame;

typedef struct {
    quad_model quad;
    sim_sensors sens;
    sensor_source src;
    fc_t fc;
    fc_params fcp;
    crsf_parser crsf;
    rc_map_params map;

    /* pilot (the transmitter) */
    float stick_roll, stick_pitch, stick_yaw, stick_throttle;
    int arm_switch, mode_pos;       /* mode switch 0 / 1 / 2 */
    float packet_hz;                /* ELRS packet rate */
    float link_latency;             /* s, air + UART + Linux + IPC (ASSUMED) */
    float packet_timer;
    sim_frame q[SIM_LINK_QUEUE];
    int q_len;
    uint32_t frames_sent, frames_delivered;

    /* environment and faults */
    vec3 wind;                      /* steady air velocity, m/s, world */
    float gust;                     /* random air velocity rms, m/s */
    vec3 gust_now;
    int link_cut;

    /* drone mode: RC comes over the Linux link (shared/ipc), not from the
     * built-in transmitter - a real ground station / rc-bridge flies it */
    int ipc_mode;
    fc_link link;

    float motor[4];
    float t;
    uint32_t t_us;
} sim_t;

void sim_init(sim_t *s, uint32_t seed, int datasheet_only);
void sim_set_pilot(sim_t *s, float roll, float pitch, float yaw, float throttle,
                   int arm_switch, int mode_pos);
void sim_set_faults(sim_t *s, int link_cut, int imu_fail);
void sim_set_wind(sim_t *s, float north_ms, float east_ms, float gust_ms);
void sim_step(sim_t *s, int ticks);
/* drone mode: take RC from (and report telemetry to) the fc_ipc page at `page`
 * (4 KB, e.g. an mmap'ed file shared with linux/rc-bridge); formats it */
void sim_attach_ipc(sim_t *s, void *page);

/* the pilot's level calibration (craft still, disarmed); 1 if started */
int sim_request_level_calibration(sim_t *s);
/* for callers that allocate sim_t themselves (the Python bridge) */
unsigned long sim_sizeof(void);

/* flat snapshot for the Python bridge and CSV logs; names match values */
const char *sim_state_names(void);
int sim_get_state(const sim_t *s, float *out, int max);

#endif
