# Linux ↔ MCU: vendor có gì

Viết tắt như [RV1103_MCU.md](RV1103_MCU.md).

| Cơ chế | Có cho RV1106 không | Bằng chứng |
|---|---|---|
| RPMsg (kernel) | **không** | `K/drivers/rpmsg/rockchip_rpmsg.c:402-404` chỉ khớp `rk3562-rpmsg`, `rk3568-rpmsg` |
| rpmsg-lite (MCU) | **không** | `MCU/bsp/rockchip/common/drivers/rpmsg-lite/lib/include/platform/`: RK3308, RK3568, i.MX…, không có RV1106 |
| remoteproc | không bật | `objs_kernel/.config`: `# CONFIG_REMOTEPROC is not set` |
| Mailbox framework (kernel) | không bật | `# CONFIG_MAILBOX is not set` |
| Mailbox phần cứng | có | `DTS/rv1106.dtsi:1116` (0xFF5C0000); MCU có ngắt `MAILBOX0_AP/BB` (`soc.h:58-59`); HAL `hal_mbox.c` |
| pstore/ramoops đọc log MCU | có trong thiết kế TB, **tắt** trên Luckfox | `DTS/rv1106-thunder-boot.dtsi:26-35`; `# CONFIG_PSTORE is not set` |
| `/dev/mem` | có | `CONFIG_DEVMEM=y`, `# CONFIG_STRICT_DEVMEM is not set` |

## Milestone 1

Chỉ có kênh một chiều MCU → Linux qua RAM chung (đã chừa bằng `reserved-memory`):
- log: vòng đệm `drv_pstore.c` tại `MCU_LOG_BASE`
- số liệu: `struct mcu_bench_shared` tại `MCU_BENCH_BASE` (`shared/ipc/mcu_bench_shared.h`), đọc nhất quán bằng số thứ tự `seq`

Cache: MCU gọi `HAL_DCACHE_CleanByRange` sau khi ghi (nếu `HAL_DCACHE_MODULE_ENABLED`). MCU có bật D-cache cho DDR không:
**UNKNOWN** (không thấy `HAL_DCACHE_Enable` trong BSP). Linux map vùng `no-map` qua `/dev/mem` với `O_SYNC`.

## Sau Milestone 1 (chưa làm)

Setpoint Linux → MCU và telemetry MCU → Linux (mục 14 của kế hoạch) sẽ cần:
bật mailbox trong kernel hoặc dùng polling, định nghĩa gói có `seq`, CRC, timeout, heartbeat. Chưa thiết kế.
