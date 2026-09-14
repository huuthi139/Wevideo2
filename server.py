#!/usr/bin/env python3
"""WEVIDEO-APP — web app local: dán kịch bản → video (một phát).

Chạy:  .venv/bin/python server.py   (hoặc ./run.sh)
Mở:    http://127.0.0.1:8080
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env(path):
    cfg = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


ENV = load_env(os.path.join(HERE, "config.env"))
APP_PORT = int(ENV.get("APP_PORT", "8080"))
FLOW_URL = ENV.get("FLOW_AGENT_URL", "http://127.0.0.1:8001")
PROJECTS = os.path.join(HERE, "projects")
os.makedirs(PROJECTS, exist_ok=True)

# ── Cập nhật phần mềm (kéo code mới từ GitHub qua gh CLI) ──
UPDATE_REPO = ENV.get("UPDATE_REPO", "huuthi139/Wevideo2")
# CHỈ ghi đè các mục CODE — KHÔNG đụng config.env / projects / engine / .venv
_UPDATE_ITEMS = ["server.py", "mcp_server.py", "pipeline", "web", "scripts",
                 "README.md", "setup.sh", "run.sh", "build_installer.sh",
                 "hermes-mcp-config.json", ".gitignore"]


def _current_version():
    vf = os.path.join(HERE, "VERSION")
    if os.path.exists(vf):
        try:
            return open(vf).read().strip()
        except Exception:
            pass
    try:
        r = subprocess.run(["git", "-C", HERE, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "?"


from pipeline import core  # noqa: E402

app = FastAPI(title="WeVideo App")
JOBS: dict[str, dict] = {}


def _defaults():
    return {
        "style": ENV.get("STYLE", "phan"),
        "voice": ENV.get("VOICE", "vi-VN-NamMinhNeural"),
        "rate": ENV.get("VOICE_RATE", "+8%"),
        "gap": float(ENV.get("VOICE_GAP", "0.30")),
        "transition": ENV.get("TRANSITION", "hardcut"),
        "zoom": ENV.get("ZOOM", "auto"),
        "duration": int(ENV.get("DURATION", "4")),
        "speed": float(ENV.get("SPEED", "1.15")),
        "auto_broll": ENV.get("AUTO_BROLL", "off").lower() in ("on", "true", "1"),
        "sfx": ENV.get("SFX", "on").lower() in ("on", "true", "1"),
        "sfx_gain": float(ENV.get("SFX_GAIN", "0.3")),
    }


def _llm_cfg():
    url = ENV.get("LLM_URL", "").strip()
    if not url:
        return None
    return {"url": url, "model": ENV.get("LLM_MODEL", ""), "key": ENV.get("LLM_KEY", "")}


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "web", "index.html"))


@app.get("/api/config")
def api_config():
    d = _defaults()
    d["llm"] = bool(_llm_cfg())
    return d


@app.get("/api/health")
def api_health():
    """Trạng thái flow-agent + extension (để UI báo sẵn sàng chưa)."""
    try:
        with urllib.request.urlopen(FLOW_URL.rstrip("/") + "/health", timeout=4) as r:
            h = json.load(r)
        ready = bool(h.get("extension_connected"))
        return {"flow_agent": True, "extension_connected": ready,
                "transport": h.get("transport"), "detail": h}
    except Exception as e:
        return {"flow_agent": False, "extension_connected": False, "error": str(e)[:120]}


@app.post("/api/create")
async def api_create(req: Request):
    body = await req.json()
    script = (body.get("script") or "").strip()
    if not script:
        return JSONResponse({"error": "Thiếu kịch bản"}, status_code=400)
    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(PROJECTS, job_id)
    d = _defaults()
    opts = {
        "script": script, "job_dir": job_dir, "name": job_id,
        "style": body.get("style", d["style"]),
        "voice": body.get("voice", d["voice"]),
        "rate": body.get("rate", d["rate"]),
        "gap": d["gap"],
        "transition": body.get("transition", d["transition"]),
        "zoom": body.get("zoom", d["zoom"]),
        "duration": int(body.get("duration", d["duration"])),
        "speed": float(body.get("speed", d["speed"])),
        "auto_broll": bool(body.get("auto_broll", d["auto_broll"])),
        "sfx": bool(body.get("sfx", d["sfx"])),
        "sfx_gain": float(body.get("sfx_gain", d["sfx_gain"])),
        "flow_agent_url": FLOW_URL,
        "llm_cfg": _llm_cfg(),
    }
    JOBS[job_id] = {"pct": 0, "msg": "Đang khởi tạo…", "done": False, "ok": None, "error": None}

    def worker():
        def prog(p, m):
            JOBS[job_id].update(pct=p, msg=m)
        try:
            res = core.run(opts, prog)
        except Exception as e:
            JOBS[job_id].update(done=True, ok=False, error=str(e)[:300]); return
        if res.get("ok"):
            JOBS[job_id].update(done=True, ok=True, pct=100, msg="Xong.",
                                video=res["out"], duration=res.get("duration"),
                                source=res.get("source"))
        else:
            JOBS[job_id].update(done=True, ok=False, error=res.get("error", "lỗi"))

    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/progress/{job_id}")
def api_progress(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        return JSONResponse({"error": "job không tồn tại"}, status_code=404)
    out = {k: j.get(k) for k in ("pct", "msg", "done", "ok", "error", "duration", "source")}
    out["video_url"] = f"/api/video/{job_id}" if j.get("ok") else None
    return out


@app.get("/api/video/{job_id}")
def api_video(job_id: str):
    j = JOBS.get(job_id)
    if not j or not j.get("video") or not os.path.exists(j["video"]):
        return JSONResponse({"error": "chưa có video"}, status_code=404)
    return FileResponse(j["video"], media_type="video/mp4",
                        filename=os.path.basename(j["video"]))


@app.get("/api/version")
def api_version():
    """Phiên bản hiện tại + bản mới nhất trên GitHub (qua gh CLI)."""
    cur = _current_version()
    latest, err = None, None
    if not shutil.which("gh"):
        err = "Thiếu 'gh' CLI (GitHub) → không kiểm được bản mới. Cài: brew install gh && gh auth login"
    else:
        try:
            r = subprocess.run(["gh", "api", f"repos/{UPDATE_REPO}/commits/main", "--jq", ".sha"],
                               capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                latest = r.stdout.strip()[:7]
            else:
                err = (r.stderr or "").strip()[-160:]
        except Exception as e:
            err = str(e)[:160]
    avail = bool(latest and cur not in ("", "?") and latest[:7] != cur[:7])
    return {"current": cur, "latest": latest, "update_available": avail, "repo": UPDATE_REPO, "error": err}


@app.post("/api/update")
def api_update():
    """Kéo code mới nhất từ GitHub, ghi đè phần CODE (giữ config.env + projects + engine)."""
    if not shutil.which("gh"):
        return JSONResponse({"ok": False, "error": "Thiếu 'gh' CLI. Cài: brew install gh && gh auth login"}, status_code=400)
    tmp = tempfile.mkdtemp(prefix="wevideo-upd-")
    src = os.path.join(tmp, "src")
    try:
        r = subprocess.run(["gh", "repo", "clone", UPDATE_REPO, src, "--", "--depth", "1", "--branch", "main"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return JSONResponse({"ok": False, "error": "Tải bản mới lỗi: " + (r.stderr or "")[-200:]}, status_code=500)
        sha = ""
        try:
            sha = subprocess.run(["git", "-C", src, "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()
        except Exception:
            pass
        applied = 0
        for item in _UPDATE_ITEMS:
            si, di = os.path.join(src, item), os.path.join(HERE, item)
            if not os.path.exists(si):
                continue
            if os.path.isdir(si):
                shutil.rmtree(di, ignore_errors=True); shutil.copytree(si, di)
            else:
                shutil.copy2(si, di)
            applied += 1
        if sha:
            with open(os.path.join(HERE, "VERSION"), "w") as f:
                f.write(sha + "\n")
        return {"ok": True, "version": sha or "?", "applied": applied,
                "note": "Đã cập nhật. Khởi động lại app (bash run.sh) để áp dụng code mới."}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if os.path.isdir(os.path.join(HERE, "web")):
    app.mount("/static", StaticFiles(directory=os.path.join(HERE, "web")), name="static")


if __name__ == "__main__":
    import uvicorn
    print(f"WeVideo App → http://127.0.0.1:{APP_PORT}  (flow-agent: {FLOW_URL})")
    uvicorn.run(app, host="127.0.0.1", port=APP_PORT)
