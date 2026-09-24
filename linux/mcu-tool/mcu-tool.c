/*
 * mcu-tool: nap, dung va doc ket qua cua HPMCU tren RV1103 tu Linux qua /dev/mem.
 *
 *   mcu-tool load <rtthread.bin>   giu reset, chep firmware, dat dia chi boot, nha reset
 *   mcu-tool stop                  giu MCU o trang thai reset
 *   mcu-tool status                ket qua benchmark (struct mcu_bench_shared)
 *   mcu-tool log                   vong dem log cua MCU (drv_pstore.c)
 *   mcu-tool clock [giay]          do tan so bo dem cua MCU theo dong ho Linux
 *
 * Trinh tu nap chep dung spl_fit_standalone_release() cua U-Boot
 * (sysdrv/source/uboot/u-boot/arch/arm/mach-rockchip/rv1106/rv1106.c:548-566).
 * Chi ghi vao vung DDR khi device tree co node reserved-memory dung dia chi va kich thuoc.
 */

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "mcu_layout.h"
#include "mcu_bench_shared.h"

/* rv1106.c:23-26, 39, 46, 109-110 */
#define CORE_GRF_BASE                   0xff040000u
#define CORE_GRF_CACHE_PERI_ADDR_START  0x0024u
#define CORE_GRF_CACHE_PERI_ADDR_END    0x0028u
#define CORE_SGRF_BASE                  0xff076000u
#define CORE_SGRF_HPMCU_BOOT_ADDR       0x0044u
#define CORECRU_BASE                    0xff3b8000u
#define CORECRU_CORESOFTRST_CON01       0x0a04u

/* rv1106.c:552-559 */
#define PERI_UNCACHE_START              0xff000u
#define PERI_UNCACHE_END                0xffc00u
#define MCU_RESET_ASSERT                0x001e001eu
#define MCU_RESET_RELEASE               0x001e0000u

/* drv_pstore.c:33-42 */
#define PSTORE_SIG                      0x43474244u
struct pstore_hdr {
    uint32_t sig;
    uint32_t start;
    uint32_t size;
};

#define DT_NODE "/proc/device-tree/reserved-memory/mcu@1800000/reg"

static int g_mem_fd = -1;

static void die(const char *msg)
{
    fprintf(stderr, "mcu-tool: %s%s%s\n", msg, errno ? ": " : "", errno ? strerror(errno) : "");
    exit(1);
}

static volatile void *map_phys(uint32_t phys, uint32_t size)
{
    long page = sysconf(_SC_PAGESIZE);
    uint32_t base = phys & ~(uint32_t)(page - 1);
    uint32_t off = phys - base;
    void *p;

    if (g_mem_fd < 0) {
        g_mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
        if (g_mem_fd < 0)
            die("open /dev/mem");
    }

    p = mmap(NULL, size + off, PROT_READ | PROT_WRITE, MAP_SHARED, g_mem_fd, base);
    if (p == MAP_FAILED)
        die("mmap /dev/mem");

    return (volatile uint8_t *)p + off;
}

static void reg_write(uint32_t base, uint32_t off, uint32_t val)
{
    volatile uint32_t *r = map_phys(base + off, 4);

    *r = val;
}

static uint32_t reg_read(uint32_t base, uint32_t off)
{
    volatile uint32_t *r = map_phys(base + off, 4);

    return *r;
}

