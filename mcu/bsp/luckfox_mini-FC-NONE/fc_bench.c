/**
  * The flight core on the HPMCU, closed loop with a simulated quad ("MCU simulation",
  * plan section 29, step 2).  No sensor and no motor is touched.
  *
  * Every 1 ms tick (hard timer, as rt_bench.c in Milestone 1):
  *   pilot script -> CRSF frame (250 Hz) -> crsf_parser -> rc_map  -> fc_rc_input
  *   quad model   -> SIM_SENSOR                                     -> fc_tick()  <- timed
  *   fc_tick motors -> quad_step (1 ms)                                            <- timed
  *
  * fc_tick() is the exact call a REAL_SENSOR build will make, so its cycle count is the
  * number that decides whether this rv32imc core (no FPU, soft float) can fly at 1 kHz.
  * Results go to the RAM log every 5 s: tools/mcu-tool log.
  */

#include <rtthread.h>
#include <rthw.h>
#include <string.h>
#include "hal_base.h"
#include "riscv_csr_encoding.h"
#include "tree/mcu/fc/fc.h"
#include "tree/simulator/quad_model.h"
#include "tree/simulator/sim_sensors.h"
#include "tree/shared/rc/crsf.h"
#include "tree/shared/rc/rc_map.h"

#define FC_STACK_SIZE       4096
#define FC_PRIORITY         1
#define REPORT_STACK_SIZE   2048
#define REPORT_PRIORITY     20
#define REPORT_PERIOD_MS    5000
#define HIST_BIN_US         5u          /* cycle histogram: 0 - 5 ms in 5 us bins */
#define HIST_BINS           1000u
#define CPU_HZ              297000000u  /* clk_core_mcu, TEST in Milestone 1 */

static fc_t s_fc;
static fc_params s_fcp;
static quad_model s_quad;
static sim_sensors s_sens;
static sensor_source s_src;
static crsf_parser s_crsf;
static rc_map_params s_map;

struct cyc_stat {
    uint32_t n, min, max, hist[HIST_BINS], over;
    uint64_t sum;
};
static struct cyc_stat s_fc_cyc, s_phys_cyc;
static volatile uint32_t s_ticks, s_done, s_overruns;
static volatile int s_mcycle_ok;

static struct rt_semaphore s_tick_sem;
static struct rt_timer s_tick_timer;

static inline uint64_t mcycle_read(void)
{
    uint32_t hi, lo, hi2;
    do {
        hi = read_csr(mcycleh);
        lo = read_csr(mcycle);
        hi2 = read_csr(mcycleh);
    } while (hi != hi2);
    return ((uint64_t)hi << 32) | lo;
}

static void stat_add(struct cyc_stat *s, uint32_t cyc)
{
    uint32_t us = cyc / (CPU_HZ / 1000000u);
    uint32_t bin = us / HIST_BIN_US;
    if (bin >= HIST_BINS) {
        bin = HIST_BINS - 1;
        s->over++;
    }
    s->hist[bin]++;
    if (s->n == 0 || cyc < s->min)
        s->min = cyc;
    if (cyc > s->max)
        s->max = cyc;
    s->sum += cyc;
    s->n++;
}

static uint32_t stat_pct_us(const struct cyc_stat *s, uint32_t per_mille)
{
    uint64_t want = ((uint64_t)s->n * per_mille + 999) / 1000, acc = 0;
    for (uint32_t i = 0; i < HIST_BINS; i++) {
        acc += s->hist[i];
        if (acc >= want)
            return (i + 1) * HIST_BIN_US;
    }
    return HIST_BINS * HIST_BIN_US;
}

static uint32_t cyc_us(uint64_t c) { return (uint32_t)(c / (CPU_HZ / 1000000u)); }

/* ---- the pilot: calibrate, arm, climb, hold height, rock left and right ---- */
static float s_thr, s_roll;
static int s_arm, s_mode = 1;           /* 1 = ANGLE (flight_mode) */

