/*
 * Unit tests for the flight core (plan section 27): filters, PID, mixer
 * (hover, roll+/-, pitch+/-, yaw+/-, saturation), attitude estimator,
 * altitude estimator, gyro calibration, arming / failsafe, CRSF, RC map.
 * Host build: make -C simulator test
 */
#include <stdio.h>
#include <string.h>
#include "../fc/fc.h"
#include "../../shared/rc/crsf.h"
#include "../../shared/rc/rc_map.h"

static int failures, checks;

#define CHECK(cond, ...) do { checks++; if (!(cond)) { failures++; \
    printf("  FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)
#define NEAR(a, b, tol) (fabsf((float)(a) - (float)(b)) <= (tol))

static void test_filters(void)
{
    pt1_filter f;
    pt1_init(&f, 10.0f, 0.001f);
    float y = 0.0f;
    for (int i = 0; i < 1000; i++)
        y = pt1_apply(&f, 1.0f);
    CHECK(NEAR(y, 1.0f, 1e-3f), "pt1 settles to 1, got %f", (double)y);

    biquad_filter b;
    biquad_lpf_init(&b, 50.0f, 1000.0f);
    for (int i = 0; i < 2000; i++)
        y = biquad_apply(&b, 1.0f);
    CHECK(NEAR(y, 1.0f, 1e-3f), "biquad DC gain 1, got %f", (double)y);
    /* 300 Hz sine through a 50 Hz Butterworth: second order, ~-31 dB */
    float peak = 0.0f;
    for (int i = 0; i < 4000; i++) {
        y = biquad_apply(&b, sinf(2.0f * FC_PI * 300.0f * (float)i / 1000.0f));
        if (i > 2000 && fabsf(y) > peak)
            peak = fabsf(y);
    }
    CHECK(peak < 0.05f, "biquad attenuates 300 Hz, peak %f", (double)peak);
}

static void test_pid(void)
{
    pid_params p = {.kp = 2.0f, .ki = 1.0f, .kd = 0.0f, .i_limit = 0.5f,
                    .out_limit = 1.0f, .d_cutoff_hz = 0.0f};
    pid_ctrl c;
    pid_init(&c, &p, 0.01f);
    float u = pid_update(&c, 0.1f, 0.0f, 0.01f, 0);
    CHECK(NEAR(c.p_term, 0.2f, 1e-6f), "P term");
    for (int i = 0; i < 10000; i++)
        u = pid_update(&c, 10.0f, 0.0f, 0.01f, 0);
    CHECK(NEAR(u, 1.0f, 1e-6f), "output saturates at out_limit, got %f", (double)u);
    CHECK(c.integ <= 0.5f + 1e-6f, "integrator clamp, got %f", (double)c.integ);
    /* anti-windup: while saturated the integrator must not have grown past
     * what it had when saturation began */
    pid_reset(&c);
    for (int i = 0; i < 100; i++)
        pid_update(&c, 10.0f, 0.0f, 0.01f, 0);
    CHECK(c.integ < 0.05f, "no windup while output saturated, integ %f", (double)c.integ);
    pid_reset(&c);
    for (int i = 0; i < 100; i++)
        pid_update(&c, 0.1f, 0.0f, 0.01f, 1);
    CHECK(c.integ == 0.0f, "freeze_i stops integration pushing into saturation");
    /* derivative on measurement: a setpoint step gives no D kick */
    pid_params pd = {.kp = 0.0f, .ki = 0.0f, .kd = 1.0f, .i_limit = 1.0f,
                     .out_limit = 100.0f, .d_cutoff_hz = 0.0f};
    pid_init(&c, &pd, 0.01f);
    pid_update(&c, 0.0f, 0.0f, 0.01f, 0);
    u = pid_update(&c, 5.0f, 0.0f, 0.01f, 0);
    CHECK(NEAR(u, 0.0f, 1e-6f), "no derivative kick on setpoint step");
    u = pid_update(&c, 5.0f, 0.1f, 0.01f, 0);
    CHECK(NEAR(u, -10.0f, 1e-3f), "D opposes measurement motion, got %f", (double)u);
}

static void test_mixer(void)
{
    const int spin[4] = {1, 0, 0, 1};
    mixer_table t;
    mixer_quadx_table(&t, spin);
    mixer_out o;
    /* M1 RR, M2 FR, M3 RL, M4 FL */
    mixer_mix(&t, 0.5f, 0.0f, 0.0f, 0.0f, &o);
    for (int i = 0; i < 4; i++)
        CHECK(NEAR(o.motor[i], 0.5f, 1e-6f), "hover: all equal");
    CHECK(!o.saturated, "hover not saturated");

    mixer_mix(&t, 0.5f, 0.1f, 0.0f, 0.0f, &o);
    CHECK(o.motor[2] > 0.5f && o.motor[3] > 0.5f && o.motor[0] < 0.5f && o.motor[1] < 0.5f,
          "roll+: left motors up, right down");
    mixer_mix(&t, 0.5f, -0.1f, 0.0f, 0.0f, &o);
    CHECK(o.motor[0] > 0.5f && o.motor[1] > 0.5f && o.motor[2] < 0.5f && o.motor[3] < 0.5f,
          "roll-: right motors up");
    mixer_mix(&t, 0.5f, 0.0f, 0.1f, 0.0f, &o);
    CHECK(o.motor[1] > 0.5f && o.motor[3] > 0.5f && o.motor[0] < 0.5f && o.motor[2] < 0.5f,
          "pitch+ (nose up): front motors up");
    mixer_mix(&t, 0.5f, 0.0f, -0.1f, 0.0f, &o);
    CHECK(o.motor[0] > 0.5f && o.motor[2] > 0.5f && o.motor[1] < 0.5f && o.motor[3] < 0.5f,
          "pitch-: rear motors up");
    mixer_mix(&t, 0.5f, 0.0f, 0.0f, 0.1f, &o);
    CHECK(o.motor[1] > 0.5f && o.motor[2] > 0.5f && o.motor[0] < 0.5f && o.motor[3] < 0.5f,
          "yaw+: CCW props (M2, M3) up");
    mixer_mix(&t, 0.5f, 0.0f, 0.0f, -0.1f, &o);
    CHECK(o.motor[0] > 0.5f && o.motor[3] > 0.5f, "yaw-: CW props (M1, M4) up");

    /* saturation: full roll at full throttle keeps the roll difference */
    mixer_mix(&t, 1.0f, 0.3f, 0.0f, 0.0f, &o);
    CHECK(o.saturated, "saturation flagged");
    CHECK(NEAR(o.motor[3] - o.motor[1], 0.6f, 1e-5f), "attitude kept under saturation");
    for (int i = 0; i < 4; i++)
        CHECK(o.motor[i] >= 0.0f && o.motor[i] <= 1.0f, "clamped to 0..1");
    mixer_mix(&t, 0.5f, 2.0f, 2.0f, 2.0f, &o);
    for (int i = 0; i < 4; i++)
        CHECK(o.motor[i] >= 0.0f && o.motor[i] <= 1.0f, "huge demand clamped");
}

static void test_attitude(void)
{
    attitude_params p = {.kp = 1.0f, .ki = 0.05f, .acc_gate = 0.15f};
    attitude_est e;
    attitude_init(&e, &p);
    /* static 20 deg roll: accel sees gravity rotated into the body */
    quat truth = q_from_euler(20.0f * FC_DEG2RAD, -10.0f * FC_DEG2RAD, 0.0f);
    vec3 acc = q_rotate_inv(truth, v3(0.0f, 0.0f, -FC_GRAVITY));
    attitude_update(&e, v3(0, 0, 0), acc, 0.001f);   /* initialises from acc */
    CHECK(NEAR(e.euler.x, 20.0f * FC_DEG2RAD, 0.01f) && NEAR(e.euler.y, -10.0f * FC_DEG2RAD, 0.01f),
          "init from accelerometer: %f %f", (double)(e.euler.x * FC_RAD2DEG),
          (double)(e.euler.y * FC_RAD2DEG));

    /* start level, truth is tilted: the filter must converge (sign check) */
    attitude_init(&e, &p);
    attitude_reset_from_acc(&e, v3(0, 0, -FC_GRAVITY));
    for (int i = 0; i < 10000; i++)
        attitude_update(&e, v3(0, 0, 0), acc, 0.001f);
    CHECK(NEAR(e.euler.x, 20.0f * FC_DEG2RAD, 0.02f) && NEAR(e.euler.y, -10.0f * FC_DEG2RAD, 0.02f),
          "converges to the accelerometer: %f %f", (double)(e.euler.x * FC_RAD2DEG),
          (double)(e.euler.y * FC_RAD2DEG));

    /* gyro only: 90 deg/s about z for 1 s -> yaw 90 deg */
    attitude_init(&e, &p);
    attitude_reset_from_acc(&e, v3(0, 0, -FC_GRAVITY));
    for (int i = 0; i < 1000; i++)
        attitude_update(&e, v3(0, 0, 90.0f * FC_DEG2RAD), v3(0, 0, -FC_GRAVITY), 0.001f);
    CHECK(NEAR(e.euler.z, 90.0f * FC_DEG2RAD, 0.01f), "yaw from gyro: %f",
          (double)(e.euler.z * FC_RAD2DEG));

    /* constant gyro bias is learnt by the integral term */
    attitude_init(&e, &p);
    attitude_reset_from_acc(&e, v3(0, 0, -FC_GRAVITY));
    for (int i = 0; i < 60000; i++)
        attitude_update(&e, v3(0.01f, -0.01f, 0), v3(0, 0, -FC_GRAVITY), 0.001f);
    CHECK(NEAR(e.euler.x, 0.0f, 0.01f) && NEAR(e.euler.y, 0.0f, 0.01f),
          "roll/pitch bias rejected: %f %f", (double)(e.euler.x * FC_RAD2DEG),
          (double)(e.euler.y * FC_RAD2DEG));
}

static void test_altitude(void)
{
    altitude_params p = {.crossover = 1.0f, .baro_timeout_s = 0.5f};
    altitude_est e;
    altitude_init(&e, &p);
    CHECK(NEAR(altitude_from_pressure(101325.0f, 101325.0f), 0.0f, 1e-3f), "0 m at p0");
    /* ~12 Pa per metre near sea level */
    float h = altitude_from_pressure(101325.0f - 120.0f, 101325.0f);
    CHECK(h > 9.5f && h < 10.5f, "120 Pa ~ 10 m, got %f", (double)h);

    /* climb at 1 m/s for 5 s with perfect accel + baro */
    quat level = q_identity();
    float truth_h = 0.0f;
    altitude_baro(&e, 101325.0f);
    for (int i = 1; i <= 5000; i++) {
        float t = (float)i * 0.001f;
        float a = t < 1.0f ? 1.0f : 0.0f;              /* accelerate, then cruise */
        vec3 acc = v3(0, 0, -(FC_GRAVITY + a));
        altitude_predict(&e, level, acc, 0.001f);
        truth_h = t < 1.0f ? 0.5f * t * t : 0.5f + (t - 1.0f);
        if (i % 20 == 0)
            altitude_baro(&e, 101325.0f * powf(1.0f - truth_h / 44330.0f, 5.255f));
    }
    CHECK(NEAR(e.h, truth_h, 0.1f) && NEAR(e.v, 1.0f, 0.1f), "tracks a climb: h %f v %f",
          (double)e.h, (double)e.v);
}

static void test_gyro_calib(void)
{
    gyro_calib c;
    gyro_calib_init(&c, 100, 0.05f);
    for (int i = 0; i < 99; i++)
        gyro_calib_feed(&c, v3(0.01f, -0.02f, 0.03f));
    CHECK(!c.done, "not done before the window is full");
    gyro_calib_feed(&c, v3(0.01f, -0.02f, 0.03f));
    CHECK(c.done && NEAR(c.bias.x, 0.01f, 1e-6f) && NEAR(c.bias.y, -0.02f, 1e-6f), "bias learnt");
    gyro_calib_init(&c, 100, 0.05f);
    for (int i = 0; i < 300; i++)
        gyro_calib_feed(&c, v3(i % 2 ? 0.5f : -0.5f, 0, 0));     /* being moved */
    CHECK(!c.done, "motion never produces a bias");
}

static arming_inputs good_inputs(void)
{
    arming_inputs in = {.rc_ok = 1, .imu_ok = 1, .calib_ok = 1, .arm_switch = 0,
                        .throttle_stick = 0.0f, .tilt = 0.0f, .landed = 0, .crash_check = 1};
    return in;
}

static void test_arming(void)
{
    fc_params fp;
    fc_default_params(&fp);
    arming_sm a;
    arming_init(&a, &fp.arm);
    arming_inputs in = good_inputs();
    const float dt = 0.001f;

    CHECK(a.state == FC_DISARMED, "boots disarmed");
    /* switch already on at boot: no arming */
    in.arm_switch = 1;
    for (int i = 0; i < 100; i++)
        arming_update(&a, &in, dt);
    CHECK(a.state == FC_DISARMED, "switch on at boot does not arm");
    in.arm_switch = 0;
    arming_update(&a, &in, dt);
    in.arm_switch = 1;
    arming_update(&a, &in, dt);
    CHECK(a.state == FC_ARMED, "arms after the switch is cycled");
    in.arm_switch = 0;
    arming_update(&a, &in, dt);
    CHECK(a.state == FC_DISARMED && a.last_disarm == DISARM_SWITCH, "switch disarms at once");

    /* refusals */
    struct { const char *what; void (*f)(arming_inputs *); } dummy;
    (void)dummy;
    in = good_inputs();
    in.throttle_stick = 0.5f;
    arming_update(&a, &in, dt);
    in.arm_switch = 1;
    arming_update(&a, &in, dt);
    CHECK(a.state == FC_DISARMED && (a.blocks & ARM_BLOCK_THROTTLE), "throttle up refuses");
    in.throttle_stick = 0.0f;
    arming_update(&a, &in, dt);
    CHECK(a.state == FC_DISARMED, "refused attempt needs a new switch cycle");
    in = good_inputs();
    in.tilt = 40.0f * FC_DEG2RAD;
    arming_update(&a, &in, dt);
    in.arm_switch = 1;
    arming_update(&a, &in, dt);
    CHECK(a.state == FC_DISARMED && (a.blocks & ARM_BLOCK_TILT), "tilted refuses");
    in = good_inputs();
    in.calib_ok = 0;
    arming_update(&a, &in, dt);
    in.arm_switch = 1;
    arming_update(&a, &in, dt);
    CHECK(a.state == FC_DISARMED && (a.blocks & ARM_BLOCK_CALIB), "no gyro calibration refuses");

    /* RC loss: hold, then land, then disarm on landing */
    in = good_inputs();
    arming_update(&a, &in, dt);
    in.arm_switch = 1;
    arming_update(&a, &in, dt);
    CHECK(a.state == FC_ARMED, "armed for failsafe test");
    in.rc_ok = 0;
    for (int i = 0; i < 300; i++)
        arming_update(&a, &in, dt);
    CHECK(a.state == FC_FAILSAFE_HOLD, "RC lost > 0.25 s: failsafe hold");
    in.rc_ok = 1;
    arming_update(&a, &in, dt);
    CHECK(a.state == FC_ARMED, "link back during hold: control returns");
    in.rc_ok = 0;
    for (int i = 0; i < 1500; i++)
        arming_update(&a, &in, dt);
    CHECK(a.state == FC_FAILSAFE_LAND, "still lost after the hold: landing");
    in.rc_ok = 1;
    arming_update(&a, &in, dt);
    CHECK(a.state == FC_FAILSAFE_LAND, "link back during landing does not resume");
    in.landed = 1;
    arming_update(&a, &in, dt);
    CHECK(a.state == FC_DISARMED && a.last_disarm == DISARM_FAILSAFE_LANDED, "landed: disarm");

    /* IMU loss disarms at once */
    in = good_inputs();
    arming_update(&a, &in, dt);
    in.arm_switch = 1;
    arming_update(&a, &in, dt);
    in.imu_ok = 0;
    for (int i = 0; i < 25; i++)
        arming_update(&a, &in, dt);
    CHECK(a.state == FC_DISARMED && a.last_disarm == DISARM_IMU_LOST, "IMU lost: disarm");

    /* crash: upside down in a self-levelling mode; not in ACRO */
    in = good_inputs();
    arming_update(&a, &in, dt);
    in.arm_switch = 1;
    arming_update(&a, &in, dt);
    in.tilt = 170.0f * FC_DEG2RAD;
    in.crash_check = 0;
    for (int i = 0; i < 1000; i++)
        arming_update(&a, &in, dt);
    CHECK(a.state == FC_ARMED, "ACRO flip is not a crash");
    in.crash_check = 1;
    for (int i = 0; i < 400; i++)
        arming_update(&a, &in, dt);
    CHECK(a.state == FC_DISARMED && a.last_disarm == DISARM_CRASH, "crash: disarm");
}

static void test_crsf(void)
{
    const uint8_t check[] = "123456789";
    CHECK(crsf_crc8(check, 9) == 0xBC, "CRC-8/DVB-S2 check value 0xBC, got 0x%02X",
          crsf_crc8(check, 9));

    uint16_t in[16], out_ok = 1;
    for (int i = 0; i < 16; i++)
        in[i] = (uint16_t)(CRSF_TICK_MIN + i * 100);
    uint8_t frame[CRSF_RC_FRAME_LEN];
    crsf_pack_channels(in, frame);
    CHECK(frame[0] == 0xC8 && frame[1] == 24 && frame[2] == 0x16, "frame header");
    crsf_parser p;
    crsf_parser_init(&p);
    /* garbage before the frame must be skipped */
    crsf_feed(&p, 0x55);
    crsf_feed(&p, 0x00);
    crsf_event ev = CRSF_NONE;
    for (int i = 0; i < CRSF_RC_FRAME_LEN; i++)
        ev = crsf_feed(&p, frame[i]);
    CHECK(ev == CRSF_GOT_CHANNELS, "channels frame parsed");
    for (int i = 0; i < 16; i++)
        if (p.channels[i] != in[i])
            out_ok = 0;
    CHECK(out_ok, "16 channels round-trip");
    frame[10] ^= 0x01;
    for (int i = 0; i < CRSF_RC_FRAME_LEN; i++)
        ev = crsf_feed(&p, frame[i]);
    CHECK(ev == CRSF_NONE && p.crc_errors == 1, "corrupted frame rejected");
    CHECK(crsf_ticks_to_us(992) == 1500 && crsf_ticks_to_us(172) == 988 &&
          crsf_ticks_to_us(1811) == 2011, "tick -> us mapping (TBS formula)");

    crsf_link_stats ls = {.up_rssi1 = 50, .up_lq = 100, .up_snr = -3};
    uint8_t lf[14];
    crsf_pack_link_stats(&ls, lf);
    for (int i = 0; i < 14; i++)
        ev = crsf_feed(&p, lf[i]);
    CHECK(ev == CRSF_GOT_LINK_STATS && p.link.up_lq == 100 && p.link.up_snr == -3, "link stats");
}

static void test_rc_map(void)
{
    rc_map_params m;
    rc_map_default(&m);
    uint16_t t[16];
    for (int i = 0; i < 16; i++)
        t[i] = CRSF_TICK_MID;
    t[2] = crsf_us_to_ticks(1000);              /* throttle low */
    t[4] = crsf_us_to_ticks(2000);              /* arm */
    t[5] = crsf_us_to_ticks(1500);              /* mode mid */
    t[0] = crsf_us_to_ticks(2000);              /* full right roll */
    rc_command c;
    rc_map_apply(&m, t, &c);
    CHECK(NEAR(c.roll, 1.0f, 0.01f) && NEAR(c.throttle, 0.0f, 0.01f) && c.arm_switch == 1 &&
          c.mode == 2, "AETR map: roll %f thr %f arm %d mode %d", (double)c.roll,
          (double)c.throttle, c.arm_switch, c.mode);
}

int main(void)
{
    test_filters();
    test_pid();
    test_mixer();
    test_attitude();
    test_altitude();
    test_gyro_calib();
    test_arming();
    test_crsf();
    test_rc_map();
    printf("unit tests: %d checks, %d failed\n", checks, failures);
    return failures ? 1 : 0;
}
