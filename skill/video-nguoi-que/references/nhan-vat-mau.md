# Nhân vật mẫu — Pixar Boss (chốt 19/08/2026, thay thế bản người que)

**Ảnh gốc giữ nhân vật:** `567788a4-3391-4b4f-b0e4-a18a3974cffd`
**Dựng từ ảnh thật** (`NHT profile.png`) qua `ref_media_ids`, phong cách 3D Pixar/Disney.
**Kho ảnh:** `/Volumes/DATA/AI-APP/mascot-nguoi-que/nhan-vat-pixar/` (12 biểu cảm sẵn dùng)

## Đặc điểm đã chốt — PHẢI lặp lại trong mọi prompt để giữ đồng nhất
- Đầu hói, khuôn mặt đầy đặn (fuller/rounder build), phong thái "boss" tự tin
- Kính đen vuông gọng dày, sang trọng ("premium black rectangular thick-framed glasses")
- Vest đen, sơ mi trắng, **cà vạt đỏ tươi + khăn túi đỏ khớp màu nhau** (không phải trắng)
- Biểu cảm: sắc sảo/thông minh nhưng vẫn ấm áp, thân thiện ("sharp shrewd intelligent eyes
  paired with a warm genuine friendly smile")

## Công thức prompt nền (copy nguyên, chỉ đổi phần biểu cảm/tư thế)
```
3D Pixar-style animated character portrait of this exact man, same bald head, same premium
black rectangular thick-framed glasses, same facial identity, same slightly fuller confident
build, wearing a sharp black suit with bright red necktie and matching red pocket square,
Pixar/Disney animation studio character design, smooth rounded stylized features, soft warm
cinematic studio lighting, blurred modern office or neutral background, high quality 3D
render, no text. <MÔ TẢ BIỂU CẢM/TƯ THẾ>
```
Luôn truyền `ref_media_ids: ["567788a4-3391-4b4f-b0e4-a18a3974cffd"]`.

## 12 biểu cảm đã có (file trong nhan-vat-pixar/)
`01_cuoi_am` `02_cuoi_lon` `03_ngac_nhien` `04_suy_nghi` `05_gio_ngon_cai` `06_vay_chao`
`07_nghiem_tuc` `08_cuoi_tinh_nghich` `09_tu_hao` `10_dong_y` `11_chi_tay` `12_thanh_cong`

## Lưu ý
- AI luôn tự thêm dấu sao lấp lánh góc dưới — muốn bỏ thì thêm `no sparkle, no glow effect`
- Nền hơi khác nhau giữa các ảnh (văn phòng mờ) — cần đồng nhất tuyệt đối thì cố định 1 mô tả nền
- Nhân vật người que cũ (`8d4253fc-...`) đã NGƯNG DÙNG, giữ lại tham khảo ở
  `mascot-nguoi-que/anh/` — không xoá, phòng khi cần quay lại phong cách chalk/nét-đơn-giản
