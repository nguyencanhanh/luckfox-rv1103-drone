#include "fc_ipc.h"
#include <string.h>

#if defined(__riscv)
#define FC_IPC_BARRIER() __asm__ volatile("fence rw, rw" ::: "memory")
#else
#define FC_IPC_BARRIER() __sync_synchronize()
#endif

uint16_t fc_ipc_crc16(const void *data, size_t len)
{
    const uint8_t *p = data;
    uint16_t crc = 0xFFFF;
    while (len--) {
        crc ^= (uint16_t)(*p++) << 8;
        for (int b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}

static void clean(struct fc_ipc_port *p, const volatile void *a, size_t n)
{
    if (p->clean)
        p->clean(a, n);
}

static void inval(struct fc_ipc_port *p, const volatile void *a, size_t n)
{
    if (p->inval)
        p->inval(a, n);
}

void fc_ipc_format(struct fc_ipc_port *port)
{
    struct fc_ipc_page *pg = port->page;
    memset((void *)pg, 0, sizeof(*pg));
    pg->page_size = FC_IPC_PAGE_SIZE;
    pg->slots = FC_IPC_SLOTS;
    pg->version = FC_IPC_VERSION;
    FC_IPC_BARRIER();
    pg->magic = FC_IPC_MAGIC;            /* last: a reader never sees half a format */
    clean(port, pg, sizeof(*pg));
}

int fc_ipc_valid(const struct fc_ipc_port *port)
{
    const struct fc_ipc_page *pg = port->page;
    if (port->inval)
        port->inval(pg, 64);
    return pg->magic == FC_IPC_MAGIC && pg->version == FC_IPC_VERSION && pg->slots == FC_IPC_SLOTS;
}

int fc_ipc_send(struct fc_ipc_port *port, struct fc_ipc_ring *ring, uint16_t type,
                const void *payload, uint16_t len)
{
    if (len > FC_IPC_PAYLOAD)
        return 0;
    inval(port, &ring->tail, 4);
    uint32_t head = ring->head, tail = ring->tail;
    if (head - tail >= FC_IPC_SLOTS)
        return 0;                                   /* full: consumer is behind */
    struct fc_ipc_record r;
    memset(&r, 0, sizeof(r));
    r.type = type;
    r.len = len;
    r.seq = ++port->tx_seq;
    memcpy(r.payload, payload, len);
    r.crc = fc_ipc_crc16(&r, offsetof(struct fc_ipc_record, crc));
    struct fc_ipc_record *slot = &ring->slot[head % FC_IPC_SLOTS];
    memcpy(slot, &r, sizeof(r));
    clean(port, slot, sizeof(*slot));
    FC_IPC_BARRIER();
    ring->head = head + 1;
    clean(port, &ring->head, 4);
    return 1;
}

int fc_ipc_recv(struct fc_ipc_port *port, struct fc_ipc_ring *ring, struct fc_ipc_record *out)
{
    inval(port, &ring->head, 4);
    uint32_t head = ring->head, tail = ring->tail;
    if (head == tail)
        return 0;
    if (head - tail > FC_IPC_SLOTS) {               /* producer lapped us: resync */
        port->rx_dropped += head - tail - FC_IPC_SLOTS;
        tail = head - FC_IPC_SLOTS;
    }
    FC_IPC_BARRIER();
    while (tail != head) {
        struct fc_ipc_record *slot = &ring->slot[tail % FC_IPC_SLOTS];
        inval(port, slot, sizeof(*slot));
        memcpy(out, (const void *)slot, sizeof(*out));
        tail++;
        if (out->crc != fc_ipc_crc16(out, offsetof(struct fc_ipc_record, crc))
            || out->len > FC_IPC_PAYLOAD) {
            port->rx_crc_err++;
            continue;
        }
        port->rx_seq_last = out->seq;
        port->rx_ok++;
        ring->tail = tail;
        clean(port, &ring->tail, 4);
        return 1;
    }
    ring->tail = tail;
    clean(port, &ring->tail, 4);
    return 0;
}
