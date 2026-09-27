/*
 * Closed-loop scenarios against the simulator, each with a pass criterion.
 *
 *   build/sim_cli                   run every scenario
 *   build/sim_cli hover rc_loss     run some
 *   build/sim_cli --csv log.csv hover   also write a 100 Hz log of the last one
 *   build/sim_cli --vib ...         add the ASSUMED frame vibration
 *   build/sim_cli --bench           time fc_step on this host
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "sim.h"

static FILE *csv;
static int vibration;
static int verbose;

typedef struct {
    sim_t s;
    float thr, roll, pitch, yaw;
    int arm, mode;
} run;

static void pilot(run *r)
{
    sim_set_pilot(&r->s, r->roll, r->pitch, r->yaw, r->thr, r->arm, r->mode);
}

static void advance(run *r, float seconds)
{
    int n = (int)(seconds * 1000.0f + 0.5f);
    for (int i = 0; i < n; i++) {
        pilot(r);
        sim_step(&r->s, 1);
        if (csv && (r->s.fc.ticks % 10) == 0) {
            float v[80];
            int k = sim_get_state(&r->s, v, 80);
            for (int j = 0; j < k; j++)
                fprintf(csv, j ? ",%.5g" : "%.5g", (double)v[j]);
            fputc('\n', csv);
        }
    }
}

static void start(run *r, uint32_t seed)
{
    memset(r, 0, sizeof(*r));
    sim_init(&r->s, seed, !vibration);
    if (csv) {
        rewind(csv);
        fprintf(csv, "%s\n", sim_state_names());
    }
}

static float height(const run *r) { return -r->s.quad.pos.z; }
static float tilt_deg(const run *r) { return acosf(constrainf(q_cos_tilt(r->s.quad.q), -1, 1)) * FC_RAD2DEG; }

/* disarmed on the ground, calibrate, arm in ANGLE, climb, switch to ALT_HOLD */
static int take_off(run *r, float to_height)
{
    r->mode = 0;
    fc_request_acc_calibration(&r->s.fc);   /* the pilot's one-off level calibration */
    advance(r, 1.5f);                 /* gyro calibration needs 1 s still */
    r->arm = 1;
    advance(r, 0.2f);
    if (r->s.fc.state != FC_ARMED) {
        printf("    could not arm (blocks 0x%X)\n", (unsigned)r->s.fc.arm.blocks);
        return 0;
    }
    r->thr = 0.65f;
    for (int i = 0; i < 800 && height(r) < to_height; i++)
        advance(r, 0.01f);
    r->mode = 1;                      /* ALT_HOLD, stick centred = hold */
    r->thr = 0.5f;
    advance(r, 3.0f);
    return height(r) > 0.5f * to_height;
}

#define RESULT(ok, ...) do { printf("  %-12s %s  ", name, (ok) ? "PASS" : "FAIL"); \
    printf(__VA_ARGS__); printf("\n"); return (ok); } while (0)

static int sc_arm_refusal(const char *name)
{
    run r;
    start(&r, 1);
    r.arm = 1;                        /* switch left on at power-up */
    advance(&r, 2.0f);
    int a = r.s.fc.state == FC_DISARMED && (r.s.fc.arm.blocks & ARM_BLOCK_SWITCH_NOT_CYCLED);
    r.arm = 0;
    r.thr = 0.6f;                     /* throttle up */
    advance(&r, 0.1f);
    r.arm = 1;
    advance(&r, 0.1f);
    int b = r.s.fc.state == FC_DISARMED && (r.s.fc.arm.blocks & ARM_BLOCK_THROTTLE);
    float m = r.s.motor[0] + r.s.motor[1] + r.s.motor[2] + r.s.motor[3];
    RESULT(a && b && m == 0.0f, "switch-on-at-boot refused %d, throttle-up refused %d, motors %.2f",
           a, b, (double)m);
}

