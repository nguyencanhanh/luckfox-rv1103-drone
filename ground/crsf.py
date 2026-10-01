"""CRSF framing for the ground station, the Python twin of shared/rc/crsf.c.

Source: TBS, github.com/tbs-fpv/tbs-crsf-spec (crsf.md).  Frame:
[0xC8][len = type + payload + crc][type][payload][crc8 poly 0xD5 over type+payload]
"""

import struct

SYNC = 0xC8
RC_CHANNELS = 0x16
ATTITUDE = 0x1E
FLIGHT_MODE = 0x21
LFX_STATUS = 0x7A   # private: struct fc_ipc_telemetry (shared/ipc/fc_ipc.h)

TICK_MIN, TICK_MID, TICK_MAX = 172, 992, 1811


def crc8(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0xD5) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def us_to_ticks(us):
    return int((us - 1500) * 8 / 5 + 992)


def pack_channels(ticks):
    """16 x 11-bit channels, LSB first -> 26-byte RC_CHANNELS_PACKED frame."""
    acc = bits = 0
    out = bytearray()
    for t in ticks[:16]:
        acc |= (int(t) & 0x7FF) << bits
        bits += 11
        while bits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            bits -= 8
    body = bytes([RC_CHANNELS]) + bytes(out)
    return bytes([SYNC, len(body) + 1]) + body + bytes([crc8(body)])


def frames(buf):
    """Yield (type, payload) for every CRC-good frame in a datagram."""
    i = 0
    while i + 4 <= len(buf):
        if buf[i] not in (0xC8, 0xEA, 0xEC, 0xEE):
            i += 1
            continue
        n = buf[i + 1]
        if n < 2 or i + 2 + n > len(buf):
            i += 1
            continue
        body = buf[i + 2:i + 1 + n]
        if crc8(body) == buf[i + 1 + n]:
            yield body[0], bytes(body[1:])
            i += 2 + n
        else:
            i += 1


# struct fc_ipc_telemetry, little-endian on both the MCU and the Mac
TELEMETRY = struct.Struct("<IBBBBHhhhhh4BHHBB")
TELEMETRY_FIELDS = ("mcu_ms", "state", "mode", "rc_source", "disarm_reason", "arm_blocks",
                    "roll_cdeg", "pitch_cdeg", "yaw_cdeg", "height_cm", "climb_cms",
                    "m1", "m2", "m3", "m4", "loop_us_max", "loop_us_avg", "alt_valid",
                    "calib_done")


def parse_status(payload):
    if len(payload) < TELEMETRY.size:
        return None
    return dict(zip(TELEMETRY_FIELDS, TELEMETRY.unpack_from(payload)))


if __name__ == "__main__":
    assert crc8(b"123456789") == 0xBC, "CRC-8/DVB-S2 check value"
    f = pack_channels([TICK_MIN + 100 * i for i in range(16)])
    assert len(f) == 26 and f[:3] == bytes([0xC8, 24, 0x16])
    (t, p), = frames(b"\x00\x55" + f)
    assert t == RC_CHANNELS and len(p) == 22
    print("crsf.py self-test ok")
