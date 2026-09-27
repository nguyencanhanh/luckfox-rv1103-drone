/**
  * Luckfox Pico Mini, 05/06: the flight core on the HPMCU ("MCU simulation", plan
  * section 29 step 2).
  *
  *  - fc_bench.c: fc_tick() at 1 kHz, fed by SIM_SENSOR and a quad model running on the
  *    MCU itself; measures the CPU cycles of the flight code on the rv32imc (no FPU)
  *
  * MCU khong co UART (HAL RV1106 khong co clock/thiet bi UART cho MCU), moi rt_kprintf
  * di vao vong dem log trong RAM chung (drv_pstore.c), Linux doc bang tools/mcu-tool.
  * Linux so huu moi chan va ngat GPIO; board nay khong mux chan nao.
  */

#include <rtthread.h>
#include "hal_base.h"
#include "board.h"

/*
 * drv_gpio.c (INIT_BOARD_EXPORT) cai va unmask ngat GPIO0-4 tren MCU, trong khi Linux dang
 * xu ly cac ngat nay. Tra lai ngay sau khi board init xong; con mot khoang ngan truoc
 * INIT_DEVICE_EXPORT ma ngat van mo tren MCU.
 */
static int gpio_irq_release(void)
{
    rt_hw_interrupt_mask(GPIO0_IRQn);
    rt_hw_interrupt_mask(GPIO1_IRQn);
    rt_hw_interrupt_mask(GPIO2_IRQn);
    rt_hw_interrupt_mask(GPIO3_IRQn);
    rt_hw_interrupt_mask(GPIO4_IRQn);
    return RT_EOK;
}
INIT_DEVICE_EXPORT(gpio_irq_release);