static int sc_hover(const char *name)
{
    run r;
    start(&r, 2);
    if (!take_off(&r, 2.0f))
        RESULT(0, "take-off failed, h %.2f", (double)height(&r));
    float h0 = r.s.fc.ctl.height_sp, emax = 0.0f, tmax = 0.0f, se = 0.0f;
    int n = 0;
    for (int i = 0; i < 1000; i++) {
        advance(&r, 0.01f);
        float e = fabsf(height(&r) - h0);
        emax = e > emax ? e : emax;
        float t = tilt_deg(&r);
        tmax = t > tmax ? t : tmax;
        vec3 est = r.s.fc.att.euler, tru = q_to_euler(r.s.quad.q);
        float d = (est.x - tru.x) * (est.x - tru.x) + (est.y - tru.y) * (est.y - tru.y);
        se += d;
        n++;
    }
    float att_rms = sqrtf(se / (float)n) * FC_RAD2DEG;
    int ok = emax < 0.3f && tmax < 3.0f && att_rms < 1.0f && !r.s.quad.crashed;
    RESULT(ok, "10 s hold at %.2f m: max height error %.3f m, max tilt %.2f deg, "
               "attitude estimate error %.3f deg rms", (double)h0, (double)emax,
           (double)tmax, (double)att_rms);
}

static int sc_angle_step(const char *name)
{
    run r;
    start(&r, 3);
    if (!take_off(&r, 3.0f))
        RESULT(0, "take-off failed");
    r.roll = 0.6f;
    float sp = 0.0f, peak = 0.0f, t90 = -1.0f;
    for (int i = 0; i < 100; i++) {
        advance(&r, 0.01f);
        sp = r.s.fc.ctl.angle_sp.x * FC_RAD2DEG;
        float roll = q_to_euler(r.s.quad.q).x * FC_RAD2DEG;
        peak = roll > peak ? roll : peak;
        if (t90 < 0.0f && sp > 1.0f && roll >= 0.9f * sp)
            t90 = (float)(i + 1) * 0.01f;
    }
    float settled = q_to_euler(r.s.quad.q).x * FC_RAD2DEG;
    float est = r.s.fc.att.euler.x * FC_RAD2DEG;
    r.roll = 0.0f;
    advance(&r, 1.0f);
    float back = fabsf(q_to_euler(r.s.quad.q).x * FC_RAD2DEG);
    float over = sp > 0.0f ? (peak - sp) / sp * 100.0f : 100.0f;
    /* the controller must hold its estimate on the setpoint (1 deg); the
     * estimate itself may be ~2 deg off while the craft accelerates sideways:
     * without GPS velocity the accelerometer cannot tell tilt from
     * acceleration (known limit, see simulator/README.md) */
    int ok = t90 > 0.0f && t90 < 0.4f && over < 20.0f && fabsf(est - sp) < 1.0f &&
             fabsf(settled - sp) < 3.0f && back < 3.0f;
    RESULT(ok, "roll step to %.1f deg: 90%% in %.2f s, overshoot %.1f %%, after 1 s estimate "
               "%.2f / true %.2f deg, 1 s after release %.2f deg", (double)sp, (double)t90,
           (double)over, (double)est, (double)settled, (double)back);
}

static int sc_yaw(const char *name)
{
    run r;
    start(&r, 4);
    if (!take_off(&r, 2.0f))
        RESULT(0, "take-off failed");
    r.yaw = 0.5f;
    advance(&r, 1.0f);
    float sp = r.s.fc.ctl.rate_sp.z * FC_RAD2DEG, w = r.s.quad.w.z * FC_RAD2DEG;
    r.yaw = 0.0f;
    advance(&r, 1.0f);
    float after = r.s.quad.w.z * FC_RAD2DEG;
    int ok = sp > 0.0f && w > 0.8f * sp && w < 1.2f * sp && fabsf(after) < 5.0f;
    RESULT(ok, "yaw stick +0.5: rate %.1f deg/s for %.1f asked (nose right), %.1f after release",
           (double)w, (double)sp, (double)after);
}

