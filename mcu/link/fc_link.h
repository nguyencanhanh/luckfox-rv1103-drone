/*
 * The flight core's side of the Linux link: RC in, telemetry out, over
 * shared/ipc/fc_ipc.h.  Used unchanged by the MCU firmware and by the simulator
 * when it plays the drone for a real ground station.
 *
 * RC arrives as CRSF channel ticks (whatever receiver or ground station Linux
 * chose); the mapping to sticks/switches (shared/rc/rc_map) happens here, on the
 * MCU, so the flight core decides what a channel means, not Linux.
 */
#ifndef FC_LINK_H
#define FC_LINK_H

#include "../fc/fc.h"
#include "../../shared/ipc/fc_ipc.h"
#include "../../shared/rc/rc_map.h"

typedef struct {
    struct fc_ipc_port port;
    rc_map_params map;
    uint8_t rc_source;          /* of the last RC record used */
    uint32_t rc_records, heartbeats;
    uint32_t report_every;      /* ticks between telemetry records */
    uint32_t tick;
    uint32_t loop_us_max, loop_us_sum, loop_n;
} fc_link;

/* page: the shared 4 KB page; owner = 1 formats it (MCU / simulated drone) */
void fc_link_init(fc_link *l, void *page, int owner, uint32_t report_every);
/* once per flight tick, before fc_step: 1 = a fresh RC record filled *rc */
int fc_link_poll(fc_link *l, fc_rc_input *rc);
/* once per flight tick, after fc_step; loop_us = how long this tick took */
void fc_link_tick(fc_link *l, const fc_t *fc, uint32_t now_ms, uint32_t loop_us);

#endif
