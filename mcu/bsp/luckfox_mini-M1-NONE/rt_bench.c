/**
  * Benchmark vong lap realtime 1 kHz tren HPMCU.
  *
  * Nguon nhip: hard timer RT-Thread chu ky 1 tick (RT_TICK_PER_SECOND = 1000), callback chay
  * trong ngat tick (mtime, drivers/timer.c), ghi thoi diem roi release semaphore. Thread uu tien
  * cao nhat cua ung dung cho semaphore, do:
  *   - chu ky: khoang cach giua hai lan thread thuc day
  *   - do tre: tu callback trong ngat toi luc thread chay
  *
  * Moi lan chay gom BENCH_RUN_LENGTH vong. Ket qua (co percentile tu histogram) ghi vao
  * struct mcu_bench_shared tai MCU_BENCH_BASE va in ra log. Sau do bat dau lan chay moi,
  * nen chay lau (1 h, 6 h, 24 h) cho ra chuoi ket qua lien tiep.
  */

#include <rtthread.h>
#include <rthw.h>
#include <string.h>
#include "hal_base.h"
#include "riscv_csr_encoding.h"
#include "timer.h"
#include "mcu_layout.h"
#include "mcu_bench_shared.h"

#define BENCH_RUN_LENGTH    1000000u
#define BENCH_PERIOD_TICKS  1
#define BENCH_STACK_SIZE    1024
#define BENCH_PRIORITY      1
#define REPORT_STACK_SIZE   2048
#define REPORT_PRIORITY     20
#define REPORT_PERIOD_MS    1000
#define REPORT_PRINT_EVERY  10          /* dong trang thai moi 10 s */

#define PERIOD_BIN_NS       250u        /* histogram chu ky: 0 - 2.5 ms */
#define PERIOD_BINS         10000u
#define LAT_BIN_NS          100u        /* histogram do tre: 0 - 100 us */
#define LAT_BINS            1000u

#define NS_SHIFT            24

struct bench_acc
{
    uint64_t n;
    uint64_t missed;
    uint64_t overruns;
    uint64_t period_sum;
    uint64_t lat_n;
    uint64_t lat_sum;
    uint32_t period_min;
    uint32_t period_max;
    uint32_t jitter_max;
    uint32_t lat_min;
    uint32_t lat_max;
    uint32_t overflow;
    uint32_t period_hist[PERIOD_BINS];
    uint32_t lat_hist[LAT_BINS];
};

static struct bench_acc s_acc[2];
static volatile int s_active;
static volatile int s_done = -1;        /* chi so buffer vua xong, cho thread bao cao */

static struct rt_semaphore s_tick_sem;
static struct rt_timer s_tick_timer;
static volatile uint64_t s_isr_stamp;

static uint32_t s_clk_src;
static uint32_t s_clk_hz;
static uint64_t s_ns_mult;              /* ns = counts * s_ns_mult >> NS_SHIFT */
static uint64_t s_counts_limit;         /* tren muc nay phep nhan tran 64 bit */
static uint32_t s_target_ns;

static struct mcu_bench_shared *const s_shared =
    (struct mcu_bench_shared *)MCU_BENCH_BASE;

static inline uint64_t mcycle_read(void)
{
    uint32_t hi, lo, hi2;

    do
    {
        hi = read_csr(mcycleh);
        lo = read_csr(mcycle);
        hi2 = read_csr(mcycleh);
    }
    while (hi != hi2);

    return ((uint64_t)hi << 32) | lo;
}

static inline uint64_t mtime_read(void)
{
    volatile uint32_t *lo_reg = (volatile uint32_t *)(CTIMER_BASE + CTIMER_MTIME);
    volatile uint32_t *hi_reg = (volatile uint32_t *)(CTIMER_BASE + CTIMER_MTIMEH);
    uint32_t hi, lo, hi2;

    do
    {
        hi = *hi_reg;
        lo = *lo_reg;
        hi2 = *hi_reg;
    }
    while (hi != hi2);

    return ((uint64_t)hi << 32) | lo;
}

