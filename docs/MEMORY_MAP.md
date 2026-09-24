# Memory map liên quan tới HPMCU

Viết tắt như [RV1103_MCU.md](RV1103_MCU.md). Không có địa chỉ nào được chọn mà không nêu lý do và cách kiểm chứng.

## DDR 64 MB (0x0000_0000 – 0x03FF_FFFF), ai dùng gì lúc boot

| Vùng | Người dùng | Nguồn |
|---|---|---|
| 0x0 – 0x28000 | SPL (code) | `UB/include/configs/rv1106_common.h:37-38` |
| 0x1FE000 – 0x21E000 | SPL bss + stack | `rv1106_common.h:39-41` |
| 0x200000, 178 KB | U-Boot (ảnh FIT) | `rv1106_common.h:22`; `dumpimage -l images/uboot.img` |
| 0x8000 → | kernel được nạp (`kernel_addr_r`) | `rv1106_common.h:81` |
| 0x8000 – 0x78C364 | kernel sau khi chạy (`_text` … `_end`) | `K/arch/arm/Makefile:141` (textofs 0x8000), `objs_kernel/System.map` (`_text=b0008000`, `_end=b078c364`), `CONFIG_AUTO_ZRELADDR=y` |
| 0xC00000 | DTB (`fdt_addr_r`) | `rv1106_common.h:79` |
| 0xE00000 / 0xE00800 | ramdisk / `CONFIG_SYS_LOAD_ADDR` (boot.img, phân vùng 4 MB) | `rv1106_common.h:25,82`; `BoardConfig…Mini-IPC.mk:38` |
| gần đỉnh RAM | U-Boot sau relocate (malloc 16 MB) | `rv1106_common.h:15`; địa chỉ thật: **UNKNOWN**, đọc bằng `bdinfo` |
| động | CMA 24 MB của Linux | TEST `/proc/meminfo` |

## ⚠ Vùng MCU mặc định 0x40000 nằm trong kernel

`BSP/link.lds:5` đặt MCU ở 0x40000–0x7BFFF, log ở 0x7C000 (`BSP/rtconfig.h:272-273`).
Kernel chiếm 0x8000–0x78C364, **chứa trọn vùng này**. Nếu MCU chạy ở 0x40000 thì kernel ghi đè code MCU, hoặc MCU ghi đè kernel.

Chính `DTS/rv1106-thunder-boot.dtsi:22-24` của Rockchip cũng khai báo `rtos@40000`. Mình chưa giải thích được thiết kế TB
sống chung với kernel ở 0x8000 thế nào: **UNKNOWN — NEED VERIFICATION**. Kết luận cho repo: **không dùng 0x40000**.

## Vùng MCU của repo (ĐỀ XUẤT, chưa kiểm chứng trên board)

Nguồn duy nhất: `shared/ipc/mcu_layout.h`. Các chỗ phải khớp được `tools/build_mcu.sh` kiểm tra khi build.

| Vùng | Địa chỉ | Kích thước | Dùng cho |
|---|---|---|---|
| code + data + heap | 0x0180_0000 | 0x3C000 | `rtthread.bin` (entry 0x1800200) |
| log | 0x0183_C000 | 0x3000 | vòng đệm `drv_pstore.c` (`CONFIG_PERSISTENT_RAM_ADDR`) |
| benchmark | 0x0183_F000 | 0x1000 | `struct mcu_bench_shared` |

Lý do chọn 0x01800000: nằm ngoài mọi vùng đã liệt kê ở bảng trên (trên boot.img ≤ 0x1200800, dưới vùng U-Boot relocate).
Được Linux chừa ra bằng `reserved-memory … no-map` trong `linux/dts/rv1103g-luckfox-pico-mini-m1.dts`.

Kiểm chứng trên board (bắt buộc trước khi tin): xem [MILESTONE1.md](MILESTONE1.md) mục kiểm tra.
1. `/proc/device-tree/reserved-memory/mcu@1800000/reg` = `01800000 00040000`.
2. `/proc/iomem`: không có "System RAM" phủ 0x01800000–0x0183FFFF.
3. U-Boot `bdinfo`: `relocaddr` và vùng malloc nằm trên 0x01840000.
4. `mcu-tool load` đọc lại khớp từng byte.

## SRAM và thanh ghi

| Vùng | Địa chỉ | Nguồn |
|---|---|---|
| system_sram | 0xFF6C0000, 256 KB | `DTS/rv1106.dtsi:1140` |
| hpmcu_sram | 0xFF6FE000, 8 KB | `DTS/rv1106.dtsi:1149` |
| Mailbox (A7↔MCU) | 0xFF5C0000 | `DTS/rv1106.dtsi:1116` |
| PMU mailbox | 0xFF378000 | `DTS/rv1106.dtsi:666` |
| INT_MUX | 0xFF5D0000 | `BSP/drivers/int_mux.h:20` |

Thanh ghi điều khiển MCU: [RV1103_MCU.md §3](RV1103_MCU.md).
