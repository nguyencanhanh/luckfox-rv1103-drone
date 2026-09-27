/*
 * CRSF (Crossfire / ExpressLRS receiver <-> flight controller), the subset a
 * flight controller needs.  Source: TBS, github.com/tbs-fpv/tbs-crsf-spec,
 * crsf.md.
 *
 *   [sync][len][type][payload ...][crc]
 *   sync  0xC8 (flight controller) on a receiver link
 *   len   counts type + payload + crc, 2..62; whole frame <= 64 bytes
 *   crc   CRC-8 poly 0xD5 (DVB-S2) over type + payload
 *   0x16  RC_CHANNELS_PACKED: 16 x 11 bit, LSB first, 22 bytes;
 *         172 = min, 992 = centre, 1811 = max; us = (x - 992) * 5 / 8 + 1500
 *   0x14  LINK_STATISTICS: 10 bytes
 * A receiver in "cut" failsafe simply stops sending 0x16 frames.
 *
 * Plain C99, no allocation: it builds for the MCU, Linux and the simulator.
 */
#ifndef CRSF_H
#define CRSF_H

#include <stdint.h>

#define CRSF_SYNC_FC            0xC8
#define CRSF_MAX_FRAME          64
#define CRSF_TYPE_LINK_STATS    0x14
#define CRSF_TYPE_RC_CHANNELS   0x16
#define CRSF_CHANNELS           16
#define CRSF_TICK_MIN           172
#define CRSF_TICK_MID           992
#define CRSF_TICK_MAX           1811
#define CRSF_RC_FRAME_LEN       26      /* sync + len + type + 22 + crc */

typedef struct {
    uint8_t up_rssi1, up_rssi2;         /* -dBm */
    uint8_t up_lq;                      /* % */
    int8_t up_snr;
    uint8_t antenna, rf_mode, up_power;
    uint8_t down_rssi, down_lq;
    int8_t down_snr;
} crsf_link_stats;

typedef enum { CRSF_NONE = 0, CRSF_GOT_CHANNELS, CRSF_GOT_LINK_STATS, CRSF_GOT_OTHER } crsf_event;

typedef struct {
    uint8_t buf[CRSF_MAX_FRAME];
    uint8_t pos, need;
    uint16_t channels[CRSF_CHANNELS];   /* last good ticks */
    crsf_link_stats link;
    uint32_t frames_ok, crc_errors, len_errors;
} crsf_parser;

uint8_t crsf_crc8(const uint8_t *data, int len);
void crsf_parser_init(crsf_parser *p);
/* feed one byte; returns an event when a frame completes with a good CRC */
crsf_event crsf_feed(crsf_parser *p, uint8_t byte);

/* build a 26-byte RC_CHANNELS_PACKED frame */
void crsf_pack_channels(const uint16_t ticks[CRSF_CHANNELS], uint8_t out[CRSF_RC_FRAME_LEN]);
/* 14-byte LINK_STATISTICS frame */
int crsf_pack_link_stats(const crsf_link_stats *s, uint8_t out[14]);

static inline int crsf_ticks_to_us(uint16_t t) { return ((int)t - 992) * 5 / 8 + 1500; }
static inline uint16_t crsf_us_to_ticks(int us) { return (uint16_t)((us - 1500) * 8 / 5 + 992); }

#endif