static inline uint64_t counter_now(void)
{
    return s_clk_src == MCU_CLK_SRC_MCYCLE ? mcycle_read() : mtime_read();
}

static inline uint32_t counts_to_ns(uint64_t counts)
{
    uint64_t ns;

    if (counts > s_counts_limit)
        return UINT32_MAX;

    ns = (counts * s_ns_mult) >> NS_SHIFT;
    return ns > UINT32_MAX ? UINT32_MAX : (uint32_t)ns;
}

/*
 * mcycle cho do phan giai ~3.4 ns; mtime chi ~3.4 us (bo chia SCR1_SYS_TIMER_DIV).
 * SCR1 co the tat bo dem chu ky, khi do mcycle dung yen va ta lui ve mtime.
 */
static void clock_select(void)
{
    uint64_t a, b;
    volatile int i;

    rt_kprintf("bench: probing mcycle\n");
    a = mcycle_read();
    for (i = 0; i < 100; i++)
        ;
    b = mcycle_read();

    if (b != a)
    {
        s_clk_src = MCU_CLK_SRC_MCYCLE;
        s_clk_hz = SCR1_CORE_FREQUECY;
    }
    else
    {
        s_clk_src = MCU_CLK_SRC_MTIME;
        s_clk_hz = SCR1_CORE_FREQUECY / SCR1_SYS_TIMER_DIV;
    }

    s_ns_mult = (1000000000ull << NS_SHIFT) / s_clk_hz;
    s_counts_limit = UINT64_MAX / s_ns_mult;
    s_target_ns = 1000000000u / RT_TICK_PER_SECOND * BENCH_PERIOD_TICKS;

    rt_kprintf("bench: clock %s %u Hz, target %u ns\n",
               s_clk_src == MCU_CLK_SRC_MCYCLE ? "mcycle" : "mtime",
               s_clk_hz, s_target_ns);
}

static void acc_reset(struct bench_acc *acc)
{
    memset(acc, 0, sizeof(*acc));
    acc->period_min = UINT32_MAX;
    acc->lat_min = UINT32_MAX;
}

static void tick_cb(void *parameter)
{
    s_isr_stamp = counter_now();
    rt_sem_release(&s_tick_sem);
}

static void bench_thread_entry(void *parameter)
{
    struct bench_acc *acc = &s_acc[s_active];
    uint64_t prev = 0;
    int have_prev = 0;

    while (1)
    {
        uint64_t now, stamp;
        uint32_t period, lat, dev;
        rt_base_t level;

        rt_sem_take(&s_tick_sem, RT_WAITING_FOREVER);

        /* doc stamp truoc now, va doc tron 64 bit, de tick ke tiep khong lam do tre am */
        level = rt_hw_interrupt_disable();
        stamp = s_isr_stamp;
        rt_hw_interrupt_enable(level);
        now = counter_now();

        /* con token nghia la da co them tick trong luc thread chua chay */
        if (s_tick_sem.value > 0)
            acc->overruns++;

        lat = counts_to_ns(now - stamp);
        acc->lat_n++;
        acc->lat_sum += lat;
        if (lat < acc->lat_min)
            acc->lat_min = lat;
        if (lat > acc->lat_max)
            acc->lat_max = lat;
        if (lat / LAT_BIN_NS < LAT_BINS)
            acc->lat_hist[lat / LAT_BIN_NS]++;
        else
            acc->overflow++;

        if (have_prev)
        {
            period = counts_to_ns(now - prev);
            dev = period > s_target_ns ? period - s_target_ns : s_target_ns - period;

            acc->n++;
            acc->period_sum += period;
            if (period < acc->period_min)
                acc->period_min = period;
            if (period > acc->period_max)
                acc->period_max = period;
            if (dev > acc->jitter_max)
                acc->jitter_max = dev;
            if (period > s_target_ns + s_target_ns / 2)
                acc->missed++;
            if (period / PERIOD_BIN_NS < PERIOD_BINS)
                acc->period_hist[period / PERIOD_BIN_NS]++;
            else
                acc->overflow++;

            /* buffer kia da duoc thread bao cao xoa khi s_done tro ve -1 */
            if (acc->n >= BENCH_RUN_LENGTH && s_done < 0)
            {
                s_done = s_active;
                s_active ^= 1;
                acc = &s_acc[s_active];
            }
        }

        prev = now;
        have_prev = 1;
    }
}

