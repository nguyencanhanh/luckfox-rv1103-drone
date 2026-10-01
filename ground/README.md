# Điều khiển từ xa + camera

![Trạm mặt đất bay drone mô phỏng](../docs/img/gcs.jpg)

```
trạm mặt đất (Mac, ground/gcs.py + trình duyệt)
   │  lệnh lái: khung CRSF qua UDP 7700, 50 Hz          ▲ telemetry CRSF 20 Hz      ▲ video MJPEG
   ▼                                                     │                           │
rc-bridge (Linux trên drone, linux/rc-bridge) ──────────┘                    ffmpeg ◄── RTSP H.265
   │  ưu tiên: bộ thu ELRS (UART2, CRSF 420000) > mạng > không gì (= failsafe)        rkipc (camera SC3336)
   ▼  vòng đệm fc_ipc trong RAM chung (trang 4 KB tại MCU_IPC_BASE = 0x0183F000)
MCU: fc_link → fc_step (code bay) → telemetry ngược lên
```

| Thành phần | File | Chạy ở đâu |
|---|---|---|
| Kênh Linux ↔ MCU | `shared/ipc/fc_ipc.{h,c}`: 2 vòng đệm SPSC, seq, CRC-16, xử lý cache phía MCU | MCU, Linux, máy tính |
| Phía MCU | `mcu/link/fc_link.{h,c}`: RC → `rc_map` → `fc_rc_input`, telemetry 50 Hz | MCU, mô phỏng |
| Phía Linux | `linux/rc-bridge/`: chọn nguồn lệnh, chuyển tiếp, telemetry về tay điều khiển và trạm mặt đất | board (ARM), máy tính |
| Trạm mặt đất | `ground/gcs.py` + `ground/web/index.html` | Mac |
| Camera | `rkipc` có sẵn trong firmware: RTSP cổng 554, `/live/0` 2304×1296 và `/live/1` 704×576 H.265 (`rkipc/common/rtsp/rtsp.c:23`, `src/rv1103_ipc/video/video.c:38-40`, `rkipc-300w.ini`) | board |

## Thử ngay trên Mac (drone mô phỏng)

```sh
make -C simulator && make -C linux/rc-bridge
python3 simulator/server.py --ipc /tmp/lfx_ipc.bin              # "MCU": code bay + vật lý
linux/rc-bridge/build/rc-bridge --shm /tmp/lfx_ipc.bin          # "Linux của drone"
python3 ground/gcs.py --drone 127.0.0.1 --video sim             # trạm mặt đất
# mở http://127.0.0.1:8780
```

Cả 3 lệnh chạy ở 3 cửa sổ terminal riêng. Video lúc này là góc nhìn FPV của mô phỏng.

## Trên board thật (khi cắm board)

```sh
tools/build_mcu.sh luckfox_mini-FC-NONE && tools/build_linux_tools.sh   # một lần
tools/run_drone_remote.sh                                               # nạp MCU, chạy rc-bridge
python3 ground/gcs.py --drone 172.32.0.93 --video rtsp://172.32.0.93/live/1
```

Lúc này MCU vẫn chạy với **cảm biến giả** (chưa có driver IMU) và **không có đầu ra motor**. Nghĩa là đang thử
đường lệnh, telemetry và camera thật, không phải bay thật. `tools/run_drone_remote.sh stop` để dừng.

## Lái

| Phím | Việc |
|---|---|
| `U` | mở / đóng **khóa ARM** của trạm mặt đất (đóng thì kênh ARM luôn thấp) |
| `Space` | công tắc ARM |
| `1` `2` `3` | ANGLE / ALT HOLD / ACRO |
| `W` `S`, `H` | ga, ga giữa |
| `A` `D`, `↑↓←→` | xoay, lái |

Tay điều khiển EdgeTX/ELRS cắm USB (chế độ joystick) được nhận tự động. Thứ tự kênh AETR, AUX1 = ARM, AUX2 = chế độ.

## An toàn

- **Trang trạm mặt đất đóng hoặc treo:** server ngừng gửi lệnh sau 0,2 s. Drone tự failsafe: giữ thăng bằng → tự hạ cánh
  → tắt motor (`ground/test_chain.py` kiểm tra đúng điều này).
- **Thời gian cho phép hạ cánh tính theo độ cao lúc mất sóng.** Lỗi cũ: giới hạn cứng 20 s sẽ tắt motor giữa trời
  nếu mất sóng ở trên khoảng 14 m. Đã sửa, có kịch bản `rc_loss_high` (30 m) chặn lỗi này.
- **Bộ thu ELRS luôn được ưu tiên hơn mạng.** `rc-bridge` không bao giờ lặp lại lệnh cũ; im lặng chính là tín hiệu failsafe.
- **Mở khóa ARM chỉ cho phép, không tự ARM.** Code bay vẫn đòi đủ điều kiện: gạt công tắc, ga 0, đã hiệu chuẩn,
  drone nằm thẳng.

## Kiểm thử

```sh
python3 ground/test_chain.py      # trạm mặt đất → UDP → rc-bridge → IPC → code bay → telemetry
python3 ground/crsf.py            # CRSF Python (CRC-8/DVB-S2, đóng gói kênh)
```

Kết quả 2026-10-01: 7/7. Gồm: telemetry về, nguồn lệnh "mạng", khóa ARM chặn đúng, ARM sau khi mở khóa, cất cánh
và giữ độ cao, độ cao trong telemetry khớp, trạm mặt đất im lặng thì drone failsafe → hạ cánh → tắt motor.
Video: đoạn H.265 704×576 25 fps (giống `/live/1`) ra trình duyệt đủ 25 hình/giây.

## Giới hạn hiện tại (chưa kiểm chứng trên board)

- **Mạng:** hiện chỉ có cáp USB (USB-ECM, 172.32.0.93), tức là "từ xa" bằng dây. Muốn Wi-Fi thì phải chuyển USB-C sang host
  và cắm USB Wi-Fi; khi đó mất ADB/ECM. **UNKNOWN.**
- **Điều khiển từ xa thật sự (tầm xa)** phải qua bộ thu ELRS. Cần chuyển console Linux khỏi UART2 (sửa DTS, nạp lại
  firmware), rồi chạy `rc-bridge --devmem --uart /dev/ttyS2`. Tên thiết bị `/dev/ttyS2` lúc đó: UNKNOWN.
- **Độ trễ video RTSP → trình duyệt chưa đo.** Tắt bộ đệm (`-fflags nobuffer`) có dùng; `-flags low_delay` làm hỏng
  giải mã HEVC trong lần thử offline nên chưa bật.
- **Khung pin CRSF (0x08) chưa gửi:** đơn vị điện áp trong đặc tả chưa xác nhận được.
- **Telemetry RSSI/LQ của ELRS** chỉ có khi bộ thu gửi LINK_STATISTICS.
