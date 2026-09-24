# Build firmware MCU

Yêu cầu: đã chạy `./run.sh build` ít nhất một lần (tạo image `luckfox-build:22.04` và volume `luckfox-src`).

```sh
tools/build_mcu.sh luckfox_mini-M1-NONE      # Milestone 1: hello + vòng lặp 1 kHz, chạy ở 0x01800000
tools/build_mcu.sh luckfox_mini-HELLO-NONE   # hello world ở vị trí mặc định 0x40000 (không chạy song song Linux được)
tools/build_mcu.sh rv1106_evb-SC3338-ADC     # board mẫu của Rockchip, nguyên bản
```

Script làm:
1. Lần đầu tạo image `luckfox-build:22.04-mcu` = image gốc + `scons` (image gốc không bị sửa).
2. Chép `mcu/bsp/<board>` và `shared/ipc/*.h` vào `BSP/board/<board>` trong volume SDK.
3. Nếu board có `mcu_region.env`: kiểm tra địa chỉ khớp `shared/ipc/mcu_layout.h` và `CONFIG_PERSISTENT_RAM_ADDR`,
   rồi tạm đổi `ORIGIN` trong `BSP/link.lds`. Bản gốc lưu ở `link.lds.sdk` và được trả lại khi build xong, kể cả khi lỗi.
4. Chạy đúng lệnh SDK: `./build.sh mcu <board>` (`project/build.sh:876-919`).
5. Chép `rtthread.{bin,elf,map}` ra `out/mcu/<board>/`, log vào `logs/mcu_<board>.log`.

Tên board phải có dạng `Board-Sensor-LightSensor` (3 phần ngăn bởi `-`), nếu không `mcu/build.sh lunch` báo "Not found".

Kết quả đã kiểm tra:

| Board | `rtthread.bin` | text / data / bss | entry |
|---|---|---|---|
| luckfox_mini-M1-NONE | 22 072 B | 21 883 / 160 / 223 688 | 0x1800200 |
| luckfox_mini-HELLO-NONE | 18 256 B | 18 080 / 148 / 227 504 | 0x40200 |
| rv1106_evb-SC3338-ADC | 114 516 B | | 0x40200 |

`bss` lớn vì heap trải hết phần còn lại của vùng 0x3C000 (`link.lds:117`, `HEAP_SIZE`).

Cấu trúc board tối thiểu: `SConscript`, `Kconfig`, `defconfig`, `board.c`, `board.h`, `iomux.c`, `iomux.h`
(`BSP/board/SConscript` nạp `board/$RT_BOARD_NAME/SConscript`). Board cần `CONFIG_RT_USING_PIN=y`, vì
`board/common/iomux_base.c` và `board_cam.c` luôn được biên dịch và cần HAL GPIO.

Công cụ Linux: `tools/build_linux_tools.sh` build `linux/mcu-tool` bằng toolchain `arm-rockchip830-linux-uclibcgnueabihf` của SDK → `out/linux-tools/mcu-tool`.
