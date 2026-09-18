"""Kho media dùng chung — copy file đã gen sang MEDIA_LIBRARY_DIR, đổi tên <mã>_<tên>,
ghi 1 dòng manifest.jsonl để app khác tra/dùng lại.

Bật bằng env `MEDIA_LIBRARY_DIR` (vd đường NAS đã mount trên máy chạy backend). CHƯA set = TẮT
(no-op) → an toàn khi chưa mount NAS. Lỗi copy/ghi KHÔNG làm hỏng request gen (chỉ log cảnh báo).
"""
import os
import re
import json
import time
import shutil
import logging
import threading

log = logging.getLogger("omniflash.media_library")
_lock = threading.Lock()


def library_dir():
    """Thư mục kho (env MEDIA_LIBRARY_DIR) hoặc None nếu chưa cấu hình → tính năng TẮT."""
    d = (os.environ.get("MEDIA_LIBRARY_DIR") or "").strip()
    return d or None


def _slug(s):
    """Làm sạch mã/tên để đặt tên file: giữ chữ (có dấu), số, . - _; khoảng trắng → '-'. Cắt 80."""
    s = str(s or "").strip()
    s = re.sub(r"[^\w.\-\s]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    return s[:80]


def save_to_library(src_path, code=None, name=None, index=1, total=1, meta=None):
    """Copy `src_path` sang kho, đặt tên `<mã>_<tên>[_i].ext`, ghi 1 dòng manifest.jsonl.

    - Chưa set MEDIA_LIBRARY_DIR / file nguồn không tồn tại → trả None (no-op).
    - Không có mã lẫn tên → dùng media_id (hoặc timestamp) làm tên (vẫn lưu để không mất).
    - Trùng tên → thêm hậu tố `-2`, `-3`… (KHÔNG ghi đè).
    Trả đường dẫn file đích trong kho, hoặc None nếu bỏ qua/lỗi.
    """
    lib = library_dir()
    if not lib or not src_path or not os.path.isfile(src_path):
        return None
    try:
        os.makedirs(lib, exist_ok=True)
        ext = os.path.splitext(src_path)[1] or ""
        meta = meta or {}
        parts = [p for p in (_slug(code), _slug(name)) if p]
        base = "_".join(parts) if parts else (_slug(meta.get("media_id")) or ("media-" + str(int(time.time()))))
        if int(total or 1) > 1:
            base = "%s_%d" % (base, index)
        dst = os.path.join(lib, base + ext)
        if os.path.exists(dst):
            k = 2
            while os.path.exists(os.path.join(lib, "%s-%d%s" % (base, k, ext))):
                k += 1
            dst = os.path.join(lib, "%s-%d%s" % (base, k, ext))
        shutil.copy2(src_path, dst)
        entry = {"ts": int(time.time()), "code": code, "name": name, "file": os.path.basename(dst)}
        entry.update({k: v for k, v in meta.items() if v is not None})
        with _lock:
            with open(os.path.join(lib, "manifest.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log.info("Library saved: %s", dst)
        return dst
    except Exception as e:
        log.warning("Library save bỏ qua (lỗi): %s", e)
        return None
