"""Nhận diện mặt (cv2) — CHẠY RIÊNG process để KHÔNG load chung 'av' của faster-whisper
(hai thư viện cùng bundle libavdevice → crash). In ra x-center (px nguồn) hoặc 'none'.
Dùng: python _facedetect.py <video> <iw> <t1,t2,...>
"""
import sys
try:
    import cv2
    video, iw = sys.argv[1], float(sys.argv[2])
    times = [float(x) for x in sys.argv[3].split(",") if x]
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(video)
    xs = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(g, 1.2, 5, minSize=(50, 50))
        if len(faces):
            fx = max(faces, key=lambda r: r[2] * r[3])
            xs.append((fx[0] + fx[2] / 2) / frame.shape[1] * iw)
    cap.release()
    print(sorted(xs)[len(xs) // 2] if xs else "none")
except Exception as e:
    print("none")
