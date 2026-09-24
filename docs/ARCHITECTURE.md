# Kiến trúc: phần cứng đã xác minh và hướng đi

SDK: LuckfoxTECH/luckfox-pico `main` @ `824b817f889c2cbff1d48fcdb18ab494a68f69d1`. Đường dẫn tính từ gốc SDK.
"TEST" = đo trực tiếp trên board Luckfox Pico Mini B đang chạy firmware build từ SDK này (2026-09-23).

## SoC

| Mục | Giá trị | Nguồn |
|---|---|---|
| SoC | RV1103 (package 38x38, bản "G") | TEST: `/proc/device-tree/compatible` = `rockchip,rv1103g-38x38-ipc-v10 rockchip,rv1103` |
| DTS board | `rv1103g-luckfox-pico-mini.dts` | `project/cfg/BoardConfig_IPC/BoardConfig-SPI_NAND-Buildroot-RV1103_Luckfox_Pico_Mini-IPC.mk` (`RK_KERNEL_DTS`) |
| Họ chip | RV1106 (RV1103 dùng chung `rv1106.dtsi`, `RK_CHIP=rv1106`) | cùng file BoardConfig (`RK_CHIP=rv1106`); `rkdeveloptool rci` trả `36 30 31 31` ("1106" đảo byte) |

## Cortex-A7 (Linux)

| Mục | Giá trị | Nguồn |
|---|---|---|
| Kiến trúc | ARMv7, 1 nhân (`processor : 0`), rev 5 | TEST: `/proc/cpuinfo` |
| Clock hiện tại | 1104 MHz | TEST: `clk_summary` → `armclk 1104000000` |
| Các mức DVFS | 408 / 600 / 816 / 1104 MHz | TEST: `scaling_available_frequencies` |
| DDR | 64 MB, bắt đầu ở 0x0 | TEST: `/proc/device-tree/memory/reg` = `<0x0 0x04000000>` |
| RAM Linux dùng được | 32596 kB (MemTotal), CMA 24576 kB giữ cho camera/ISP | TEST: `/proc/meminfo` |
| GPU / framebuffer | không có | TEST: không có `/dev/dri`, `/dev/fb*`, `/dev/mali*` |
| NAND | 128 MB SPI NAND (SAMSUNG, block 128 KB, page 2 KB) | TEST: `rkdeveloptool rfi` |

## MCU phụ (HPMCU)

Bằng chứng đầy đủ: [RV1103_MCU.md](RV1103_MCU.md).

| Mục | Giá trị | Trạng thái |
|---|---|---|
| Nhân | RISC-V Syntacore SCR1, `rv32imc`, ilp32 | từ source (`rtconfig.py:38`) |
| Clock | 297 MHz | TEST (`clk_core_mcu`) + khớp `timer.h:34` |
| SRAM riêng | 8 KB (`hpmcu_sram`) | từ DTS; MCU có chạy code từ đây không: UNKNOWN |
| Vùng chạy code | DDR; SDK mặc định 0x40000 **nằm trong kernel**, repo dùng 0x01800000 (đề xuất) | [MEMORY_MAP.md](MEMORY_MAP.md) |
| Bộ điều khiển ngắt | SCR1 IPIC + INT_MUX 0xFF5D0000 | từ source |
| Timer hệ thống | SCR1 mtime @ 0xFF1E0000, bộ chia 1000 | `timer.c:135-147`; nguồn clock của mtime: UNKNOWN |
| Watchdog | không thấy trong bảng ngắt của MCU | UNKNOWN |

## Còn một MCU thứ hai?

HAL có thanh ghi `LPMCU_BOOT_ADDR` (`sysdrv/source/mcu/rt-thread/bsp/rockchip/common/hal/lib/CMSIS/Device/RV1106/Include/rv1106.h:52`)
và kernel có clock `clk_pmu_mcu` (TEST: 198 MHz, **đang tắt**). Nhiều khả năng có một MCU công suất thấp trong miền PMU.
SDK không có firmware hay luồng build nào cho nó. **Chưa xác minh**, không dùng cho tới khi có tài liệu.

## Hướng kiến trúc

Mục tiêu: một chip RV1103, Linux trên Cortex-A7 lo camera, AI, mạng; HPMCU chạy vòng điều khiển bay.
Trạng thái: **NOT YET DEMONSTRATED**. Chưa có lần nào MCU chạy cùng Linux trên board ([MILESTONE1.md](MILESTONE1.md)).

Những điểm đã thấy có thể buộc phải dùng MCU điều khiển bay rời (phương án dự phòng):

| Vấn đề | Bằng chứng | Ảnh hưởng |
|---|---|---|
| MCU không có UART trong HAL RV1106 | [PERIPHERALS.md](PERIPHERALS.md) | debug, GPS/ESC telemetry trên MCU phải tự viết driver |
| Không thấy ngắt DMA trong bảng ngắt của MCU | `soc.h:53-94` | DShot bằng Timer+DMA có thể không làm được từ MCU |
| PWM trên header trùng chân SPI0: dùng SPI0 cho IMU thì còn 3 kênh | [PERIPHERALS.md](PERIPHERALS.md) | ESC x4 cần 4 kênh |
| Không có RPMsg cho RV1106 | [IPC.md](IPC.md) | IPC phải tự làm |
| Lỗi tràn timer trong SDK | `timer.c:128` | phải sửa trước khi chạy dài |

Quyết định giữ hay bỏ kiến trúc một chip chỉ đưa ra sau khi có số liệu của Milestone 1 và 2.