static int sc_rc_loss(const char *name)
{
    run r;
    start(&r, 5);
    if (!take_off(&r, 4.0f))
        RESULT(0, "take-off failed");
    float t_cut = r.s.t, t_hold = -1, t_land = -1, t_dis = -1, tmax = 0;
    sim_set_faults(&r.s, 1, 0);
    for (int i = 0; i < 3000; i++) {
        advance(&r, 0.01f);
        fc_state st = r.s.fc.state;
        if (t_hold < 0 && st == FC_FAILSAFE_HOLD) t_hold = r.s.t - t_cut;
        if (t_land < 0 && st == FC_FAILSAFE_LAND) t_land = r.s.t - t_cut;
        if (st == FC_DISARMED) { t_dis = r.s.t - t_cut; break; }
        float t = tilt_deg(&r);
        tmax = t > tmax ? t : tmax;
    }
    int ok = t_hold > 0 && t_hold < 0.35f && t_land > 1.0f && t_dis > 0 &&
             r.s.fc.arm.last_disarm == DISARM_FAILSAFE_LANDED && !r.s.quad.crashed &&
             r.s.quad.on_ground && tmax < 10.0f;
    RESULT(ok, "link cut at 4 m: hold after %.2f s, land after %.2f s, disarmed %.1f s "
               "(reason %d), on ground %d, crashed %d, max tilt %.1f deg",
           (double)t_hold, (double)t_land, (double)t_dis, r.s.fc.arm.last_disarm,
           r.s.quad.on_ground, r.s.quad.crashed, (double)tmax);
}

static int sc_imu_fail(const char *name)
{
    run r;
    start(&r, 6);
    if (!take_off(&r, 2.0f))
        RESULT(0, "take-off failed");
    float t0 = r.s.t, t_dis = -1;
    sim_set_faults(&r.s, 0, 1);
    for (int i = 0; i < 200; i++) {
        advance(&r, 0.001f);
        if (r.s.fc.state == FC_DISARMED) { t_dis = r.s.t - t0; break; }
    }
    float m = r.s.motor[0] + r.s.motor[1] + r.s.motor[2] + r.s.motor[3];
    int ok = t_dis > 0 && t_dis < 0.03f && m == 0.0f && r.s.fc.arm.last_disarm == DISARM_IMU_LOST;
    RESULT(ok, "IMU dies in flight: motors off after %.1f ms (the craft then falls: "
               "no IMU, nothing to fly with)", (double)(t_dis * 1000.0f));
}

static int sc_wind(const char *name)
{
    run r;
    start(&r, 7);
    if (!take_off(&r, 3.0f))
        RESULT(0, "take-off failed");
    sim_set_wind(&r.s, 4.0f, 2.0f, 2.0f);
    float h0 = r.s.fc.ctl.height_sp, emax = 0, tmax = 0;
    for (int i = 0; i < 1000; i++) {
        advance(&r, 0.01f);
        float e = fabsf(height(&r) - h0), t = tilt_deg(&r);
        emax = e > emax ? e : emax;
        tmax = t > tmax ? t : tmax;
    }
    int ok = emax < 1.0f && tmax < 20.0f && !r.s.quad.crashed && r.s.fc.state == FC_ARMED;
    RESULT(ok, "4.5 m/s wind + 2 m/s rms gusts, 10 s: max height error %.2f m, max tilt %.1f deg "
               "(no position hold: it drifts %.1f m)", (double)emax, (double)tmax,
           (double)sqrtf(r.s.quad.pos.x * r.s.quad.pos.x + r.s.quad.pos.y * r.s.quad.pos.y));
}

