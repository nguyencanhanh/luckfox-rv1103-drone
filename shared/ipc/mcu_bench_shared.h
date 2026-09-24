/*
 * Ket qua benchmark vong lap realtime cua MCU, MCU ghi vao MCU_BENCH_BASE, Linux doc qua /dev/mem.
 * Chi dung kieu co kich thuoc co dinh; ca rv32 ilp32 va ARM EABI deu can uint64_t theo 8 byte.
 *
 * Doc nhat quan: seq le = MCU dang ghi. Linux doc seq, doc struct, doc lai seq, lap lai neu khac.
 */
#ifndef MCU_BENCH_SHARED_H
#define MCU_BENCH_SHARED_H

#include <stdint.h>

#define MCU_BENCH_MAGIC         0x4E42314Du     /* "M1BN" */
#define MCU_BENCH_VERSION       1u

#define MCU_CLK_SRC_MCYCLE      1u              /* CSR mcycle, dem theo chu ky loi */
#define MCU_CLK_SRC_MTIME       2u              /* SCR1 mtime sau bo chia */

/* So lieu cua mot lan chay; moi thoi gian tinh bang ns */
struct mcu_bench_run {
    uint64_t iterations;
    uint64_t missed;            /* chu ky > 1.5 x target */
    uint64_t overruns;          /* semaphore con gia tri khi thread thuc day: da lo mat tick */
    uint32_t period_min;
    uint32_t period_max;
    uint32_t period_avg;
    uint32_t jitter_max;        /* max |chu ky - target| */
    uint32_t period_p50;
    uint32_t period_p95;
    uint32_t period_p99;
    uint32_t period_p999;
    uint32_t period_p9999;
    uint32_t latency_min;       /* tu callback tick (ISR) toi luc thread chay */
    uint32_t latency_max;
    uint32_t latency_avg;
    uint32_t latency_p99;
    uint32_t latency_p9999;
    uint32_t hist_overflow;     /* mau vuot khoang histogram, percentile khi do la chan tren */
    uint32_t reserved;
};

struct mcu_bench_shared {
    uint32_t magic;
    uint32_t version;
    uint32_t seq;
    uint32_t clock_src;
    uint32_t clock_hz;          /* tan so danh nghia cua bo dem dang dung */
    uint32_t target_period_ns;
    uint32_t run_length;        /* so vong lap moi lan chay */
    uint32_t runs_done;
    uint64_t now_counts;        /* gia tri bo dem luc cap nhat; Linux dung de tu do tan so */
    uint64_t heartbeat;         /* tang moi lan MCU cap nhat (1 s) */
    struct mcu_bench_run live;  /* lan chay dang dien ra, chua co percentile */
    struct mcu_bench_run last;  /* lan chay hoan tat gan nhat */
};

/* MCU (rv32 ilp32) va Linux (ARM EABI) phai thay cung mot layout */
_Static_assert(sizeof(struct mcu_bench_run) == 88, "mcu_bench_run layout");
_Static_assert(sizeof(struct mcu_bench_shared) == 224, "mcu_bench_shared layout");

#endif