static uint32_t hist_percentile(const uint32_t *hist, uint32_t bins, uint32_t bin_ns,
                                uint64_t n, uint32_t max_ns, uint32_t ppm)
{
    uint64_t target = (n * ppm + 999999u) / 1000000u;
    uint64_t cum = 0;
    uint32_t i;

    for (i = 0; i < bins; i++)
    {
        cum += hist[i];
        if (cum >= target)
            return (i + 1) * bin_ns;   /* chan tren cua o */
    }

    return max_ns;
}

/* Chep so lieu vo huong; histogram chi doc khi lan chay da xong */
static void acc_scalars(const struct bench_acc *acc, struct mcu_bench_run *run)
{
    rt_base_t level = rt_hw_interrupt_disable();

    run->iterations = acc->n;
    run->missed = acc->missed;
    run->overruns = acc->overruns;
    run->period_min = acc->n ? acc->period_min : 0;
    run->period_max = acc->period_max;
    run->period_avg = acc->n ? (uint32_t)(acc->period_sum / acc->n) : 0;
    run->jitter_max = acc->jitter_max;
    run->latency_min = acc->lat_min == UINT32_MAX ? 0 : acc->lat_min;
    run->latency_max = acc->lat_max;
    run->latency_avg = acc->lat_n ? (uint32_t)(acc->lat_sum / acc->lat_n) : 0;
    run->hist_overflow = acc->overflow;

    rt_hw_interrupt_enable(level);
}

static void acc_percentiles(const struct bench_acc *acc, struct mcu_bench_run *run)
{
    uint64_t n = acc->n;
    uint64_t nl = acc->lat_n;

    run->period_p50 = hist_percentile(acc->period_hist, PERIOD_BINS, PERIOD_BIN_NS, n, acc->period_max, 500000);
    run->period_p95 = hist_percentile(acc->period_hist, PERIOD_BINS, PERIOD_BIN_NS, n, acc->period_max, 950000);
    run->period_p99 = hist_percentile(acc->period_hist, PERIOD_BINS, PERIOD_BIN_NS, n, acc->period_max, 990000);
    run->period_p999 = hist_percentile(acc->period_hist, PERIOD_BINS, PERIOD_BIN_NS, n, acc->period_max, 999000);
    run->period_p9999 = hist_percentile(acc->period_hist, PERIOD_BINS, PERIOD_BIN_NS, n, acc->period_max, 999900);
    run->latency_p99 = hist_percentile(acc->lat_hist, LAT_BINS, LAT_BIN_NS, nl, acc->lat_max, 990000);
    run->latency_p9999 = hist_percentile(acc->lat_hist, LAT_BINS, LAT_BIN_NS, nl, acc->lat_max, 999900);
}

static void dcache_clean(uint32_t addr, uint32_t size)
{
#ifdef HAL_DCACHE_MODULE_ENABLED
    HAL_DCACHE_CleanByRange(addr, size);
#endif
}

static void shared_begin(void)
{
    s_shared->seq++;
    dcache_clean((uint32_t)&s_shared->seq, sizeof(s_shared->seq));
}

static void shared_end(void)
{
    dcache_clean((uint32_t)s_shared, sizeof(*s_shared));
    s_shared->seq++;
    dcache_clean((uint32_t)&s_shared->seq, sizeof(s_shared->seq));
}

