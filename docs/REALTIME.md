# Benchmark vòng lặp 1 kHz trên MCU

Code: `mcu/bsp/luckfox_mini-M1-NONE/rt_bench.c`. Chưa được gọi hệ thống là hard-real-time.

## Kết quả

| Kịch bản | Log | n | missed | overrun | period min / avg / max (µs) | jitter max | P50 / P95 / P99 / P99.9 / P99.99 (µs) | latency avg / P99 / P99.99 / max (µs) |
|---|---|---|---|---|---|---|---|---|
| Firmware mặc định: `rkipc` chạy (camera + ISP + encoder), load 11,3 | `logs/m1_run1_rkipc.txt` | 1 000 000 | 0 | 0 | 894,7 / 1000,999 / 1116,7 | 116,7 µs | 1001,25 / 1010,0 / 1021,25 / 1053,0 / 1099,75 | 9,1 / 21,6 / 63,7 / 107,1 |

- Chu kỳ trung bình 1,000999 ms thay vì 1 ms: tick RT-Thread của SDK chậm 0,1% (xem [RV1103_MCU.md §4](RV1103_MCU.md)).
- Percentile là cận trên của ô histogram (250 ns cho period, 100 ns cho latency).
- 9 mẫu latency vượt 100 µs (`hist overflow`).

## Cách đo

```
tick mtime (1 ms) ──ISR──► hard timer RT-Thread ──► ghi t_isr, rt_sem_release
                                                     │
thread "bench" (ưu tiên 1, cao nhất của ứng dụng) ◄──┘ rt_sem_take → ghi t_wake
```

| Đại lượng | Định nghĩa |
|---|---|
| period | `t_wake[i] − t_wake[i−1]`, mục tiêu 1 000 000 ns |
| jitter | `max |period − 1 ms|` |
| latency | `t_wake − t_isr` (từ callback trong ngắt tới lúc thread chạy) |
| missed | period > 1,5 ms |
| overrun | khi thread thức dậy semaphore vẫn còn token, tức là đã có thêm tick trong lúc thread chưa chạy |
| P50…P99.99 | từ histogram: period ô 250 ns trong 0–2,5 ms; latency ô 100 ns trong 0–100 µs. Giá trị báo cáo là **cận trên của ô**. Mẫu vượt khoảng tính vào `hist_overflow` |

- Nguồn thời gian: `mcycle` (≈ 3,37 ns) nếu bộ đếm này chạy, không thì `mtime` (≈ 3,37 µs, kết quả thô). `mcu-tool status` in rõ đang dùng nguồn nào.
- Tần số danh nghĩa 297 MHz lấy từ `timer.h:34`. `mcu-tool clock` đo lại tần số bộ đếm theo `CLOCK_MONOTONIC` của Linux.
- Mỗi lần chạy = 1 000 000 vòng (≈ 16,7 phút), xong thì chạy tiếp. Mỗi lần chạy xong in kết quả vào log và `last`.
- Trong lúc chạy, thread báo cáo tắt ngắt khoảng vài chục chu kỳ để chép số liệu. Việc này nằm trong kết quả đo.

## Những gì có thể làm sai kết quả

| Rủi ro | Nguồn | Xử lý |
|---|---|---|
| Nhịp đo chính là tick mtime: sai số tần số tick không lộ ra ở period nếu đo bằng cùng clock | thiết kế | `mcu-tool clock` so với đồng hồ Linux |
| Lỗi `timer.c:128`: sau ≈ 4 h tick có thể hỏng | [RV1103_MCU.md §4](RV1103_MCU.md) | chạy ≥ 6 h và theo dõi `heartbeat` |
| `drv_gpio.c` unmask ngắt GPIO trên MCU, ta mask lại ở `INIT_DEVICE_EXPORT` | `board.c` | có một khoảng hở ngắn lúc boot |
| MCU không có UART, `rt_kprintf` chỉ ghi RAM | [PERIPHERALS.md](PERIPHERALS.md) | log không ảnh hưởng timing qua UART |

## Kịch bản tải (mục 28 của kế hoạch, sau khi boot được)

1. Linux idle
2. + camera/ISP (`rkipc` mặc định của Luckfox)
3. + NPU
4. + encode video
5. + lưu lượng mạng (USB-ECM, `iperf3` nếu có)

Mỗi kịch bản ≥ 1 lần chạy đủ 1 000 000 vòng. Ghi `mcu-tool status` + `mcu-tool clock` vào `logs/`.
