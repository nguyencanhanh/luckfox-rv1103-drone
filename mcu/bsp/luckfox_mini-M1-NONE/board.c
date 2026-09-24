/**
  * Luckfox Pico Mini, Milestone 1: RT-Thread tren HPMCU chay dong thoi voi Linux.
  *
  *  - thread "hello": in "Hello RV1103 MCU" moi 1 s
  *  - rt_bench.c: vong lap 1 kHz uu tien cao, do chu ky va do tre
  *
  * MCU khong co UART (HAL RV1106 khong co clock/thiet bi UART cho MCU), moi rt_kprintf
  * di vao vong dem log trong RAM chung (drv_pstore.c), Linux doc bang tools/mcu-tool.
  * Linux so huu moi chan va ngat GPIO; board nay khong mux chan nao.
  */

#include <rtthread.h>
#include "hal_base.h"
#include "board.h"

#define HELLO_PERIOD_MS     1000
#define HELLO_STACK_SIZE    1024
#define HELLO_PRIORITY      25
#define HELLO_TIMESLICE     10

static void hello_thread_entry(void *parameter)
{
    unsigned int count = 0;

    while (1)
    {
        rt_kprintf("Hello RV1103 MCU %u\n", count++);
        rt_thread_mdelay(HELLO_PERIOD_MS);
    }
}

static int hello_init(void)
{
    rt_thread_t tid;

    tid = rt_thread_create("hello", hello_thread_entry, RT_NULL,
                           HELLO_STACK_SIZE, HELLO_PRIORITY, HELLO_TIMESLICE);
    if (tid == RT_NULL)
        return -RT_ENOMEM;

    rt_thread_startup(tid);
    return RT_EOK;
}
INIT_APP_EXPORT(hello_init);

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
