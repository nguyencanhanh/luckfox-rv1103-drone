#include "fc_link.h"
#include <string.h>

void fc_link_init(fc_link *l, void *page, int owner, uint32_t report_every)
{
    memset(l, 0, sizeof(*l));
    l->port.page = page;
    rc_map_default(&l->map);
    l->report_every = report_every ? report_every : 20;
    if (owner)
        fc_ipc_format(&l->port);
}

int fc_link_poll(fc_link *l, fc_rc_input *rc)
{
    struct fc_ipc_record r;
    int fresh = 0;
    struct fc_ipc_rc last;
    /* drain: only the newest command matters, heartbeats are counted */
    while (fc_ipc_recv(&l->port, &l->port.page->down, &r)) {
        if (r.type == FC_IPC_RC && r.len >= sizeof(struct fc_ipc_rc)) {
            memcpy(&last, r.payload, sizeof(last));
            fresh = 1;
            l->rc_records++;
        } else if (r.type == FC_IPC_HEARTBEAT) {
            l->heartbeats++;
        }
    }
    if (!fresh)
        return 0;
    rc_command c;
    rc_map_apply(&l->map, last.ch, &c);
    rc->valid = 1;
    rc->sticks.roll = c.roll;
    rc->sticks.pitch = c.pitch;
    rc->sticks.yaw = c.yaw;
    rc->sticks.throttle = c.throttle;
    rc->sticks.mode = (flight_mode)c.mode;
    rc->arm_switch = c.arm_switch;
    l->rc_source = last.source;
    return 1;
}

static int16_t cdeg(float rad)
{
    float d = rad * FC_RAD2DEG * 100.0f;
    return (int16_t)constrainf(d, -32768.0f, 32767.0f);
}

void fc_link_tick(fc_link *l, const fc_t *fc, uint32_t now_ms, uint32_t loop_us)
{
    l->loop_us_max = loop_us > l->loop_us_max ? loop_us : l->loop_us_max;
    l->loop_us_sum += loop_us;
    l->loop_n++;
    if (++l->tick % l->report_every)
        return;
    struct fc_ipc_telemetry t;
    memset(&t, 0, sizeof(t));
    t.mcu_ms = now_ms;
    t.state = (uint8_t)fc->state;
    t.mode = (uint8_t)fc->rc.sticks.mode;
    t.rc_source = l->rc_source;
    t.disarm_reason = (uint8_t)fc->arm.last_disarm;
    t.arm_blocks = (uint16_t)fc->arm.blocks;
    t.roll_cdeg = cdeg(fc->att.euler.x);
    t.pitch_cdeg = cdeg(fc->att.euler.y);
    t.yaw_cdeg = cdeg(fc->att.euler.z);
    t.height_cm = (int16_t)constrainf(fc->alt.h * 100.0f, -32768.0f, 32767.0f);
    t.climb_cms = (int16_t)constrainf(fc->alt.v * 100.0f, -32768.0f, 32767.0f);
    for (int i = 0; i < 4; i++)
        t.motor[i] = (uint8_t)(constrainf(fc->motor[i], 0.0f, 1.0f) * 255.0f);
    t.loop_us_max = (uint16_t)(l->loop_us_max > 65535u ? 65535u : l->loop_us_max);
    t.loop_us_avg = (uint16_t)(l->loop_n ? l->loop_us_sum / l->loop_n : 0);
    t.alt_valid = (uint8_t)fc->alt.valid;
    t.calib_done = (uint8_t)fc->calib.done;
    fc_ipc_send(&l->port, &l->port.page->up, FC_IPC_TELEMETRY, &t, sizeof(t));
    l->port.page->mcu_alive++;
    l->loop_us_max = l->loop_us_sum = l->loop_n = 0;
}
