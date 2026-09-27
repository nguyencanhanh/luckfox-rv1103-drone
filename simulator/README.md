# Mô phỏng bay (SITL) — 05-simulator

Chạy toàn bộ phần mềm bay trên máy Mac, không cần board, không cần motor.
Code bay trong `mcu/` (ước lượng góc, PID, mixer, failsafe) và `shared/rc/` (CRSF)
**chính là code sẽ build cho MCU**. Simulator chỉ thay phần cảm biến bằng `SIM_SENSOR`
và thay motor bằng mô hình vật lý (plan mục 26).

```
tay điều khiển / bàn phím ─► khung CRSF (như bộ thu ELRS gửi) ─► độ trễ link + Linux + IPC
    ─► crsf_parser ─► rc_map ─► fc_tick()  ◄── SIM_SENSOR (ICM-42688-P + BMP390 giả lập)
                                   │
                                   ▼ 4 số 0..1 (motor ảo)
                             mô hình quad 6 bậc tự do (4 kHz) ─► hiển thị 3D
```

![ALT HOLD trong 3D](../docs/img/sim/02_alt_hold_chase.jpg)

Thêm ảnh và biểu đồ: [README gốc](../README.md#mô-phỏng). Tạo lại ảnh: `tools/sim_screenshots.sh`,
biểu đồ: `python3 tools/plot_sim.py`.

## Chạy

```sh
make -C simulator            # build: unit test, sim_cli, libsim
make -C simulator test       # 66 unit test + 9 kịch bản bay × 2 profile cảm biến
make -C simulator e2e        # bấm phím thật vào trang 3D qua Chrome headless: cất cánh, bay, hạ cánh
make -C simulator run        # mở http://127.0.0.1:8777 để lái trong 3D
```

Chỉ cần `cc` và `python3` (thư viện chuẩn). Trang 3D tải three.js r128 từ cdnjs.

## Lái trong 3D

| Phím | Việc |
|---|---|
| `Space` | công tắc ARM (bật/tắt) |
| `1` / `2` / `3` | ANGLE (tự cân bằng) / ALT HOLD (giữ độ cao) / ACRO |
| `W` `S` | ga lên / xuống (giữ nguyên khi nhả, như cần ga thật) · `H` = ga giữa |
| `A` `D` | xoay mũi trái / phải |
| `↑` `↓` `←` `→` | chúi tới / lui, nghiêng trái / phải |
| `L` | cắt sóng RC → thử failsafe |
| `I` | hỏng IMU |
| `G` | gió 0 / 3 / 6 / 9 m/s |
| `C` | hiệu chuẩn cân bằng (drone đứng yên trên mặt phẳng) |
| `V` | camera: đuổi theo / người đứng dưới đất / FPV |
| `R` | reset |

Cách bay thử: `C` → chờ hết dòng "đang hiệu chuẩn" → `Space` (ARM) → giữ `W` tới ~0,65 cho
cất cánh → `2` (ALT HOLD) → `H` (ga giữa = giữ độ cao) → lái bằng các phím mũi tên.
Hạ cánh: ở ALT HOLD giữ `S` (xuống tối đa 1 m/s), chạm đất thì `Space`. Ở ANGLE mà hạ ga về 0 là rơi tự do, chạm
đất > 4 m/s thì bị tính là rơi: bấm `R` để đặt lại. Dòng gợi ý ở giữa phía trên màn hình luôn nói bước tiếp theo.

**Tay điều khiển thật:** radio EdgeTX / ELRS cắm USB ở chế độ joystick sẽ hiện ra như gamepad.
Trang tự nhận; bảng "Tay điều khiển USB" cho chọn trục và đảo chiều (mặc định AETR: trục 0–5
= roll, pitch, ga, yaw, ARM, chế độ). Mở thêm `http://127.0.0.1:8777/?watch` ở màn hình khác để
chỉ xem.

## Kịch bản tự kiểm (`build/sim_cli`)

| Kịch bản | Kiểm tra |
|---|---|
| `arm_refusal` | công tắc ARM bật sẵn lúc khởi động không arm; ga cao không arm; motor = 0 |
| `hover` | giữ độ cao 10 s: sai số < 0,3 m, nghiêng < 3°, ước lượng góc sai < 1° rms |
| `angle_step` | nghiêng 15°: 90 % trong < 0,4 s, vọt lố < 20 % |
| `yaw` | yaw đúng chiều (mũi sang phải), tốc độ đúng ±20 % |
| `rc_loss` | mất sóng: giữ thăng bằng sau 0,25 s, tự hạ sau 1 s nữa, chạm đất rồi tự disarm, không rơi |
| `imu_fail` | IMU chết giữa trời: tắt motor trong 20 ms |
| `wind` | gió 4,5 m/s + giật 2 m/s: độ cao sai < 1 m, nghiêng < 20° |
| `acro_flip` | lật 360° ở ACRO (400 °/s) rồi về ANGLE: tự cân bằng lại, ước lượng góc vẫn đúng |
| `alt_engage` | bật ALT HOLD khi đang lao lên 9 m/s: phanh rồi mới khóa độ cao, không vọt lên rồi tụt xuống |

`build/sim_cli --csv log.csv hover` ghi log 100 Hz; `--vib` thêm rung khung (giả định).

## Nguồn số liệu

| Thứ | Giá trị | Nguồn |
|---|---|---|
| Nhiễu gyro | 0,0028 °/s/√Hz | ICM-42688-P DS-000347 v1.7, tr. 11 |
| Lệch zero gyro | ±0,5 °/s | cùng bảng |
| Nhiễu accel | 65 (x, y) / 70 (z) µg/√Hz | cùng datasheet |
| Lệch zero accel | ±20 mg | cùng datasheet |
| Nhiễu áp suất | 2,0 Pa rms (standard, IIR tắt) | BMP390 datasheet, bảng 8 |
| Khung CRSF, CRC 0xD5, 420000 baud, failsafe "cut" | | [tbs-crsf-spec](https://github.com/tbs-fpv/tbs-crsf-spec/blob/main/crsf.md), [ExpressLRS](https://www.expresslrs.org/quick-start/receivers/wiring-up/) |
| Bộ lọc Mahony | | Mahony, Hamel, Pflimlin, IEEE TAC 2008; [ahrs docs](https://ahrs.readthedocs.io/en/latest/filters/mahony.html) |
| Mô hình động học, motor | T = Tmax·ω², trễ bậc 1 | [Gibiansky](https://andrew.gibiansky.com/blog/physics/quadcopter-dynamics/), [PX4 SITL motor model](https://github.com/PX4/sitl_gazebo/issues/110) |
| Lực cản rotor tuyến tính theo vận tốc gió | | Faessler, Franchi, Scaramuzza, RA-L 2018 |

**GIẢ ĐỊNH (chưa có khung thật):** khung ~0,6 kg, 225 mm, 6 N/motor, quán tính, lực cản,
chiều quay cánh (props-in), rung khung, độ trễ link 5 ms. Các hệ số PID được chỉnh trên mô hình
giả định này, **chỉ là điểm xuất phát, chưa phải bộ chỉnh cho drone thật**.

## Giới hạn đã biết

- Không có GPS / la bàn: không giữ vị trí (gió sẽ đẩy trôi), hướng mũi trôi theo gyro.
- Không có vận tốc từ GPS thì khi drone đang tăng tốc ngang, accelerometer không phân biệt được
  nghiêng với gia tốc: ở `angle_step` góc ước lượng lệch góc thật ~2° trong lúc tăng tốc. Hết khi có
  GPS (EKF, giai đoạn 3 của plan mục 9).
- Thời gian chạy trên Mac (`sim_cli --bench`) không nói gì về MCU: HPMCU là rv32imc **không có FPU**
  (`rtconfig.py:38`), mọi phép float là gọi hàm mềm. Phải đo trên board.
