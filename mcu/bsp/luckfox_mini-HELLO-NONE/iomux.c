/**
  * Luckfox Pico Mini: Linux owns every pin (UART2 console, I2C4 camera,
  * MIPI refclk). The hello world MCU image must not touch pinmux.
  */

#include "rtdef.h"
#include "iomux.h"

void rt_hw_iomux_config(void)
{
}
