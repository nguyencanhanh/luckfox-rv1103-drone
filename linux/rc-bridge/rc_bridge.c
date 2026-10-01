/*
 * rc-bridge: the drone's Linux side of remote control.
 *
 *   ELRS receiver --CRSF 420000 baud, UART2--+
 *                                           +--> pick a source --> fc_ipc "down" --> MCU
 *   ground station --CRSF frames over UDP--+
 *
 *   MCU --fc_ipc "up" telemetry--> CRSF frames --> ground station (UDP) and the
 *                                                  ELRS receiver (to the handset)
 *
 * Source rule: the ELRS receiver wins whenever it delivered a good frame in the last
 * --timeout-ms; otherwise the network; otherwise nothing is forwarded at all, and
 * the flight core's own RC timeout runs the failsafe (hold level, then land).  Stale
 * commands are never repeated: silence is the failsafe signal.
 *
 * Shared page: --devmem maps MCU_IPC_BASE through /dev/mem (on the board, the
 * reserved-memory page of shared/ipc/mcu_layout.h); --shm FILE maps a file (host,
 * with simulator/server.py --ipc FILE playing the MCU).
 * Builds for the board (SDK ARM toolchain, tools/build_linux_tools.sh) and the host.
 */
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include "../../shared/ipc/fc_ipc.h"
#include "../../shared/ipc/mcu_layout.h"
#include "../../shared/rc/crsf.h"
#include "uart.h"

static volatile sig_atomic_t g_stop;
static void on_signal(int s) { (void)s; g_stop = 1; }

static uint64_t now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000u + (uint64_t)(ts.tv_nsec / 1000000);
}

static void *map_page(const char *shm, int devmem)
{
    int fd;
    off_t off = 0;
    if (devmem) {
        fd = open("/dev/mem", O_RDWR | O_SYNC);      /* uncached: no cache maintenance */
        off = (off_t)MCU_IPC_BASE;
    } else {
        fd = open(shm, O_RDWR | O_CREAT, 0644);
        if (fd >= 0 && ftruncate(fd, FC_IPC_PAGE_SIZE) < 0) {
            close(fd);
            fd = -1;
        }
    }
    if (fd < 0) {
        perror(devmem ? "/dev/mem" : shm);
        return NULL;
    }
    void *p = mmap(NULL, FC_IPC_PAGE_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, off);
    close(fd);
    if (p == MAP_FAILED) {
        perror("mmap");
        return NULL;
    }
    return p;
}

static const char *mode_name(int mode, int state)
{
    if (state == 2 || state == 3)
        return "FAILSAFE";
    switch (mode) {
    case 0: return "ACRO";
    case 1: return "ANGLE";
    case 2: return "ALTHOLD";
    }
    return "?";
}

static void usage(void)
{
    fprintf(stderr,
            "usage: rc-bridge (--devmem | --shm FILE) [--uart DEV] [--baud N] [--udp PORT]\n"
            "                 [--timeout-ms N] [-v]\n"
            "  --devmem       shared page at MCU_IPC_BASE via /dev/mem (on the board)\n"
            "  --shm FILE     shared page in a file (host, with simulator/server.py --ipc FILE)\n"
            "  --uart DEV     ELRS receiver, e.g. /dev/ttyS2 (UART2 after the console moved)\n"
            "  --baud N       default 420000 (ExpressLRS default; TBS spec 416666)\n"
            "  --udp PORT     ground-station CRSF over UDP, default 7700\n"
            "  --timeout-ms N a source counts as live this long after its last frame, default 200\n");
}

