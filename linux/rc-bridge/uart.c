/* kept apart from rc_bridge.c: <asm/termbits.h> (termios2) clashes with <termios.h> */
#include "uart.h"
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/ioctl.h>

#if defined(__linux__)
#include <asm/termbits.h>

int uart_open(const char *dev, int baud)
{
    int fd = open(dev, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0)
        return -1;
    struct termios2 t;
    if (ioctl(fd, TCGETS2, &t) < 0)
        goto fail;
    t.c_iflag = 0;
    t.c_oflag = 0;
    t.c_lflag = 0;
    t.c_cflag = CS8 | CREAD | CLOCAL | BOTHER;      /* 8N1, arbitrary speed */
    t.c_ispeed = t.c_ospeed = (speed_t)baud;
    t.c_cc[VMIN] = 0;
    t.c_cc[VTIME] = 0;
    if (ioctl(fd, TCSETS2, &t) < 0)
        goto fail;
    return fd;
fail:
    perror("uart");
    close(fd);
    return -1;
}

#elif defined(__APPLE__)
#include <termios.h>
#include <IOKit/serial/ioss.h>

int uart_open(const char *dev, int baud)
{
    int fd = open(dev, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0)
        return -1;
    struct termios t;
    if (tcgetattr(fd, &t) < 0)
        goto fail;
    cfmakeraw(&t);
    t.c_cflag |= CLOCAL | CREAD;
    t.c_cc[VMIN] = 0;
    t.c_cc[VTIME] = 0;
    if (tcsetattr(fd, TCSANOW, &t) < 0)
        goto fail;
    speed_t sp = (speed_t)baud;
    if (ioctl(fd, IOSSIOSPEED, &sp) < 0)
        goto fail;
    return fd;
fail:
    perror("uart");
    close(fd);
    return -1;
}

#else
int uart_open(const char *dev, int baud)
{
    (void)dev;
    (void)baud;
    fprintf(stderr, "uart: no arbitrary-baud support on this platform\n");
    return -1;
}
#endif
