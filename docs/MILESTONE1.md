# Milestone 1: Linux + RT-Thread trên HPMCU + vòng lặp 1 kHz

## Trạng thái (2026-09-24)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Stock SDK build | **PASS** | `logs/sdk_build.log`; ảnh trong `images/` (build 2026-09-23) |
| Linux boot | **PASS** (firmware stock) | TEST 2026-09-23: SSH, `/proc/cpuinfo`, `clk_summary` |
| RT-Thread firmware build | **PASS** | `tools/build_mcu.sh luckfox_mini-M1-NONE` → 22 072 B, entry 0x1800200 |
| Linux M1 (DTS có reserved-memory) build | **một phần**: DTB build được qua kbuild; `boot.img` M1 chưa build | `objs_kernel/.../rv1103g-luckfox-pico-mini-m1.dtb` 72 712 B |
| MCU firmware boot | **CHƯA THỬ**: board chưa cắm | |
| UART debug | **Linux: có (UART2). MCU: KHÔNG CÓ** trong SDK cho RV1106, thay bằng log trong RAM | [PERIPHERALS.md](PERIPHERALS.md) |
| Vòng lặp 1 kHz chạy | **CHƯA THỬ** | |
| Đo jitter | **CHƯA CÓ SỐ LIỆU** | |

Milestone 1: **NOT YET DEMONSTRATED**.

## Cần có

- Board Luckfox Pico Mini B, cáp USB-C truyền dữ liệu.
- (Nên có) USB-UART **3,3 V** để xem console U-Boot và Linux trên UART2, **115200 8N1** (`rv1106.dtsi:227,230`):

  | USB-UART | Chân board |
  |---|---|
  | RX | 4 (GPIO1_B2, UART2_TX_M1) |
  | TX | 5 (GPIO1_B3, UART2_RX_M1) |
  | GND | 2 hoặc 21 |
  | VCC | **không nối**, board cấp nguồn qua USB-C |

  Trên Mac: `screen /dev/cu.usbserial-* 115200` (thoát: Ctrl-A rồi K). Nguồn chân: [PERIPHERALS.md](PERIPHERALS.md).

## 1. Build (trên Mac)

```sh
orb start                                   # nếu Docker engine đang tắt
tools/build_mcu.sh luckfox_mini-M1-NONE     # → out/mcu/luckfox_mini-M1-NONE/rtthread.bin
tools/build_linux_tools.sh                  # → out/linux-tools/mcu-tool
tools/install_m1.sh                         # đưa DTS + BoardConfig M1 vào SDK
./run.sh board                              # chọn dòng ...Mini_M1-IPC
./run.sh build                              # build lại U-Boot + kernel + firmware, ảnh ra images/
```

`./run.sh build` xóa ảnh cũ trong `images/` rồi chép ảnh mới vào (đầu ra của repo nằm ở `out/`, không bị xóa).
Quay lại firmware stock: `./run.sh board` chọn lại `...Mini-IPC`, rồi `./run.sh build`.

## 2. Nạp firmware Linux

```sh
./run.sh flash       # vào chế độ nạp qua ADB, ghi mọi phân vùng; xóa dữ liệu trên board
./run.sh connect     # chờ board lên, gắn IP USB-ECM, mở SSH root@172.32.0.93
```

## 3. Kiểm tra vùng nhớ trước khi chạy MCU (bắt buộc)

```sh
B=root@172.32.0.93
ssh $B 'hexdump -C /proc/device-tree/reserved-memory/mcu@1800000/reg'   # phải là 01 80 00 00 00 04 00 00
ssh $B 'cat /proc/iomem'                                                # 0x01800000-0x0183ffff không thuộc System RAM
```
Trên console UART2, dừng U-Boot bằng phím bất kỳ rồi `bdinfo`: `relocaddr` phải > 0x01840000.
Sai bất kỳ điều nào thì **dừng**, không nạp MCU.

## 4. Nạp và chạy MCU (từ Linux)

```sh
cat out/mcu/luckfox_mini-M1-NONE/rtthread.bin | ssh $B 'cat > /tmp/rtthread.bin'
cat out/linux-tools/mcu-tool                 | ssh $B 'cat > /tmp/mcu-tool && chmod +x /tmp/mcu-tool'
ssh $B '/tmp/mcu-tool load /tmp/rtthread.bin'
ssh $B 'sleep 3; /tmp/mcu-tool log'          # phải thấy "bench: clock ..." và "Hello RV1103 MCU 0, 1, 2"
ssh $B '/tmp/mcu-tool status'
ssh $B '/tmp/mcu-tool clock 30'              # tần số bộ đếm MCU đo theo đồng hồ Linux
ssh $B '/tmp/mcu-tool stop'                  # giữ MCU ở reset
```

`mcu-tool load` sẽ từ chối nếu:
- device tree không có `reserved-memory/mcu@1800000` đúng địa chỉ và kích thước;
- đọc lại firmware trong DDR không khớp;
- Linux không ghi được `HPMCU_BOOT_ADDR` (thanh ghi secure). Khi đó MCU vẫn giữ reset, và phải chuyển sang đường nạp bằng SPL FIT ([RV1103_MCU.md §2](RV1103_MCU.md)).

## 5. Đo và lưu kết quả

Mỗi lần chạy 1 000 000 vòng mất khoảng 16,7 phút:
```sh
sleep 1080; ssh $B '/tmp/mcu-tool status; /tmp/mcu-tool clock 30' | tee logs/m1_idle.txt
```
Các kịch bản tải: [REALTIME.md](REALTIME.md).

## 6. Nếu không thấy log

| Triệu chứng | Nghĩa là |
|---|---|
| `vong dem log chua khoi tao` | MCU không chạy tới `pstore_dev_init`: không boot, sai địa chỉ, hoặc cache chưa được đẩy ra DDR |
| Log dừng ở `bench: probing mcycle` | đọc CSR `mcycle` gây lỗi trên lõi này; sửa `clock_select()` để chỉ dùng mtime |
| `heartbeat` không tăng | MCU treo hoặc tick không chạy |
| Linux treo hoặc panic sau `load` | vùng nhớ không thực sự trống: dừng, kiểm tra lại mục 3 |