static void print_run(const char *tag, const struct mcu_bench_run *r)
{
    rt_kprintf("%s n=%u missed=%u overrun=%u period ns min=%u avg=%u max=%u jitter=%u\n",
               tag, (uint32_t)r->iterations, (uint32_t)r->missed, (uint32_t)r->overruns,
               r->period_min, r->period_avg, r->period_max, r->jitter_max);
}

static void report_thread_entry(void *parameter)
{
    struct mcu_bench_run live;
    unsigned int secs = 0;

    while (1)
    {
        rt_thread_mdelay(REPORT_PERIOD_MS);
        secs++;

        acc_scalars(&s_acc[s_active], &live);

        if (s_done >= 0)
        {
            struct bench_acc *done = &s_acc[s_done];
            struct mcu_bench_run last;

            memset(&last, 0, sizeof(last));
            acc_scalars(done, &last);
            acc_percentiles(done, &last);

            shared_begin();
            s_shared->last = last;
            s_shared->runs_done++;
            shared_end();

            rt_kprintf("bench: run %u done\n", s_shared->runs_done);
            print_run("bench: final", &last);
            rt_kprintf("bench: final period ns p50=%u p95=%u p99=%u p99.9=%u p99.99=%u\n",
                       last.period_p50, last.period_p95, last.period_p99,
                       last.period_p999, last.period_p9999);
            rt_kprintf("bench: final latency ns min=%u avg=%u max=%u p99=%u p99.99=%u overflow=%u\n",
                       last.latency_min, last.latency_avg, last.latency_max,
                       last.latency_p99, last.latency_p9999, last.hist_overflow);

            acc_reset(done);
            s_done = -1;
        }

        shared_begin();
        s_shared->live = live;
        s_shared->now_counts = counter_now();
        s_shared->heartbeat++;
        shared_end();

        dcache_clean(MCU_LOG_BASE, MCU_LOG_SIZE);

        if (secs % REPORT_PRINT_EVERY == 0)
            print_run("bench: live", &live);
    }
}

static int bench_init(void)
{
    rt_thread_t tid;

    clock_select();
    acc_reset(&s_acc[0]);
    acc_reset(&s_acc[1]);

    memset(s_shared, 0, sizeof(*s_shared));
    s_shared->magic = MCU_BENCH_MAGIC;
    s_shared->version = MCU_BENCH_VERSION;
    s_shared->clock_src = s_clk_src;
    s_shared->clock_hz = s_clk_hz;
    s_shared->target_period_ns = s_target_ns;
    s_shared->run_length = BENCH_RUN_LENGTH;
    dcache_clean((uint32_t)s_shared, sizeof(*s_shared));

    rt_sem_init(&s_tick_sem, "b1k", 0, RT_IPC_FLAG_FIFO);

    tid = rt_thread_create("bench", bench_thread_entry, RT_NULL,
                           BENCH_STACK_SIZE, BENCH_PRIORITY, 10);
    if (tid == RT_NULL)
        return -RT_ENOMEM;
    rt_thread_startup(tid);

    tid = rt_thread_create("report", report_thread_entry, RT_NULL,
                           REPORT_STACK_SIZE, REPORT_PRIORITY, 10);
    if (tid == RT_NULL)
        return -RT_ENOMEM;
    rt_thread_startup(tid);

    rt_timer_init(&s_tick_timer, "b1k", tick_cb, RT_NULL, BENCH_PERIOD_TICKS,
                  RT_TIMER_FLAG_PERIODIC | RT_TIMER_FLAG_HARD_TIMER);
    rt_timer_start(&s_tick_timer);

    rt_kprintf("bench: started, run length %u\n", BENCH_RUN_LENGTH);
    return RT_EOK;
}
INIT_APP_EXPORT(bench_init);