static void pilot(float t)
{
    if (t < 2.0f) {
        s_arm = 0;
        s_thr = 0.0f;
    } else if (t < 2.2f) {
        s_arm = 1;
    } else if (s_mode != 2) {
        s_thr = 0.65f;
        if (-s_quad.pos.z > 2.0f) {
            s_mode = 2;                 /* ALT_HOLD */
            s_thr = 0.5f;
        }
    } else {
        int phase = (int)(t / 2.0f) % 4;
        s_roll = phase == 1 ? 0.4f : (phase == 3 ? -0.4f : 0.0f);
    }
}

static int rc_from_crsf(fc_rc_input *rc)
{
    static const int MODE_US[3] = {2000, 1000, 1500};     /* flight_mode -> switch */
    uint16_t ch[CRSF_CHANNELS];
    uint8_t frame[CRSF_RC_FRAME_LEN];
    for (int i = 0; i < CRSF_CHANNELS; i++)
        ch[i] = CRSF_TICK_MID;
    ch[s_map.ch_roll] = crsf_us_to_ticks(1500 + (int)(500.0f * s_roll));
    ch[s_map.ch_throttle] = crsf_us_to_ticks(1000 + (int)(1000.0f * s_thr));
    ch[s_map.ch_arm] = crsf_us_to_ticks(s_arm ? 2000 : 1000);
    ch[s_map.ch_mode] = crsf_us_to_ticks(MODE_US[s_mode]);
    crsf_pack_channels(ch, frame);
    int got = 0;
    for (int i = 0; i < CRSF_RC_FRAME_LEN; i++)
        if (crsf_feed(&s_crsf, frame[i]) == CRSF_GOT_CHANNELS)
            got = 1;
    if (!got)
        return 0;
    rc_command c;
    rc_map_apply(&s_map, s_crsf.channels, &c);
    rc->valid = 1;
    rc->sticks.roll = c.roll;
    rc->sticks.pitch = c.pitch;
    rc->sticks.yaw = c.yaw;
    rc->sticks.throttle = c.throttle;
    rc->sticks.mode = (flight_mode)c.mode;
    rc->arm_switch = c.arm_switch;
    return 1;
}

static void tick_cb(void *parameter)
{
    s_ticks++;
    rt_sem_release(&s_tick_sem);
}

static void fc_thread_entry(void *parameter)
{
    float motor[4];
    uint32_t k = 0;
    while (1) {
        rt_sem_take(&s_tick_sem, RT_WAITING_FOREVER);
        if (s_tick_sem.value > 0)
            s_overruns++;               /* a tick arrived while we were still busy */
        float t = (float)k * 0.001f;
        if (k == 0)
            fc_request_acc_calibration(&s_fc);
        pilot(t);
        fc_rc_input rc;
        memset(&rc, 0, sizeof(rc));
        int fresh = (k % 4 == 0) && rc_from_crsf(&rc);
        sim_sensors_sample(&s_sens, k * 1000u, 0.001f);

        uint64_t c0 = mcycle_read();
        fc_tick(&s_fc, &s_src, fresh ? &rc : NULL, motor);
        uint64_t c1 = mcycle_read();
        quad_step(&s_quad, motor, v3(0.0f, 0.0f, 0.0f), 0.001f);
        uint64_t c2 = mcycle_read();

        stat_add(&s_fc_cyc, (uint32_t)(c1 - c0));
        stat_add(&s_phys_cyc, (uint32_t)(c2 - c1));
        k++;
        s_done = k;
    }
}

