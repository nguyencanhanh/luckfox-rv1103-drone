# HPMCU của RV1103: bằng chứng (Phase 0 + Phase 2)

SDK: LuckfoxTECH/luckfox-pico `main` @ `824b817f889c2cbff1d48fcdb18ab494a68f69d1` (xem `SDK_VERSION`).
Đường dẫn tính từ gốc SDK. Viết tắt:
`MCU/` = `sysdrv/source/mcu/rt-thread/`, `BSP/` = `MCU/bsp/rockchip/rv1106-mcu/`, `HAL/` = `MCU/bsp/rockchip/common/hal/lib/`,
`UB/` = `sysdrv/source/uboot/u-boot/`, `K/` = `sysdrv/source/kernel/`, `DTS/` = `K/arch/arm/boot/dts/`.
**TEST** = đo trên board Luckfox Pico Mini B chạy firmware stock (2026-09-23).

## 1. Câu hỏi Phase 0

| Câu hỏi | Kết luận | Nguồn (file:dòng) | Giải thích |
|---|---|---|---|
| Nhân MCU | RISC-V 32-bit, `rv32imc`, ABI `ilp32`, lõi Syntacore SCR1 | `BSP/rtconfig.py:38`; thư mục `MCU/libcpu/risc-v/scr1/`; ELF đã build: "RISC-V, RVC, soft-float" | cờ biên dịch và port CPU mà BSP dùng |
| Clock MCU | 297 MHz | `BSP/drivers/timer.h:34`; TEST `clk_core_mcu` = 297 MHz | kernel khai báo `clk_core_mcu` từ gpll/24M, không critical (`K/drivers/clk/rockchip/clk-rv1106.c:335-337`) |
| SRAM riêng | 8 KB `hpmcu_sram` @ 0xFF6FE000 | `DTS/rv1106.dtsi:1140,1149` | nằm trong system_sram 0xFF6C0000; MCU có chạy code từ đây không: **UNKNOWN — NEED VERIFICATION** |
| RAM chạy code | DDR, SDK mặc định 0x40000, dài 0x3C000 | `BSP/link.lds:5` | firmware chạy trong DDR chung với Linux |
| RT-Thread | 3.1.3 | defconfig `CONFIG_RT_VER_NUM=0x30103` | |
| Toolchain | xPack `riscv-none-embed-gcc` 10.2.0 | `sysdrv/source/mcu/prebuilts/gcc/linux-x86/riscv64/`; tải bởi `project/build.sh:883-894` | |
| Lệnh build | `./build.sh mcu <Board-Sensor-Light>` | `project/build.sh:876-919, 2764-2765` | tên board phải có đúng 3 phần ngăn bởi `-`, nếu không `mcu/build.sh lunch` báo "Not found" |
| Firmware ra ở đâu | `output/out/mcu_out/rtthread.bin` | `project/build.sh:57,70` | |
| MCU boot thế nào | SPL nạp ảnh FIT "standalone" tên `mcu0`, rồi: đặt vùng ngoại vi không cache, reset MCU, ghi `HPMCU_BOOT_ADDR`, nhả reset | `UB/common/spl/spl_fit.c:655-676` → `UB/arch/arm/mach-rockchip/rv1106/rv1106.c:548-566` | xem mục 2 |
| Linux và MCU chạy đồng thời? | Có cơ chế: node `rockchip,amp` giữ clock MCU bật | `DTS/rv1106-amp.dtsi`; include từ `DTS/rv1103-luckfox-pico-ipc.dtsi:5`; driver `K/drivers/soc/rockchip/rockchip_amp.c` (probe gọi `clk_bulk_prepare_enable`) | **chưa chứng minh bằng chạy thật** |

## 2. Đường khởi động MCU

| Bước | Bằng chứng |
|---|---|
| SPL của U-Boot trên Luckfox được build với `CONFIG_SPL_LOAD_FIT=y` | `UB/configs/luckfox_rv1106_uboot_defconfig:26` |
| Loader non-TB mà Luckfox dùng lấy SPL **build sẵn** `rv1106_spl_v1.02.bin`, không build từ source | `sysdrv/source/uboot/rkbin/RKBOOT/RV1106MINIALL.ini` (`FlashBoot=bin/rv11/rv1106_spl_v1.02.bin`) |
| SPL build sẵn đó có mã nhả MCU | `strings rkbin/bin/rv11/rv1106_spl_v1.02.bin` có `mcu0`, `mcu1`, `standalone`, `%s: start standalone fail, ret=%d` (chuỗi của `spl_fit.c:675`) |
| Đóng gói MCU vào FIT: `fit_args.sh -m0 <offset>` + file `mcu0.bin` | `UB/arch/arm/mach-rockchip/fit_args.sh:24,132`; `fit_nodes.sh:210-265` |
| `make.sh --mcu` chép thành `mcu.bin`, trong khi `fit_nodes.sh` đọc `mcu0.bin` | `UB/make.sh:215-216` | tên không khớp: đường `--mcu` **UNKNOWN — NEED VERIFICATION** |
| Đường chính thức của SDK: loader thunder-boot có mục `Hpmcu=` | `project/build.sh:697-723`; `rkbin/RKBOOT/RV1106MINIALL_SPI_NAND_TB.ini:20,22` | Luckfox Mini không dùng TB |

