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

## Kênh điều khiển (2026-10-01): `shared/ipc/fc_ipc.{h,c}`

Dùng polling, không dùng mailbox (kernel không bật `CONFIG_MAILBOX`):
- **Vị trí:** trang 4 KB tại `MCU_IPC_BASE` = `0x0183F000`. Đây là chính trang benchmark của M1, nên DTS hiện tại đã giữ riêng sẵn, không phải nạp lại Linux. Mỗi firmware dùng trang này cho benchmark hoặc cho IPC, không bao giờ cả hai.
- **Hai vòng đệm SPSC, mỗi vòng 16 bản ghi 64 byte:**
  - `down`: Linux → MCU, chở lệnh lái (kênh CRSF) và heartbeat.
  - `up`: MCU → Linux, chở telemetry.
- **Chỉ số head/tail:** mỗi chỉ số do đúng một bên ghi, và nằm trên dòng 64 byte riêng.
- **Chống đọc dở:** mỗi bản ghi có `seq` và CRC-16. Bản ghi rách hoặc cũ bị bỏ, không bao giờ được dùng.
- **Cache:**
  - MCU gọi `HAL_DCACHE_CleanByRange` sau khi ghi và `HAL_DCACHE_InvalidateByRange` trước khi đọc (`hal_conf.h` bật `HAL_DCACHE_MODULE_ENABLED`).
  - Linux map `/dev/mem` với `O_SYNC`.
- **Chưa kiểm chứng trên board:** MCU có thật sự bật D-cache cho DDR không vẫn **UNKNOWN**; hàm invalidate/clean làm đúng trong cả hai trường hợp.
- **Kiểm thử:** unit test trong `mcu/tests/test_flight.c` (`test_ipc`), chuỗi đầy đủ trong `ground/test_chain.py`.
