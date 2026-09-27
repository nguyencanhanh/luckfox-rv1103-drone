/*
 * Small single-precision math kit shared by the flight code and the simulator.
 *
 * Frames: NED world (x north, y east, z down) and FRD body (x forward,
 * y right, z down).  A quaternion q rotates body vectors into the world:
 * v_world = q * v_body * conj(q).  Euler angles are ZYX (yaw, pitch, roll).
 *
 * Everything is float on purpose: the HPMCU is rv32imc (no FPU,
 * rtconfig.py:38), so every double would cost a soft-double call.  Build with
 * -Wdouble-promotion to keep it that way.
 */
#ifndef FC_MATH_H
#define FC_MATH_H

#include <math.h>

#define FC_PI      3.14159265f
#define FC_DEG2RAD (FC_PI / 180.0f)
#define FC_RAD2DEG (180.0f / FC_PI)
#define FC_GRAVITY 9.80665f

typedef struct { float x, y, z; } vec3;
typedef struct { float w, x, y, z; } quat;

static inline float constrainf(float v, float lo, float hi)
{
    return v < lo ? lo : (v > hi ? hi : v);
}

static inline float wrap_pi(float a)
{
    while (a > FC_PI)
        a -= 2.0f * FC_PI;
    while (a < -FC_PI)
        a += 2.0f * FC_PI;
    return a;
}

static inline vec3 v3(float x, float y, float z) { vec3 r = {x, y, z}; return r; }
static inline vec3 v3_add(vec3 a, vec3 b) { return v3(a.x + b.x, a.y + b.y, a.z + b.z); }
static inline vec3 v3_sub(vec3 a, vec3 b) { return v3(a.x - b.x, a.y - b.y, a.z - b.z); }
static inline vec3 v3_scale(vec3 a, float s) { return v3(a.x * s, a.y * s, a.z * s); }
static inline float v3_dot(vec3 a, vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static inline float v3_norm(vec3 a) { return sqrtf(v3_dot(a, a)); }

static inline vec3 v3_cross(vec3 a, vec3 b)
{
    return v3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
}

static inline quat q_identity(void) { quat q = {1.0f, 0.0f, 0.0f, 0.0f}; return q; }
static inline quat q_conj(quat q) { quat r = {q.w, -q.x, -q.y, -q.z}; return r; }

static inline quat q_mul(quat a, quat b)
{
    quat r;
    r.w = a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z;
    r.x = a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y;
    r.y = a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x;
    r.z = a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w;
    return r;
}

static inline quat q_normalize(quat q)
{
    float n = sqrtf(q.w * q.w + q.x * q.x + q.y * q.y + q.z * q.z);
    if (n < 1e-9f)
        return q_identity();
    n = 1.0f / n;
    q.w *= n; q.x *= n; q.y *= n; q.z *= n;
    return q;
}

/* body -> world */
static inline vec3 q_rotate(quat q, vec3 v)
{
    vec3 u = v3(q.x, q.y, q.z);
    vec3 t = v3_scale(v3_cross(u, v), 2.0f);
    return v3_add(v3_add(v, v3_scale(t, q.w)), v3_cross(u, t));
}

/* world -> body */
static inline vec3 q_rotate_inv(quat q, vec3 v) { return q_rotate(q_conj(q), v); }

/* q <- q (x) exp(w dt / 2), w in body rad/s */
static inline quat q_integrate(quat q, vec3 w, float dt)
{
    float h = 0.5f * dt;
    quat d = {1.0f, w.x * h, w.y * h, w.z * h};
    return q_normalize(q_mul(q, d));
}

static inline quat q_from_euler(float roll, float pitch, float yaw)
{
    float cr = cosf(roll * 0.5f), sr = sinf(roll * 0.5f);
    float cp = cosf(pitch * 0.5f), sp = sinf(pitch * 0.5f);
    float cy = cosf(yaw * 0.5f), sy = sinf(yaw * 0.5f);
    quat q;
    q.w = cr * cp * cy + sr * sp * sy;
    q.x = sr * cp * cy - cr * sp * sy;
    q.y = cr * sp * cy + sr * cp * sy;
    q.z = cr * cp * sy - sr * sp * cy;
    return q;
}

static inline vec3 q_to_euler(quat q)
{
    vec3 e;
    e.x = atan2f(2.0f * (q.w * q.x + q.y * q.z), 1.0f - 2.0f * (q.x * q.x + q.y * q.y));
    e.y = asinf(constrainf(2.0f * (q.w * q.y - q.z * q.x), -1.0f, 1.0f));
    e.z = atan2f(2.0f * (q.w * q.z + q.x * q.y), 1.0f - 2.0f * (q.y * q.y + q.z * q.z));
    return e;
}

/* cosine of the angle between body z and world z: 1 = level, 0 = on its side */
static inline float q_cos_tilt(quat q)
{
    return 1.0f - 2.0f * (q.x * q.x + q.y * q.y);
}

#endif
