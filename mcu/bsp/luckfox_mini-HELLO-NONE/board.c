/**
  * RV1103 HPMCU (RISC-V SCR1) RT-Thread hello world for Luckfox Pico Mini.
  *
  * Prints a heartbeat once per second through rt_kprintf. With
  * RT_USING_PSTORE the output goes to the persistent RAM log at
  * PERSISTENT_RAM_ADDR (see bsp/rockchip/common/drivers/drv_pstore.c).
  */

#include <rtthread.h>
#include "board.h"

#define HELLO_PERIOD_MS     1000
#define HELLO_STACK_SIZE    1024
#define HELLO_PRIORITY      10
#define HELLO_TIMESLICE     10

static void hello_thread_entry(void *parameter)
{
    unsigned int count = 0;

    while (1)
    {
        rt_kprintf("RV1103 MCU RT-Thread alive %u tick=%u\n",
                   count++, (unsigned int)rt_tick_get());
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
