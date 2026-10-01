/*
 * Linux <-> MCU message channel in shared DDR (plan items 12-14, docs/IPC.md).
 *
 * The SDK has no RPMsg / mailbox driver for RV1106 (docs/IPC.md), so this is two
 * single-producer / single-consumer rings polled by both sides:
 *
 *   down  Linux -> MCU   RC channels (CRSF ticks, already the receiver's view),
 *                        heartbeat
 *   up    MCU -> Linux   telemetry (state, attitude, height, motors, timing)
 *
 * It lives in the 4 KB page at MCU_IPC_BASE (= the Milestone-1 benchmark page,
 * shared/ipc/mcu_layout.h), which the M1 device tree already reserves: no new
 * reserved-memory and no Linux reflash is needed.  A firmware uses that page for
 * either the benchmark or the IPC, never both.
 *
 * Rules that make it safe without coherent caches or locks:
 *  - each index is written by exactly one side (head by the producer, tail by the
 *    consumer) and sits on its own 64-byte line;
 *  - a record is written in full, its cache line(s) cleaned, a barrier, and only
 *    then head moves;
 *  - every record carries a sequence number and a CRC-16; a torn or stale read
 *    fails the CRC and is dropped, never acted on;
 *  - the consumer that finds the ring full-of-old-data simply skips to the newest
 *    record (RC wants the latest command, not every command).
 * Plain C99, fixed-size types only: the same file builds for rv32 ilp32 (MCU),
 * ARM EABI (Linux) and the host (simulator, tests).
 */
#ifndef FC_IPC_H
#define FC_IPC_H

#include <stdint.h>
#include <stddef.h>

#define FC_IPC_MAGIC        0x43504946u        /* "FIPC" */
#define FC_IPC_VERSION      1u
#define FC_IPC_SLOTS        16u                /* per ring, power of two */
#define FC_IPC_PAYLOAD      52u
#define FC_IPC_PAGE_SIZE    4096u

enum fc_ipc_type {
    FC_IPC_RC = 1,          /* down: struct fc_ipc_rc */
    FC_IPC_HEARTBEAT = 2,   /* down: struct fc_ipc_heartbeat */
    FC_IPC_TELEMETRY = 16,  /* up:   struct fc_ipc_telemetry */
};

/* RC source the Linux side forwarded */
enum fc_ipc_rc_source { FC_RC_NONE = 0, FC_RC_ELRS = 1, FC_RC_NETWORK = 2 };

struct fc_ipc_rc {
    uint16_t ch[16];        /* CRSF ticks 172..1811, as the receiver delivered them */
    uint8_t source;         /* enum fc_ipc_rc_source */
    uint8_t link_quality;   /* %, 0 = unknown */
    int8_t rssi_dbm;        /* 0 = unknown */
    uint8_t reserved;
};

struct fc_ipc_heartbeat {
    uint32_t linux_ms;      /* Linux monotonic time, ms */
    uint32_t flags;
};

struct fc_ipc_telemetry {
    uint32_t mcu_ms;        /* MCU time, ms */
    uint8_t state;          /* fc_state */
    uint8_t mode;           /* flight_mode */
    uint8_t rc_source;      /* source of the last RC the MCU used */
    uint8_t disarm_reason;
    uint16_t arm_blocks;    /* arm_block bits */
    int16_t roll_cdeg, pitch_cdeg, yaw_cdeg;    /* attitude estimate, 0.01 deg */
    int16_t height_cm, climb_cms;               /* altitude estimate */
    uint8_t motor[4];       /* 0..255 */
    uint16_t loop_us_max;   /* longest flight-loop tick since the last report */
    uint16_t loop_us_avg;
    uint8_t alt_valid, calib_done;
};

struct fc_ipc_record {
    uint16_t type;
    uint16_t len;
    uint32_t seq;
    uint8_t payload[FC_IPC_PAYLOAD];
    uint16_t crc;           /* CRC-16/CCITT-FALSE over type..payload */
    uint16_t pad;
};

struct fc_ipc_ring {
    volatile uint32_t head;             /* producer: next slot to write */
    uint8_t _h[60];
    volatile uint32_t tail;             /* consumer: next slot to read */
    uint8_t _t[60];
    struct fc_ipc_record slot[FC_IPC_SLOTS];
};

struct fc_ipc_page {
    uint32_t magic, version, page_size, slots;
    volatile uint32_t mcu_alive;        /* MCU increments every report */
    volatile uint32_t linux_alive;      /* Linux increments every heartbeat */
    uint8_t _pad[40];
    struct fc_ipc_ring down;            /* Linux -> MCU */
    struct fc_ipc_ring up;              /* MCU -> Linux */
};

/* platform hooks: clean = push this CPU's writes to DDR, inval = drop stale lines.
 * NULL on cache-coherent or uncached mappings (Linux /dev/mem O_SYNC, the host). */
struct fc_ipc_port {
    struct fc_ipc_page *page;
    void (*clean)(const volatile void *p, size_t n);
    void (*inval)(const volatile void *p, size_t n);
    uint32_t tx_seq;
    uint32_t rx_seq_last;
    uint32_t rx_ok, rx_crc_err, rx_dropped;
};

uint16_t fc_ipc_crc16(const void *data, size_t len);
/* MCU calls this once (it owns the page layout); Linux checks it with fc_ipc_valid */
void fc_ipc_format(struct fc_ipc_port *port);
int fc_ipc_valid(const struct fc_ipc_port *port);
/* 1 = sent, 0 = ring full (record dropped) */
int fc_ipc_send(struct fc_ipc_port *port, struct fc_ipc_ring *ring, uint16_t type,
                const void *payload, uint16_t len);
/* 1 = one good record copied out, 0 = nothing new */
int fc_ipc_recv(struct fc_ipc_port *port, struct fc_ipc_ring *ring, struct fc_ipc_record *out);

/* Layout checks: both compilers must agree (rv32 ilp32 and ARM EABI). */
_Static_assert(sizeof(struct fc_ipc_rc) <= FC_IPC_PAYLOAD, "rc payload");
_Static_assert(sizeof(struct fc_ipc_telemetry) <= FC_IPC_PAYLOAD, "telemetry payload");
_Static_assert(sizeof(struct fc_ipc_record) == 64, "record is one cache line");
_Static_assert(sizeof(struct fc_ipc_page) <= FC_IPC_PAGE_SIZE, "fits the 4 KB page");

#endif
