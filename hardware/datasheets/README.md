# Datasheet (không lưu trong repo)

Datasheet là tài liệu có bản quyền của hãng, nên không đưa vào repo. Tải về bằng:

```sh
hardware/fetch_vendor.sh      # tải PDF từ trang chính thức, tạo bản .txt bằng pdftotext
```

Các file `.txt` là bản chữ trích từ PDF. Tài liệu trong repo trích dẫn số liệu theo tên file,
phiên bản và trang.

| File | Linh kiện | Nguồn chính thức |
|---|---|---|
| `TPS54360.pdf` | buck 5 V (U1), SLVSBB4G | https://www.ti.com/lit/ds/symlink/tps54360.pdf |
| `TPS54560B.pdf` | tham khảo cho buck | https://www.ti.com/lit/ds/symlink/tps54560b.pdf |
| `LM66100.pdf` | diode lý tưởng (U2), SLVSEZ8A | https://www.ti.com/lit/ds/symlink/lm66100.pdf |
| `TLV755P.pdf` | LDO 3,3 V cảm biến (U3) | https://www.ti.com/lit/ds/symlink/tlv755p.pdf |
| `BMP390.pdf` | barometer (U5) | https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp390-ds002.pdf |
| `ICM-42688-P_DS-000347_v1.7.pdf` | IMU (U4) | **tải tay**: https://invensense.tdk.com/products/motion-tracking/6-axis/icm-42688-p/ (link PDF trực tiếp của TDK trả về trang HTML, không tải bằng script được) |
| `../vendor/Luckfox-Pico-Mini.pdf` | sơ đồ nguyên lý Luckfox Pico Mini | https://github.com/LuckfoxTECH/Luckfox-Pico-docs (Hardware/Schematic) |