static int sc_acro_flip(const char *name)
{
    run r;
    start(&r, 8);
    if (!take_off(&r, 8.0f))
        RESULT(0, "take-off failed");
    r.mode = 2;                       /* ACRO */
    r.thr = 0.55f;
    advance(&r, 0.2f);
    r.roll = 1.0f;
    float wmax = 0.0f;
    for (int i = 0; i < 90; i++) {
        advance(&r, 0.01f);
        float w = r.s.quad.w.x * FC_RAD2DEG;
        wmax = w > wmax ? w : wmax;
    }
    r.roll = 0.0f;
    r.mode = 0;                       /* back to ANGLE: must self-level */
    advance(&r, 2.0f);
    float tilt = tilt_deg(&r);
    vec3 est = r.s.fc.att.euler, tru = q_to_euler(r.s.quad.q);
    float est_err = fabsf(wrap_pi(est.x - tru.x)) * FC_RAD2DEG;
    int ok = r.s.fc.state == FC_ARMED && wmax > 0.8f * 400.0f && tilt < 5.0f && !r.s.quad.crashed
             && est_err < 3.0f;
    RESULT(ok, "full-stick ACRO roll: peak %.0f deg/s (400 asked), level again %.1f deg, "
               "estimate error after the flip %.2f deg, height %.1f m", (double)wmax,
           (double)tilt, (double)est_err, (double)height(&r));
}

static void bench(void)
{
    /* time the ARMED path (estimator + all loops + mixer), on a copy of a
     * flight core that is hovering in ALT_HOLD */
    static run r;
    start(&r, 9);
    take_off(&r, 2.0f);
    static fc_t fc;
    fc = r.s.fc;
    fc_rc_input rc = r.s.fc.rc;
    rc.valid = 1;
    imu_sample imu = r.s.fc.imu;
    baro_sample baro = {0, r.s.fc.last_pressure, 25.0f};
    const int n = 200000;
    float m[4], sink = 0.0f;
    clock_t c0 = clock();
    for (int i = 0; i < n; i++) {
        imu.t_us += 1000;
        imu.gyro.x = 0.001f * (float)(i & 7);          /* keep the optimiser honest */
        fc_step(&fc, &imu, (i % 20) ? NULL : &baro, (i % 4) ? NULL : &rc, m);
        sink += m[0];
    }
    double us = (double)(clock() - c0) / CLOCKS_PER_SEC * 1e6 / n;
    printf("fc_step, armed ALT_HOLD, on this host: %.3f us per call (%d calls, state %s, %g)\n"
           "Not the MCU: an rv32imc without FPU at 297 MHz is far slower - measured on the board.\n",
           us, n, fc_state_name(fc.state), (double)sink);
}

typedef struct { const char *name; int (*fn)(const char *); } scenario;
static const scenario ALL[] = {
    {"arm_refusal", sc_arm_refusal}, {"hover", sc_hover}, {"angle_step", sc_angle_step},
    {"yaw", sc_yaw}, {"rc_loss", sc_rc_loss}, {"imu_fail", sc_imu_fail}, {"wind", sc_wind},
    {"acro_flip", sc_acro_flip},
};

int main(int argc, char **argv)
{
    const char *want[16];
    int nwant = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--csv") && i + 1 < argc) {
            csv = fopen(argv[++i], "w");
            if (!csv) { perror("csv"); return 2; }
        } else if (!strcmp(argv[i], "--vib")) {
            vibration = 1;
        } else if (!strcmp(argv[i], "--bench")) {
            bench();
            return 0;
        } else if (!strcmp(argv[i], "-v")) {
            verbose = 1;
        } else if (nwant < 16) {
            want[nwant++] = argv[i];
        }
    }
    printf("SITL scenarios (%s sensor profile)\n", vibration ? "datasheet + ASSUMED vibration"
                                                               : "datasheet noise only");
    int fails = 0, ran = 0;
    for (size_t k = 0; k < sizeof(ALL) / sizeof(ALL[0]); k++) {
        int pick = nwant == 0;
        for (int i = 0; i < nwant; i++)
            if (!strcmp(want[i], ALL[k].name))
                pick = 1;
        if (!pick)
            continue;
        ran++;
        if (!ALL[k].fn(ALL[k].name))
            fails++;
    }
    printf("%d scenarios, %d failed\n", ran, fails);
    if (csv)
        fclose(csv);
    return fails ? 1 : 0;
}