Repo này nạp MCU **từ Linux** bằng `linux/mcu-tool`, làm đúng 5 lệnh ghi của `rv1106.c:552-559` qua `/dev/mem`.
Linux có quyền ghi `CORE_SGRF` (thanh ghi secure) hay không: **UNKNOWN — NEED VERIFICATION**. Tool đọc lại và dừng nếu ghi không ăn.
Nếu không ghi được, dùng đường SPL FIT ở trên.

## 3. Thanh ghi điều khiển MCU

| Thanh ghi | Địa chỉ | Nguồn |
|---|---|---|
| `CORE_GRF_BASE` | 0xFF040000 | `UB/.../rv1106.c:23` |
| `CACHE_PERI_ADDR_START/END` | +0x24 / +0x28, giá trị 0xFF000 / 0xFFC00 | `rv1106.c:24-25,552-553`; HAL `rv1106.h:1180-1182` (trường 20 bit) |
| `CORE_SGRF_BASE` + `HPMCU_BOOT_ADDR` | 0xFF076000 + 0x44 | `rv1106.c:39,46` |
| `CORECRU_BASE` + `CORESOFTRST_CON01` | 0xFF3B8000 + 0xA04; giữ reset 0x001E001E, nhả 0x001E0000 | `rv1106.c:109-110,555,559`; HAL `rv1106.h:781` |
| SCR1 mtime | 0xFF1E0000 | `BSP/drivers/timer.h:19-25` |

## 4. Timer và đo thời gian

| Kết luận | Nguồn |
|---|---|
| Tick RT-Thread = mtime với bộ chia 1000, bước 297000/1000 = 297 đếm = 1 ms | `BSP/board/common/board_base.c:117`; `timer.c:135-147`; `timer.h:34-35` |
| Độ phân giải mtime ≈ 3,37 µs, quá thô để đo jitter | suy ra từ trên; ngữ nghĩa bộ chia (chia N hay N+1): **UNKNOWN** |
| **Lỗi trong SDK**: `timer_cmp.time_cmph + 1;` không có tác dụng, nửa trên thanh so sánh không bao giờ tăng | `BSP/drivers/timer.c:128` | khi 32 bit thấp của mtime tràn (≈ 2³²/297 kHz ≈ 4,0 h) tick có thể hỏng. **Phải kiểm tra trong bài test 6 h/24 h** |
| CSR `mcycle` được khai báo | `BSP/cpu/riscv_csr_encoding.h:863,1371` | lõi có bật bộ đếm hay không: **UNKNOWN**; firmware tự kiểm tra và lùi về mtime |

## 5. Ngoại vi MCU nhìn thấy

Bảng ngắt riêng của MCU nằm trong `#ifdef HAL_MCU_CORE` (`HAL/CMSIS/Device/RV1106/Include/soc.h:53`).
Chi tiết từng khối: [PERIPHERALS.md](PERIPHERALS.md).

| Khối | Có ngắt phía MCU | Driver RT-Thread có trong SDK | Dùng được trên Luckfox? |
|---|---|---|---|
| Mailbox | có (`soc.h:58-59`) | `hal_mbox.c` | chưa thử |
| SPI0/1 | có (`soc.h:75-76`) | `drv_spi.c` | UNKNOWN — cần thử |
| UART0–5 | có (`soc.h:77-82`) | `drv_uart.c`, nhưng HAL RV1106 chỉ có `g_uart2Dev` (`HAL/bsp/RV1106/hal_bsp.c:120`), **không có mã clock UART nào cho RV1106** | **không, nếu không tự viết mô tả thiết bị + clock** |
| PWM0–2 | có (`soc.h:83-88`) | `drv_pwm.c` | UNKNOWN — Milestone 4 |
| TIMER0–5 | có (`soc.h:89-94`) | `hal_timer.c` | UNKNOWN |
| DMA | **không thấy trong bảng ngắt MCU** | `drv_dwdma.c`, `hal_pl330.c` | UNKNOWN — NEED VERIFICATION |
| Watchdog | không thấy trong bảng ngắt MCU | `drv_wdt.c` | UNKNOWN |

## 6. Firmware của repo

| Board | Mục đích | Vị trí link | Kích thước |
|---|---|---|---|
| `mcu/bsp/luckfox_mini-HELLO-NONE` | hello world, bố cục mặc định SDK | 0x40000 (**xung đột kernel, không chạy được song song**) | 18 256 B |
| `mcu/bsp/luckfox_mini-M1-NONE` | Milestone 1: hello mỗi giây + vòng lặp 1 kHz | 0x01800000 (đề xuất, [MEMORY_MAP.md](MEMORY_MAP.md)) | 22 072 B, heap trống ≈ 124 KB |

Build lại board mẫu của Rockchip `rv1106_evb-SC3338-ADC` cho 114 516 B, **cùng kích thước nhưng khác 60 184 byte**
so với bản build sẵn trong SDK. Chưa rõ nguyên nhân, không coi là build tái lập từng byte.