static void report_thread_entry(void *parameter)
{
    uint32_t last_done = 0;
    while (1) {
        rt_thread_mdelay(REPORT_PERIOD_MS);
        /* read in place: a copy of the 4 KB histograms would overflow this stack;
         * the fc thread may update them meanwhile, which only blurs one sample */
        const struct cyc_stat *const pf = &s_fc_cyc, *const pp = &s_phys_cyc;
        uint32_t done = s_done, ticks = s_ticks;
        vec3 e = q_to_euler(s_quad.q);
        int h_cm = (int)(-s_quad.pos.z * 100.0f);
        int roll_d10 = (int)(e.x * FC_RAD2DEG * 10.0f);
        int est_d10 = (int)(s_fc.att.euler.x * FC_RAD2DEG * 10.0f);
        /* RT_CONSOLEBUF_SIZE is 128 (defconfig): keep every line shorter */
        rt_kprintf("fc: t=%us loops=%u (+%u) ticks=%u overruns=%u\n",
                   done / 1000, done, done - last_done, ticks, s_overruns);
        rt_kprintf("fc: %s crashed=%d h=%dcm roll=%d.%d est=%d.%d deg\n",
                   fc_state_name(s_fc.state), s_quad.crashed, h_cm, roll_d10 / 10,
                   (roll_d10 < 0 ? -roll_d10 : roll_d10) % 10, est_d10 / 10,
                   (est_d10 < 0 ? -est_d10 : est_d10) % 10);
        uint32_t fn = pf->n, pn = pp->n;
        if (fn && pn) {
            rt_kprintf("fc: fc_tick us min=%u avg=%u p50<=%u p99<=%u p999<=%u max=%u\n",
                       cyc_us(pf->min), cyc_us(pf->sum / fn), stat_pct_us(pf, 500),
                       stat_pct_us(pf, 990), stat_pct_us(pf, 999), cyc_us(pf->max));
            rt_kprintf("fc: quad_step us avg=%u max=%u (budget 1000 us/tick)\n",
                       cyc_us(pp->sum / pn), cyc_us(pp->max));
        }
        last_done = done;
    }
}

static int fc_bench_init(void)
{
    /* mcycle must count, or every number below is meaningless */
    uint64_t a = mcycle_read();
    for (volatile int i = 0; i < 1000; i++)
        ;
    uint64_t b = mcycle_read();
    s_mcycle_ok = b != a;
    rt_kprintf("fc: mcycle %s (%u cycles for an empty 1000 loop)\n",
               s_mcycle_ok ? "counts" : "STOPPED - timings invalid", (uint32_t)(b - a));

    quad_params qp;
    quad_default_params(&qp);
    quad_init(&s_quad, &qp);
    sim_sensor_params sp;
    sim_sensor_default_params(&sp, 1);
    sim_sensors_init(&s_sens, &sp, &s_quad, 12345u);
    s_src = sim_sensors_source(&s_sens);
    fc_default_params(&s_fcp);
    fc_init(&s_fc, &s_fcp);
    crsf_parser_init(&s_crsf);
    rc_map_default(&s_map);
    rt_kprintf("fc: flight core %u B state, sensor %s\n", (uint32_t)sizeof(s_fc), s_src.name);

    rt_sem_init(&s_tick_sem, "fct", 0, RT_IPC_FLAG_FIFO);
    rt_thread_t tid = rt_thread_create("fc", fc_thread_entry, RT_NULL, FC_STACK_SIZE,
                                       FC_PRIORITY, 10);
    if (tid == RT_NULL)
        return -RT_ENOMEM;
    rt_thread_startup(tid);
    tid = rt_thread_create("fcrep", report_thread_entry, RT_NULL, REPORT_STACK_SIZE,
                           REPORT_PRIORITY, 10);
    if (tid == RT_NULL)
        return -RT_ENOMEM;
    rt_thread_startup(tid);
    rt_timer_init(&s_tick_timer, "fc1k", tick_cb, RT_NULL, 1,
                  RT_TIMER_FLAG_PERIODIC | RT_TIMER_FLAG_HARD_TIMER);
    rt_timer_start(&s_tick_timer);
    return RT_EOK;
}
INIT_APP_EXPORT(fc_bench_init);
