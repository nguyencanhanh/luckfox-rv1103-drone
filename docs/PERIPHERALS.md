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

## Chân trên header của Luckfox Pico Mini

Nguồn: ảnh sơ đồ chân của Luckfox (`Luckfox-Pico-Mini-details-inter.jpg`, người dùng cung cấp 2026-09-24),
đối chiếu với `rv1106-pinctrl.dtsi`. "Khớp" = ảnh và DTS cùng nói một chức năng cho chân đó.

| Chân | GPIO | Chức năng dùng tới | Đối chiếu DTS |
|---|---|---|---|
| 2, 21 | GND | | |
| 3 | 3V3 (ra) | | |
| 4 | GPIO1_B2 | **UART2_TX_M1: console Linux** | khớp: `rv1106-pinctrl.dtsi:998-999`, UART2 dùng M1 `rv1106.dtsi:1010` |
| 5 | GPIO1_B3 | **UART2_RX_M1: console Linux** | khớp: `rv1106-pinctrl.dtsi:996-997` |
| 6–9 | GPIO1_C0–C3 | SPI0_M0 CS0/CLK/MOSI/MISO; hoặc PWM2/4/5/6_M2 | SPI khớp `:834-848`; PWM mux 3 `:494,540,563,586` |
| 10 | GPIO1_C4 | UART4 (M1); hoặc PWM8_M1 | PWM `:625`; **hướng UART lệch**: ảnh ghi TX, DTS ghi `uart4_rx_m1` (`:1036-1037`) |
| 11 | GPIO1_C5 | UART4 (M1); hoặc PWM9_M1 | PWM `:641`; ảnh ghi RX, DTS ghi `uart4_tx_m1` (`:1038-1039`) |
| 12 | GPIO1_D0 | UART3_TX_M1 | khớp `:1018-1019` |
| 13 | GPIO1_D1 | UART3_RX_M1 | khớp `:1016-1017` |
| 14, 15 | GPIO1_D2, D3 | I2C3_M1 SDA/SCL | |
| 18 | GPIO0_A4 | PWM1_M0 (ảnh không ghi) | `:454-457` |

Hướng TX/RX của UART4_M1: **UNKNOWN — NEED VERIFICATION** (ảnh và DTS nói ngược nhau). Đo bằng máy hiện sóng trước khi dùng.

Các chân PWM khác mà ảnh không ghi, tra từ `rv1106-pinctrl.dtsi`:
chân 12 PWM3_M2 (`:514`), 13 PWM10_M2 (`:661`), 14 PWM0_M1 (`:445`), 15 PWM11_M2 (`:684`),
16 PWM10_M1 (`:654`), 17 PWM11_M1 (`:677`), 20 PWM1_M1 (`:461`).

`spi0_cs1n_m0` là GPIO1_D2 = **chân 14** (`:852-855`); ảnh ghi CS1 ở chân 15. **Lệch giữa ảnh và DTS**, theo DTS.

**PWM cho ESC x4 (đề xuất):** PWM8/9/10/11_M1 ở chân 10, 11, 16, 17. Cả 4 kênh thuộc cùng bộ PWM @ 0xFF490000,
chính là `g_pwm2Dev` trong HAL MCU (`hal_bsp.c:99-105`, `rv1106.h:790`). Không trùng chân SPI0 (6–9).

## Điều kiện để MCU dùng một khối

1. **Linux không bind driver**: giữ `status = "disabled"`.
2. **Clock không bị Linux tắt**: kernel tắt mọi clock không ai dùng lúc khởi động xong (`clk_disable_unused`).
   Phải thêm clock của khối đó vào node `rockchip,amp` (`DTS/rv1106-amp.dtsi`). Driver `rockchip_amp.c` bật và giữ mọi clock trong danh sách.
3. **MCU có ngắt**: có trong bảng `HAL_MCU_CORE` (`soc.h:53-94`).
4. **HAL có mô tả thiết bị + mã clock cho RV1106**: UART thì **không** (`hal_bsp.c:120` chỉ có UART2; không có `CLK_UART*` nào cho RV1106).
   PWM0–2 và I2C0–4 **có** (`hal_bsp.c:28-107`). **SPI không có** mô tả thiết bị. DMA: **UNKNOWN**.

## UART debug cho MCU

Không có đường chính thức (điều kiện 4). Milestone 1 dùng vòng đệm log trong RAM (`drv_pstore.c`), đọc bằng `mcu-tool log`.
Muốn UART thật cho MCU thì phải tự viết driver polled cho UART3 (DW 8250) và kiểm clock `SCLK_UART3` trên board. Đây là việc riêng, chưa làm.
