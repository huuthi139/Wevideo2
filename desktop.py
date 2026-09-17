#!/usr/bin/env python3
"""desktop.py — Cửa sổ ứng dụng WeVideo trên macOS (pywebview / WKWebView).

Chạy như 1 app có cửa sổ riêng + icon Dock, KHÔNG mở tab trình duyệt. Phần lõi (engine
:8001 + web app :8080) vẫn chạy nền: nếu chưa chạy thì tự bật bằng run.sh (tiến trình
tách phiên, cửa sổ đóng vẫn chạy tiếp để không cắt job đang gen).

Lưu ý: gen clip Veo vẫn cần extension Chrome + 1 tab flow.google.com đã đăng nhập —
đó là ràng buộc của Google Flow, không phải của cửa sổ này.
"""
import os
import sys
import time
import subprocess
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def _port():
    try:
        for line in open(os.path.join(HERE, "config.env"), encoding="utf-8"):
            if line.strip().startswith("APP_PORT="):
                return line.split("=", 1)[1].strip().strip("'\"") or "8080"
    except Exception:
        pass
    return "8080"


PORT = _port()
URL = f"http://127.0.0.1:{PORT}"


def _up():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=2):
            return True
    except Exception:
        return False


def _ensure_backend():
    if _up():
        return True
    run = os.path.join(HERE, "run.sh")
    if not os.path.exists(run):
        return False
    env = dict(os.environ, PATH="/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", ""))
    log = open(os.path.join(HERE, "run.log"), "a")
    # start_new_session=True → tách phiên: đóng cửa sổ app, engine/app vẫn chạy nền
    subprocess.Popen(["bash", run], cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                     start_new_session=True, stdin=subprocess.DEVNULL)
    for _ in range(90):
        if _up():
            return True
        time.sleep(1)
    return False


def _set_app_name(name):
    """Đổi tên app trên thanh menu macOS (mặc định lấy CFBundleName của Python.app → 'Python').
    Vá CFBundleName của mainBundle TRƯỚC khi pywebview dựng menu → menu hiện đúng tên."""
    try:
        from Foundation import NSBundle
        b = NSBundle.mainBundle()
        for info in (b.localizedInfoDictionary(), b.infoDictionary()):
            if info is not None:
                info["CFBundleName"] = name
    except Exception:
        pass


def main():
    try:
        import webview
    except ImportError:
        sys.stderr.write("Thiếu pywebview. Cài: .venv/bin/pip install pywebview\n")
        sys.exit(1)
    _set_app_name("WeVideo")   # tên hiện trên thanh menu macOS (mặc định là "Python")
    _ensure_backend()   # dù backend chưa lên vẫn mở cửa sổ — trang tự báo trạng thái + thử lại
    webview.create_window("WeVideo", URL, width=1240, height=880, min_size=(900, 640))
    webview.start()


if __name__ == "__main__":
    main()