static uint32_t be32(const uint8_t *p)
{
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

/* Tu choi ghi DDR neu Linux chua danh rieng dung vung nay */
static void check_reserved(void)
{
    uint8_t reg[8];
    FILE *f = fopen(DT_NODE, "rb");

    if (!f || fread(reg, 1, sizeof(reg), f) != sizeof(reg))
        die("thieu reserved-memory mcu@1800000 trong device tree, khong ghi DDR");
    fclose(f);

    if (be32(reg) != MCU_REGION_BASE || be32(reg + 4) != MCU_REGION_SIZE) {
        errno = 0;
        fprintf(stderr, "device tree: 0x%08x + 0x%x, mong doi 0x%08x + 0x%x\n",
                be32(reg), be32(reg + 4), MCU_REGION_BASE, MCU_REGION_SIZE);
        die("reserved-memory khong khop mcu_layout.h");
    }
}

static void cmd_stop(void)
{
    reg_write(CORECRU_BASE, CORECRU_CORESOFTRST_CON01, MCU_RESET_ASSERT);
    printf("MCU dang giu reset\n");
}

static void cmd_load(const char *path)
{
    struct stat st;
    volatile uint8_t *code, *tail;
    uint8_t *buf;
    uint32_t boot;
    FILE *f;
    size_t i;

    check_reserved();

    f = fopen(path, "rb");
    if (!f || fstat(fileno(f), &st) != 0)
        die("mo firmware");
    if (st.st_size <= 0 || (uint32_t)st.st_size > MCU_CODE_SIZE) {
        errno = 0;
        die("firmware rong hoac lon hon MCU_CODE_SIZE");
    }
    buf = malloc(st.st_size);
    if (!buf || fread(buf, 1, st.st_size, f) != (size_t)st.st_size)
        die("doc firmware");
    fclose(f);

    reg_write(CORECRU_BASE, CORECRU_CORESOFTRST_CON01, MCU_RESET_ASSERT);

    code = map_phys(MCU_CODE_BASE, MCU_REGION_SIZE);
    for (i = 0; i < (size_t)st.st_size; i++)
        code[i] = buf[i];
    for (i = 0; i < (size_t)st.st_size; i++) {
        if (code[i] != buf[i]) {
            errno = 0;
            fprintf(stderr, "sai lech tai offset 0x%zx\n", i);
            die("doc lai firmware khong khop");
        }
    }
    /* xoa log va vung benchmark de khong doc nham so lieu cua lan truoc */
    tail = code + (MCU_LOG_BASE - MCU_REGION_BASE);
    for (i = 0; i < MCU_LOG_SIZE + MCU_BENCH_SIZE; i++)
        tail[i] = 0;
    free(buf);

    reg_write(CORE_GRF_BASE, CORE_GRF_CACHE_PERI_ADDR_START, PERI_UNCACHE_START);
    reg_write(CORE_GRF_BASE, CORE_GRF_CACHE_PERI_ADDR_END, PERI_UNCACHE_END);
    reg_write(CORE_SGRF_BASE, CORE_SGRF_HPMCU_BOOT_ADDR, MCU_CODE_BASE);

    boot = reg_read(CORE_SGRF_BASE, CORE_SGRF_HPMCU_BOOT_ADDR);
    if (boot != MCU_CODE_BASE) {
        errno = 0;
        fprintf(stderr, "HPMCU_BOOT_ADDR doc lai 0x%08x, mong doi 0x%08x\n", boot, MCU_CODE_BASE);
        die("khong ghi duoc thanh ghi SGRF tu Linux; MCU van giu reset");
    }

    reg_write(CORECRU_BASE, CORECRU_CORESOFTRST_CON01, MCU_RESET_RELEASE);
    printf("da nap %lld byte vao 0x%08x, boot addr 0x%08x, da nha reset\n",
           (long long)st.st_size, MCU_CODE_BASE, boot);
}

/* Doc nhat quan theo seq (mcu_bench_shared.h) */
static int read_shared(struct mcu_bench_shared *out)
{
    volatile struct mcu_bench_shared *s = map_phys(MCU_BENCH_BASE, sizeof(*s));
    int tries;

    for (tries = 0; tries < 1000; tries++) {
        uint32_t seq1 = s->seq;

        if (seq1 & 1) {
            usleep(100);
            continue;
        }
        memcpy(out, (const void *)s, sizeof(*out));
        if (s->seq == seq1)
            return out->magic == MCU_BENCH_MAGIC && out->version == MCU_BENCH_VERSION ? 0 : -1;
    }
    return -1;
}

static void print_run(const char *title, const struct mcu_bench_run *r, int with_pct)
{
    printf("%s\n", title);
    printf("  iterations      %" PRIu64 "\n", r->iterations);
    printf("  missed          %" PRIu64 "   (chu ky > 1.5 x target)\n", r->missed);
    printf("  overruns        %" PRIu64 "   (lo tick)\n", r->overruns);
    printf("  period ns       min %u  avg %u  max %u\n", r->period_min, r->period_avg, r->period_max);
    printf("  jitter max ns   %u\n", r->jitter_max);
    if (with_pct) {
        printf("  period pct ns   P50 %u  P95 %u  P99 %u  P99.9 %u  P99.99 %u\n",
               r->period_p50, r->period_p95, r->period_p99, r->period_p999, r->period_p9999);
        printf("  latency ns      min %u  avg %u  max %u  P99 %u  P99.99 %u\n",
               r->latency_min, r->latency_avg, r->latency_max, r->latency_p99, r->latency_p9999);
        printf("  hist overflow   %u\n", r->hist_overflow);
    } else {
        printf("  latency ns      min %u  avg %u  max %u\n",
               r->latency_min, r->latency_avg, r->latency_max);
    }
}

static void cmd_status(void)
{
    struct mcu_bench_shared s;

    if (read_shared(&s) != 0) {
        errno = 0;
        die("chua co du lieu benchmark (MCU chua chay hoac sai magic)");
    }

    printf("clock           %s, %u Hz danh nghia\n",
           s.clock_src == MCU_CLK_SRC_MCYCLE ? "mcycle" : "mtime", s.clock_hz);
    printf("target period   %u ns, %u vong moi lan chay\n", s.target_period_ns, s.run_length);
    printf("heartbeat       %" PRIu64 "\n", s.heartbeat);
    printf("runs done       %u\n", s.runs_done);
    print_run("live (lan chay hien tai):", &s.live, 0);
    if (s.runs_done)
        print_run("last (lan chay hoan tat gan nhat):", &s.last, 1);
}

static void cmd_log(void)
{
    volatile struct pstore_hdr *h = map_phys(MCU_LOG_BASE, MCU_LOG_SIZE);
    volatile uint8_t *data = (volatile uint8_t *)(h + 1);
    uint32_t cap = MCU_LOG_SIZE - sizeof(*h);
    uint32_t start = h->start, size = h->size, i, first;

    if (h->sig != PSTORE_SIG || start >= cap || size > cap) {
        errno = 0;
        die("vong dem log chua khoi tao");
    }

    first = size < cap ? 0 : start;
    for (i = 0; i < size; i++) {
        uint8_t c = data[(first + i) % cap];

        if (c != '\r')
            putchar(c);
    }
}

static double now_s(void)
{
    struct timespec ts;

    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

/* Cho heartbeat doi (MCU cap nhat now_counts moi giay), ghi lai thoi diem Linux */
static void sample_edge(uint64_t *counts, double *t)
{
    struct mcu_bench_shared s;
    uint64_t hb;

    if (read_shared(&s) != 0) {
        errno = 0;
        die("chua co du lieu benchmark");
    }
    hb = s.heartbeat;
    do {
        usleep(200);
        if (read_shared(&s) != 0)
            continue;
    } while (s.heartbeat == hb);

    *t = now_s();
    *counts = s.now_counts;
}

static void cmd_clock(int secs)
{
    uint64_t c1, c2;
    double t1, t2, hz;
    struct mcu_bench_shared s;

    sample_edge(&c1, &t1);
    sleep(secs > 1 ? secs - 1 : 1);
    sample_edge(&c2, &t2);
    read_shared(&s);

    hz = (double)(c2 - c1) / (t2 - t1);
    printf("bo dem MCU      %.0f Hz do duoc trong %.1f s (danh nghia %u, lech %+.3f%%)\n",
           hz, t2 - t1, s.clock_hz, (hz / s.clock_hz - 1.0) * 100.0);
    printf("sai so do       ~0.2 ms / %.1f s do buoc thuc day 200 us\n", t2 - t1);
}

int main(int argc, char **argv)
{
    if (argc >= 3 && !strcmp(argv[1], "load"))
        cmd_load(argv[2]);
    else if (argc >= 2 && !strcmp(argv[1], "stop"))
        cmd_stop();
    else if (argc >= 2 && !strcmp(argv[1], "status"))
        cmd_status();
    else if (argc >= 2 && !strcmp(argv[1], "log"))
        cmd_log();
    else if (argc >= 2 && !strcmp(argv[1], "clock"))
        cmd_clock(argc >= 3 ? atoi(argv[2]) : 10);
    else {
        fprintf(stderr, "dung: mcu-tool load <rtthread.bin> | stop | status | log | clock [giay]\n");
        return 2;
    }
    return 0;
}
