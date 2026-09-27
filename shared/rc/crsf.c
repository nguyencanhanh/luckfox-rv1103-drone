#include "crsf.h"
#include <string.h>

uint8_t crsf_crc8(const uint8_t *data, int len)
{
    uint8_t crc = 0;
    for (int i = 0; i < len; i++) {
        crc ^= data[i];
        for (int b = 0; b < 8; b++)
            crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0xD5) : (uint8_t)(crc << 1);
    }
    return crc;
}

void crsf_parser_init(crsf_parser *p)
{
    memset(p, 0, sizeof(*p));
    for (int i = 0; i < CRSF_CHANNELS; i++)
        p->channels[i] = CRSF_TICK_MID;
}

static void unpack_channels(const uint8_t *pl, uint16_t out[CRSF_CHANNELS])
{
    uint32_t acc = 0;
    int bits = 0, ch = 0;
    for (int i = 0; i < 22 && ch < CRSF_CHANNELS; i++) {
        acc |= (uint32_t)pl[i] << bits;
        bits += 8;
        while (bits >= 11 && ch < CRSF_CHANNELS) {
            out[ch++] = (uint16_t)(acc & 0x7FF);
            acc >>= 11;
            bits -= 11;
        }
    }
}

static crsf_event handle_frame(crsf_parser *p)
{
    uint8_t len = p->buf[1];
    uint8_t type = p->buf[2];
    const uint8_t *pl = &p->buf[3];
    int plen = len - 2;
    if (crsf_crc8(&p->buf[2], len - 1) != p->buf[len + 1]) {
        p->crc_errors++;
        return CRSF_NONE;
    }
    p->frames_ok++;
    if (type == CRSF_TYPE_RC_CHANNELS && plen == 22) {
        unpack_channels(pl, p->channels);
        return CRSF_GOT_CHANNELS;
    }
    if (type == CRSF_TYPE_LINK_STATS && plen == 10) {
        crsf_link_stats *s = &p->link;
        s->up_rssi1 = pl[0]; s->up_rssi2 = pl[1]; s->up_lq = pl[2];
        s->up_snr = (int8_t)pl[3]; s->antenna = pl[4]; s->rf_mode = pl[5];
        s->up_power = pl[6]; s->down_rssi = pl[7]; s->down_lq = pl[8];
        s->down_snr = (int8_t)pl[9];
        return CRSF_GOT_LINK_STATS;
    }
    return CRSF_GOT_OTHER;
}

crsf_event crsf_feed(crsf_parser *p, uint8_t byte)
{
    if (p->pos == 0) {
        /* receiver -> FC frames start with the FC address; accept the other
         * documented sync values too so a bench TX module also parses */
        if (byte == CRSF_SYNC_FC || byte == 0xEA || byte == 0xEC || byte == 0xEE)
            p->buf[p->pos++] = byte;
        return CRSF_NONE;
    }
    if (p->pos == 1) {
        if (byte < 2 || byte > CRSF_MAX_FRAME - 2) {
            p->len_errors++;
            p->pos = 0;
            return CRSF_NONE;
        }
        p->buf[p->pos++] = byte;
        p->need = (uint8_t)(byte + 2);
        return CRSF_NONE;
    }
    p->buf[p->pos++] = byte;
    if (p->pos < p->need)
        return CRSF_NONE;
    p->pos = 0;
    return handle_frame(p);
}

void crsf_pack_channels(const uint16_t ticks[CRSF_CHANNELS], uint8_t out[CRSF_RC_FRAME_LEN])
{
    out[0] = CRSF_SYNC_FC;
    out[1] = 24;                           /* type + 22 + crc */
    out[2] = CRSF_TYPE_RC_CHANNELS;
    uint32_t acc = 0;
    int bits = 0, o = 3;
    for (int ch = 0; ch < CRSF_CHANNELS; ch++) {
        acc |= (uint32_t)(ticks[ch] & 0x7FF) << bits;
        bits += 11;
        while (bits >= 8) {
            out[o++] = (uint8_t)(acc & 0xFF);
            acc >>= 8;
            bits -= 8;
        }
    }
    out[25] = crsf_crc8(&out[2], 23);
}

int crsf_pack_link_stats(const crsf_link_stats *s, uint8_t out[14])
{
    out[0] = CRSF_SYNC_FC;
    out[1] = 12;
    out[2] = CRSF_TYPE_LINK_STATS;
    out[3] = s->up_rssi1; out[4] = s->up_rssi2; out[5] = s->up_lq;
    out[6] = (uint8_t)s->up_snr; out[7] = s->antenna; out[8] = s->rf_mode;
    out[9] = s->up_power; out[10] = s->down_rssi; out[11] = s->down_lq;
    out[12] = (uint8_t)s->down_snr;
    out[13] = crsf_crc8(&out[2], 11);
    return 14;
}
