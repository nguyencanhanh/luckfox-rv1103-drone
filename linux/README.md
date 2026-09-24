# Phía Linux

| Thư mục | Nội dung |
|---|---|
| `dts/rv1103g-luckfox-pico-mini-m1.dts` | DTS Mini gốc + `reserved-memory` cho MCU. Cài vào SDK bằng `tools/install_m1.sh` |
| `mcu-tool/` | nạp/dừng MCU, đọc log và kết quả benchmark qua `/dev/mem`. Build: `tools/build_linux_tools.sh` |
| `dts/sdk/` | bản sao DTS của SDK **chỉ để đọc**, không nằm trong git. Tạo lại: `tools/extract_sdk_ref.sh` |

## Chuỗi include của Luckfox Pico Mini

```
rv1103g-luckfox-pico-mini-m1.dts   (repo)
└── rv1103g-luckfox-pico-mini.dts
    ├── rv1103.dtsi → rv1106.dtsi
    ├── rv1106-evb.dtsi
    └── rv1103-luckfox-pico-ipc.dtsi
        └── rv1106-amp.dtsi        node rockchip,amp: giữ clock MCU bật
```
