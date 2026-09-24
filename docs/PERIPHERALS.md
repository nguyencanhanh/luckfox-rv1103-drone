# Ngoại vi: ai sở hữu, MCU có dùng được không

Viết tắt như [RV1103_MCU.md](RV1103_MCU.md). "Linux bật" = `status = "okay"` trong DTS của Luckfox Pico Mini
(`DTS/rv1103g-luckfox-pico-mini.dts` + `DTS/rv1103-luckfox-pico-ipc.dtsi`).

## Linux đang dùng (không đưa cho MCU)

| Khối | Địa chỉ | DTS bật ở | Dùng cho |
|---|---|---|---|
| UART2 | 0xFF4C0000 | bootargs `earlycon=…0xff4c0000 console=ttyFIQ0` (`rv1103-luckfox-pico-ipc.dtsi:9`) | console Linux |
| I2C4 | 0xFF470000 | `rv1103-luckfox-pico-ipc.dtsi:168` | camera |
| MIPI CSI, ISP, VICAP | 0xFFA00000… | `rv1103-luckfox-pico-ipc.dtsi:120-301` | camera |
| NPU | 0xFF660000 | `rv1106-evb.dtsi:55` | AI |
| Encoder (rkvenc) | 0xFFA50000 | `rv1106-evb.dtsi:67-71` | video |
| USB (dwc3) | 0xFFB00000 | `rv1103g-luckfox-pico-mini.dts:55` | USB OTG / mạng ECM |
| SARADC | 0xFF3C0000 | `rv1103-luckfox-pico-ipc.dtsi:92` | |
| SFC (SPI NAND) | | `rv1103g-luckfox-pico-mini.dts:18` | lưu trữ |

## Khai báo nhưng Linux tắt: ứng viên cho MCU

| Khối | Địa chỉ | Chân (pinmux) | Nguồn |
|---|---|---|---|
| SPI0_M0 | 0xFF500000 | CLK GPIO1_C1, MOSI GPIO1_C2, MISO GPIO1_C3, CS0 GPIO1_C0 | `mini.dts:60-67`; `rv1106-pinctrl.dtsi:834-848`; `rv1106.dtsi:1059` |
| UART3_M1 | 0xFF4D0000 | TX GPIO1_D0, RX GPIO1_D1 (mux 5) | `mini.dts:77-80`; `rv1106-pinctrl.dtsi:1014-1019`; `rv1106.dtsi:1014` |
| UART4_M1 | 0xFF4E0000 | RX GPIO1_C4, TX GPIO1_C5 (mux 4) | `mini.dts:82-85`; `rv1106-pinctrl.dtsi:1034-1039`; `rv1106.dtsi:1029` |
| PWM1_M0 | 0xFF350010 | GPIO0_A4 | `mini.dts:87-91`; `rv1106-pinctrl.dtsi:454-457`; `rv1106.dtsi:580` |
| I2C3_M1 | 0xFF460000 | | `mini.dts:69-74`; `rv1106.dtsi:879` |

Chân GPIO nào ra header nào trên board: **UNKNOWN — NEED VERIFICATION** với sơ đồ chân Luckfox Pico Mini (Luckfox Wiki).
Mới có **một** kênh PWM được khai báo trên Mini; ESC x4 cần 4 kênh. Còn phải xem thêm các kênh PWM0–11 (`rv1106.dtsi:568-956`)
ở chân nào: UNKNOWN, để Milestone 4.

## Điều kiện để MCU dùng một khối

1. **Linux không bind driver**: giữ `status = "disabled"`.
2. **Clock không bị Linux tắt**: kernel tắt mọi clock không ai dùng lúc khởi động xong (`clk_disable_unused`).
   Phải thêm clock của khối đó vào node `rockchip,amp` (`DTS/rv1106-amp.dtsi`). Driver `rockchip_amp.c` bật và giữ mọi clock trong danh sách.
3. **MCU có ngắt**: có trong bảng `HAL_MCU_CORE` (`soc.h:53-94`).
4. **HAL có mô tả thiết bị + mã clock cho RV1106**: UART thì **không** (`hal_bsp.c:120` chỉ có UART2; không có `CLK_UART*` nào cho RV1106).
   SPI, PWM, DMA: chưa kiểm tra, **UNKNOWN**.

## UART debug cho MCU

Không có đường chính thức (điều kiện 4). Milestone 1 dùng vòng đệm log trong RAM (`drv_pstore.c`), đọc bằng `mcu-tool log`.
Muốn UART thật cho MCU thì phải tự viết driver polled cho UART3 (DW 8250) và kiểm clock `SCLK_UART3` trên board. Đây là việc riêng, chưa làm.
