"""Nhận diện mặt (cv2) — CHẠY RIÊNG process để KHÔNG load chung 'av' của faster-whisper
(hai thư viện cùng bundle libavdevice → crash). In ra x-center (px nguồn) hoặc 'none'.
Dùng: python _facedetect.py <video> <iw> <t1,t2,...>

Ưu tiên YuNet DNN (cv2.FaceDetectorYN — có trên opencv 5.x, bắt cả mặt nghiêng/góc, mạnh hơn Haar).
opencv 5.0 ĐÃ BỎ CascadeClassifier → nếu thiếu YuNet mới thử Haar (opencv 4.x). Gộp nhiều khung,
ưu tiên mặt TO nhất (nhân vật chính) → bám mặt cho video talking-head.
"""
import os
import sys


def _center(cands, iw):
    if not cands:
        return "none"
    mx = max(a for _, a in cands)
    xs = sorted(x for x, a in cands if a >= 0.4 * mx)
    return xs[len(xs) // 2] if xs else "none"


try:
    import cv2
    video, iw = sys.argv[1], float(sys.argv[2])
    times = [float(x) for x in sys.argv[3].split(",") if x]
    cap = cv2.VideoCapture(video)
    cands = []  # (x_center px nguồn, diện tích mặt)

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

    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        if yunet is not None:
            yunet.setInputSize((w, h))
            try:
                _, faces = yunet.detect(frame)
            except Exception:
                faces = None
            if faces is not None:
                for f in faces:
                    fx, fy, fw, fh = float(f[0]), float(f[1]), float(f[2]), float(f[3])
                    cands.append(((fx + fw / 2.0) / w * iw, fw * fh))
        else:
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            for c in haar:
                for (x, y, fw, fh) in c.detectMultiScale(g, 1.1, 4, minSize=(60, 60)):
                    cands.append(((x + fw / 2.0) / w * iw, fw * fh))
    cap.release()
    print(_center(cands, iw))
except Exception:
    print("none")
