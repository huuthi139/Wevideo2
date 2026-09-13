#!/usr/bin/env python3
"""MCP server cho WeVideo App — cho AI agent (Hermes…) điều khiển tạo video.

Là lớp MỎNG bọc REST API sẵn có của app (:8080). Agent gọi tool → app lo pipeline.
Chạy (stdio, do MCP client khởi động):  .venv/bin/python mcp_server.py
Yêu cầu: WeVideo App đang chạy (bash run.sh) + flow-agent sẵn sàng.

Tools:  app_health · list_options · create_video · video_status
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Optional

from mcp.server import MCPServer  # mcp SDK 2.x (FastMCP cũ đổi tên thành MCPServer)

HERE = os.path.dirname(os.path.abspath(__file__))


def _env(path):
    c = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                c[k.strip()] = v.strip().strip('"').strip("'")
    return c


ENV = _env(os.path.join(HERE, "config.env"))
APP_URL = os.environ.get("WEVIDEO_APP_URL", f"http://127.0.0.1:{ENV.get('APP_PORT', '8080')}").rstrip("/")

mcp = MCPServer("wevideo")


def _get(path, timeout=10):
    with urllib.request.urlopen(APP_URL + path, timeout=timeout) as r:
        return json.load(r)


def _post(path, body, timeout=15):
    req = urllib.request.Request(APP_URL + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _video_path(job):
    return os.path.join(HERE, "projects", job, f"{job}_9x16.mp4")


@mcp.tool()
def app_health() -> dict:
    """Kiểm WeVideo App + engine gen (flow-agent/extension) đã sẵn sàng chưa.
    GỌI TRƯỚC khi create_video. ready=true mới gen được clip."""
    try:
        h = _get("/api/health")
    except Exception as e:
        return {"ready": False, "error": f"App WeVideo chưa chạy tại {APP_URL} ({e}). Bật: bash run.sh"}
    return {"ready": bool(h.get("extension_connected")), **h}


@mcp.tool()
def list_options() -> dict:
    """Giá trị hợp lệ cho tham số create_video + mặc định hiện tại của app."""
    try:
        cfg = _get("/api/config")
    except Exception:
        cfg = {}
    return {
        "style": ["phan", "trang"],
        "voice": ["vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"],
        "transition": ["hardcut", "dissolve", "fade", "slideleft", "circleopen"],
        "zoom": ["auto", "none", "in"],
        "duration": [4, 6, 8],
        "speed": [1.0, 1.1, 1.15],
        "defaults": cfg,
        "script_note": ("Mỗi dòng = 1 câu ĐỌC (tiếng Việt thuần). Kiểm soát hình: khối mỗi cảnh cách "
                        "nhau 1 dòng trống, gồm 'doc:' (lời đọc) 'hinh:' (mô tả hình tiếng Anh cho Veo) "
                        "'phude:' (phụ đề, *từ khoá* → IN HOA to). Tuỳ chọn 'broll:' (mô tả hình tiếng "
                        "Anh) → app gen thêm 1 clip Veo chèn cutaway giữa cảnh đó, giọng chạy tiếp."),
    }


@mcp.tool()
def create_video(script: str, style: Optional[str] = None, voice: Optional[str] = None,
                 transition: Optional[str] = None, zoom: Optional[str] = None,
                 duration: Optional[int] = None, speed: Optional[float] = None,
                 wait: bool = True, timeout_s: int = 600) -> dict:
    """Tạo video 9:16 từ kịch bản tiếng Việt (giọng + phụ đề kinetic + clip Veo + ráp).

    script: kịch bản (xem list_options.script_note). Tham số None = dùng mặc định app.
    wait=True: chờ xong, trả video_path (file mp4 trên máy) + video_url. Tốn ~7 credit/cảnh, mất 1-3 phút/cảnh.
    wait=False: trả job_id ngay, tự theo dõi bằng video_status(job_id) — nên dùng khi client MCP có timeout ngắn.
    """
    body = {"script": script}
    for k, v in (("style", style), ("voice", voice), ("transition", transition),
                 ("zoom", zoom), ("duration", duration), ("speed", speed)):
        if v is not None:
            body[k] = v
    try:
        r = _post("/api/create", body)
    except Exception as e:
        return {"ok": False, "error": f"Không gọi được app ({e}). App đã chạy chưa? bash run.sh"}
    job = r.get("job_id")
    if not job:
        return {"ok": False, "error": r.get("error", "tạo job thất bại")}
    if not wait:
        return {"ok": True, "job_id": job, "hint": "Theo dõi bằng video_status(job_id)."}
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            p = _get(f"/api/progress/{job}")
        except Exception:
            time.sleep(3); continue
        if p.get("done"):
            if p.get("ok"):
                return {"ok": True, "job_id": job, "video_path": _video_path(job),
                        "video_url": APP_URL + (p.get("video_url") or ""),
                        "duration": p.get("duration"), "source": p.get("source")}
            return {"ok": False, "job_id": job, "error": p.get("error", "lỗi")}
        time.sleep(3)
    return {"ok": False, "job_id": job, "status": "timeout",
            "error": f"Quá {timeout_s}s chưa xong. Dùng video_status('{job}') để theo dõi tiếp."}


@mcp.tool()
def video_status(job_id: str) -> dict:
    """Tiến độ 1 job tạo video (dùng khi create_video wait=False).
    Trả pct/msg/done/ok/error; xong thì thêm video_path + video_url."""
    try:
        p = _get(f"/api/progress/{job_id}")
    except Exception as e:
        return {"error": f"Không lấy được tiến độ ({e})."}
    if p.get("done") and p.get("ok"):
        p["video_path"] = _video_path(job_id)
        if p.get("video_url"):
            p["video_url"] = APP_URL + p["video_url"]
    return p


if __name__ == "__main__":
    mcp.run()