int main(int argc, char **argv)
{
    const char *shm = NULL, *uart_dev = NULL;
    int devmem = 0, baud = 420000, udp_port = 7700, timeout_ms = 200, verbose = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--devmem")) devmem = 1;
        else if (!strcmp(argv[i], "--shm") && i + 1 < argc) shm = argv[++i];
        else if (!strcmp(argv[i], "--uart") && i + 1 < argc) uart_dev = argv[++i];
        else if (!strcmp(argv[i], "--baud") && i + 1 < argc) baud = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--udp") && i + 1 < argc) udp_port = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--timeout-ms") && i + 1 < argc) timeout_ms = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-v")) verbose = 1;
        else { usage(); return 2; }
    }
    if (!devmem && !shm) {
        usage();
        return 2;
    }
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    struct fc_ipc_port port;
    memset(&port, 0, sizeof(port));
    port.page = map_page(shm, devmem);
    if (!port.page)
        return 1;

    int ufd = -1;
    if (uart_dev && (ufd = uart_open(uart_dev, baud)) < 0) {
        fprintf(stderr, "rc-bridge: cannot open %s\n", uart_dev);
        return 1;
    }
    int sfd = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons((uint16_t)udp_port);
    a.sin_addr.s_addr = htonl(INADDR_ANY);
    if (sfd < 0 || bind(sfd, (struct sockaddr *)&a, sizeof(a)) < 0) {
        perror("udp");
        return 1;
    }
    fprintf(stderr, "rc-bridge: page %s, ELRS %s @ %d, ground station UDP %d\n",
            devmem ? "/dev/mem MCU_IPC_BASE" : shm, uart_dev ? uart_dev : "(none)", baud, udp_port);

    crsf_parser elrs, net;
    crsf_parser_init(&elrs);
    crsf_parser_init(&net);
    uint64_t t_elrs = 0, t_net = 0, t_hb = 0, t_gcs_tx = 0, t_uart_tx = 0, t_log = now_ms();
    struct sockaddr_in gcs;
    socklen_t gcs_len = 0;
    struct fc_ipc_telemetry tel;
    int have_tel = 0, uart_turn = 0, waiting_logged = 0;
    uint32_t fwd_elrs = 0, fwd_net = 0, tel_n = 0, hb_seq = 0;

    while (!g_stop) {
        struct pollfd pf[2];
        int n = 0;
        pf[n].fd = sfd; pf[n].events = POLLIN; n++;
        if (ufd >= 0) { pf[n].fd = ufd; pf[n].events = POLLIN; n++; }
        poll(pf, (nfds_t)n, 5);
        uint64_t now = now_ms();

        if (!fc_ipc_valid(&port)) {               /* MCU not up (or re-formatting) */
            if (!waiting_logged)
                fprintf(stderr, "rc-bridge: waiting for the MCU to format the shared page\n");
            waiting_logged = 1;
            usleep(20000);
            continue;
        }
        waiting_logged = 0;

        /* ---- ELRS receiver ---- */
        if (ufd >= 0 && (pf[1].revents & POLLIN)) {
            uint8_t buf[256];
            ssize_t r = read(ufd, buf, sizeof(buf));
            for (ssize_t i = 0; i < r; i++) {
                if (crsf_feed(&elrs, buf[i]) == CRSF_GOT_CHANNELS) {
                    t_elrs = now;
                    struct fc_ipc_rc rc;
                    memset(&rc, 0, sizeof(rc));
                    memcpy(rc.ch, elrs.channels, sizeof(rc.ch));
                    rc.source = FC_RC_ELRS;
                    rc.link_quality = elrs.link.up_lq;
                    rc.rssi_dbm = (int8_t)(-(int)elrs.link.up_rssi1);
                    fwd_elrs += fc_ipc_send(&port, &port.page->down, FC_IPC_RC, &rc, sizeof(rc));
                }
            }
        }

        /* ---- ground station ---- */
        if (pf[0].revents & POLLIN) {
            uint8_t buf[512];
            struct sockaddr_in from;
            socklen_t fl = sizeof(from);
            ssize_t r = recvfrom(sfd, buf, sizeof(buf), 0, (struct sockaddr *)&from, &fl);
            int got = 0;
            for (ssize_t i = 0; i < r; i++)
                if (crsf_feed(&net, buf[i]) == CRSF_GOT_CHANNELS)
                    got = 1;
            if (got) {
                gcs = from;
                gcs_len = fl;
                t_net = now;
                /* the receiver has priority: the network only flies when ELRS is silent */
                if (!t_elrs || now - t_elrs > (uint64_t)timeout_ms) {
                    struct fc_ipc_rc rc;
                    memset(&rc, 0, sizeof(rc));
                    memcpy(rc.ch, net.channels, sizeof(rc.ch));
                    rc.source = FC_RC_NETWORK;
                    fwd_net += fc_ipc_send(&port, &port.page->down, FC_IPC_RC, &rc, sizeof(rc));
                }
            }
        }

        /* ---- heartbeat, 10 Hz ---- */
        if (now - t_hb >= 100) {
            struct fc_ipc_heartbeat hb = {(uint32_t)now, hb_seq++};
            fc_ipc_send(&port, &port.page->down, FC_IPC_HEARTBEAT, &hb, sizeof(hb));
            port.page->linux_alive++;
            t_hb = now;
        }

        /* ---- telemetry from the MCU ---- */
        struct fc_ipc_record rec;
        while (fc_ipc_recv(&port, &port.page->up, &rec))
            if (rec.type == FC_IPC_TELEMETRY && rec.len >= sizeof(tel)) {
                memcpy(&tel, rec.payload, sizeof(tel));
                have_tel = 1;
                tel_n++;
            }
        uint8_t f[CRSF_MAX_FRAME];
        const float CD = 3.14159265f / 18000.0f;          /* centidegree -> rad */
        if (have_tel && gcs_len && now - t_gcs_tx >= 50) { /* 20 Hz to the ground */
            uint8_t pkt[3 * CRSF_MAX_FRAME];
            int len = crsf_pack_frame(CRSF_TYPE_LFX_STATUS, &tel, (int)sizeof(tel), pkt);
            len += crsf_pack_attitude(tel.pitch_cdeg * CD, tel.roll_cdeg * CD, tel.yaw_cdeg * CD,
                                      pkt + len);
            len += crsf_pack_flight_mode(mode_name(tel.mode, tel.state), pkt + len);
            sendto(sfd, pkt, (size_t)len, 0, (struct sockaddr *)&gcs, gcs_len);
            t_gcs_tx = now;
        }
        if (have_tel && ufd >= 0 && now - t_uart_tx >= 100) {   /* 10 Hz to the handset */
            int len = (uart_turn++ & 1)
                ? crsf_pack_flight_mode(mode_name(tel.mode, tel.state), f)
                : crsf_pack_attitude(tel.pitch_cdeg * CD, tel.roll_cdeg * CD, tel.yaw_cdeg * CD, f);
            if (write(ufd, f, (size_t)len) < 0 && errno != EAGAIN)
                perror("uart write");
            t_uart_tx = now;
        }

        if (now - t_log >= 5000) {
            const char *src = (t_elrs && now - t_elrs <= (uint64_t)timeout_ms) ? "ELRS"
                            : (t_net && now - t_net <= (uint64_t)timeout_ms) ? "network" : "NONE";
            fprintf(stderr, "rc-bridge: source %s | fwd elrs %u net %u | telemetry %u | "
                    "crc err elrs %u net %u | ipc crc %u\n", src, fwd_elrs, fwd_net, tel_n,
                    elrs.crc_errors, net.crc_errors, port.rx_crc_err);
            if (verbose && have_tel)
                fprintf(stderr, "  state %u mode %u h %d cm loop avg/max %u/%u us\n", tel.state,
                        tel.mode, tel.height_cm, tel.loop_us_avg, tel.loop_us_max);
            t_log = now;
        }
    }
    fprintf(stderr, "rc-bridge: stop\n");
    return 0;
}
