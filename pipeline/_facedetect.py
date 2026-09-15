"""Nhận diện mặt (cv2) — CHẠY RIÊNG process để KHÔNG load chung 'av' của faster-whisper.
Dùng: python _facedetect.py <video> <iw> <t1,t2,...>
IN RA: mỗi mốc thời gian 1 giá trị x-center (px nguồn) của mặt TO nhất tại khung đó, hoặc 'none',
ngăn cách bằng dấu phẩy, ĐÚNG THỨ TỰ mốc truyền vào → phía gọi dựng đường bám mặt theo thời gian.

Ưu tiên YuNet DNN (cv2.FaceDetectorYN — opencv 5.x, bắt cả mặt nghiêng/góc). opencv 5.0 BỎ
CascadeClassifier → thiếu YuNet mới thử Haar (opencv 4.x).
"""
import os
import sys

try:
    import cv2
    video, iw = sys.argv[1], float(sys.argv[2])
    times = [float(x) for x in sys.argv[3].split(",") if x]
    cap = cv2.VideoCapture(video)

    yunet = None
    model = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "yunet.onnx")
    if hasattr(cv2, "FaceDetectorYN") and os.path.exists(model):
        try:
            yunet = cv2.FaceDetectorYN.create(model, "", (320, 320), 0.6, 0.3, 5000)
        except Exception:
            yunet = None
    haar = []
    if yunet is None and hasattr(cv2, "CascadeClassifier"):
        for n in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml"):
            c = cv2.CascadeClassifier(cv2.data.haarcascades + n)
            if not c.empty():
                haar.append(c)

    def largest_x(frame):
        h, w = frame.shape[:2]
        best = None  # (area, x_center_src)
        if yunet is not None:
            yunet.setInputSize((w, h))
            try:
                _, faces = yunet.detect(frame)
            except Exception:
                faces = None
            if faces is not None:
                for f in faces:
                    fx, fw, fh = float(f[0]), float(f[2]), float(f[3])
                    a = fw * fh
                    if best is None or a > best[0]:
                        best = (a, (fx + fw / 2.0) / w * iw)
        else:
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            for c in haar:
                for (x, y, fw, fh) in c.detectMultiScale(g, 1.1, 4, minSize=(60, 60)):
                    a = fw * fh
                    if best is None or a > best[0]:
                        best = (a, (x + fw / 2.0) / w * iw)
        return best[1] if best else None

    out = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        x = largest_x(frame) if ok else None
        out.append(f"{x:.1f}" if x is not None else "none")
    cap.release()
    print(",".join(out))
except Exception:
    # số 'none' đúng bằng số mốc để phía gọi không lệch
    try:
        n = len(sys.argv[3].split(","))
    except Exception:
        n = 1
    print(",".join(["none"] * n))
