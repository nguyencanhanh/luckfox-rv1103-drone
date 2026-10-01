#ifndef RC_BRIDGE_UART_H
#define RC_BRIDGE_UART_H

/* Open a serial port raw 8N1 at any baud rate (CRSF wants 420000, not a standard
 * termios speed): Linux termios2 / BOTHER, macOS IOSSIOSPEED.  -1 on error. */
int uart_open(const char *dev, int baud);

#endif
