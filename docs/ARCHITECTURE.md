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

Tài liệu đầy đủ có sơ đồ: [architecture.html](architecture.html) (phần cứng, phân chân, phần mềm, IPC, failsafe, bộ nhớ, rủi ro, phương án B).

Mục tiêu: một chip RV1103, Linux trên Cortex-A7 lo camera, AI, mạng; HPMCU chạy vòng điều khiển bay.
Trạng thái: **NOT YET DEMONSTRATED**. Milestone 1 PASS: MCU chạy 1 kHz cùng Linux, 0 lỡ chu kỳ trên 2 000 000 vòng,
jitter 18,2 µs khi idle và 116,7 µs khi camera chạy ([REALTIME.md](REALTIME.md)).

| Miền | Phần cứng (đề xuất) | Phần mềm (đề xuất) |
|---|---|---|
| MCU | SPI0 (chân 6–9, CS1 chân 14): IMU ICM-42688-P + barometer; PWM2 kênh 8–11 (chân 10, 11, 16, 17): 4 ESC | RT-Thread: ctrl_rate 1 kHz, ctrl_att 250 Hz, ctrl_alt 100 Hz, safety 100 Hz, comms 100 Hz, blackbox |
| Linux | CSI camera; UART3 (chân 12/13): module LTE + GNSS Lierda NT26-KCN E; chân 18 / 20: RESET / BOOT của module; SARADC IN0 (chân 19): áp pin; USB host: Wi-Fi | vision, flight-manager, telemetry + web, blackbox-writer, mcu-loader, lte-loader (nạp firmware Lierda) |
| Chung | DDR: MCU 0x01800000 (256 KB, đã chạy) + IPC 0x01840000 (256 KB, đề xuất) | vòng đệm SPSC + polling (không có mailbox driver, không có RPMsg cho RV1106) |

Những điểm có thể buộc phải dùng MCU điều khiển bay rời (phương án B):

| Vấn đề | Bằng chứng | Ảnh hưởng |
|---|---|---|
| HAL MCU không có SPI, không có UART | `hal_bsp.c` chỉ có I2C0–4, PWM0–2, UART0/2 | phải tự viết mô tả thiết bị + kiểm clock |
| Không thấy ngắt DMA trong bảng ngắt của MCU | `soc.h:53-94` | DShot bằng Timer+DMA có thể không làm được |
| Tải camera làm jitter MCU tăng 6,4 lần | [REALTIME.md](REALTIME.md) | phải đo thêm với NPU + Wi-Fi |
| Bộ thu RC (ELRS/CRSF) dùng UART2, đường RC đi qua Linux | [PERIPHERALS.md](PERIPHERALS.md#bộ-thu-rc-trên-uart2) | Linux treo = mất RC; MCU phải failsafe theo timeout. MCU tự đọc UART2 cần viết mã clock (UNKNOWN) |
| Không có RPMsg/mailbox driver cho RV1106 | [IPC.md](IPC.md) | IPC tự làm |
| Lỗi tick trong SDK | `timer.c:128`, chậm 0,1% | phải sửa trước khi chạy dài |

Quyết định giữ hay bỏ kiến trúc một chip chỉ đưa ra sau khi có số liệu của Milestone 2.
