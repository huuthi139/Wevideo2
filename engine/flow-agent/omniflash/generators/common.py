"""Omni Flash — Common utilities for all generators.

Shared functions: client context builder, poll_status, download_video.
"""

import asyncio
import base64
import json
import logging
import os
import random
import re
import time
import urllib.request
import uuid

from ..config import (
    CLIENT_CTX, ENDPOINTS, POLL_INTERVAL, POLL_TIMEOUT,
)

log = logging.getLogger("omniflash.generators")

# [VÁ RIÊNG 11/09] URL media ký sẵn của Flow (CDN cũ storage.googleapis, CDN mới
# flow-content.google). Google trả URL này NGAY TRONG response của poll
# (batchCheckAsync: operations[].operation.metadata.video.fifeUrl) và của
# /v1/media/{id} (video.fifeUrl) — không cần chờ tab Flow gọi tRPC như vá 18/08.
# Bài học từ TobyFlow: quét regex cả response thay vì tin vào một đường JSON cố
# định, vì hình dạng response đổi theo phiên bản Flow.
_MEDIA_URL_RE = re.compile(
    r"https://(?:storage\.googleapis\.com/ai-sandbox-videofx|flow-content\.google)"
    r"/(?:image|video)/([0-9a-fA-F-]{36})\?[^\"'\s\\]+"
)


def harvest_media_urls(bridge, payload) -> int:
    """Gặt URL ký sẵn trong `payload` (dict/str) vào `bridge.media_urls`.

    Trả về số URL tìm thấy. Không ném lỗi — hỏng thì trả 0.
    """
    urls = getattr(bridge, "media_urls", None)
    if urls is None:
        return 0
    try:
        text = payload if isinstance(payload, str) else json.dumps(payload)
    except (TypeError, ValueError):
        return 0
    text = text.replace("\\u0026", "&").replace("\\/", "/")
    found = 0
    for m in _MEDIA_URL_RE.finditer(text):
        urls[m.group(1).lower()] = m.group(0)
        found += 1
    return found


def _save_from_signed_url(bridge, media_id: str, output_path: str, label: str) -> bool:
    """Tải bằng URL ký sẵn đang giữ cho `media_id`. Không có URL / tải hỏng → False."""
    signed = getattr(bridge, "media_urls", {}).get(media_id.lower())
    if not signed:
        return False
    try:
        req = urllib.request.Request(signed, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as r:
            video_bytes = r.read()
        with open(output_path, "wb") as f:
            f.write(video_bytes)
        log.info("Saved: %s (%.1f MB) [%s]", output_path,
                 len(video_bytes) / (1024 * 1024), label)
        return True
    except Exception as e:
        log.error("Tai bang URL ky san hong (%s) [%s]", e, label)
        return False


def build_client_context(project_id: str) -> dict:
    """Build the clientContext dict used by all API requests."""
    return {
        "projectId": project_id,
        "tool": CLIENT_CTX["tool"],
        "userPaygateTier": CLIENT_CTX["tier"],
        "sessionId": f";{int(time.time() * 1000)}",
        "recaptchaContext": {
            "applicationType": CLIENT_CTX["recaptcha_app_type"],
            "token": "",
        },
    }


def build_generation_context(audio_pref: str = None) -> dict:
    """Build the mediaGenerationContext dict."""
    ctx = {"batchId": str(uuid.uuid4())}
    if audio_pref:
        ctx["audioFailurePreference"] = audio_pref
    return ctx


async def poll_status(bridge, media_id: str, project_id: str) -> bool:
    """Poll until video is ready. Returns True on success."""
    body = {"media": [{"name": media_id, "projectId": project_id}]}
    start = time.time()

    while time.time() - start < POLL_TIMEOUT:
        result = await bridge.api_request(ENDPOINTS["poll_status"], body, captcha_action="")
        harvest_media_urls(bridge, result)  # [VÁ RIÊNG 11/09]
        data = result.get("data", {})
        media = data.get("media", [])

        if media:
            meta = media[0].get("mediaMetadata", {}).get("mediaStatus", {})
            status = meta.get("mediaGenerationStatus", "")

            if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                elapsed = int(time.time() - start)
                log.info("Video ready! (%ds)", elapsed)
                return True
            elif "FAILED" in status or "BLOCKED" in status:
                log.error("Failed: %s", status)
                return False

        elapsed = int(time.time() - start)
        log.info("Waiting... (%ds)", elapsed)
        await asyncio.sleep(POLL_INTERVAL)

    log.error("Timeout after %ds", POLL_TIMEOUT)
    return False


async def download_video(bridge, media_id: str, output_path: str) -> bool:
    """Tải video về đĩa.

    [VÁ RIÊNG 18/08 — khác upstream 16/07] Ưu tiên **URL ký sẵn** trên CDN GCS.
    Extension trích URL đó từ response tRPC của trang Flow rồi đẩy sang bằng
    message `media_urls_refresh`; URL có chữ ký nên tải thẳng được, không cần
    token. Chỉ khi không có URL mới rơi về đường base64 `/v1/media/{id}` — đường
    này Google nay trả 400 INVALID_ARGUMENT, coi như đã chết.

    [VÁ RIÊNG 11/09] Ngoài URL do extension đẩy sang, `poll_status` và chính
    lệnh get_media bên dưới cũng được quét để gặt URL ký sẵn (xem
    `harvest_media_urls`) — nên tải được KHÔNG cần tab Flow mở.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # [FLOW V2 11/09] Tầng 0: bytes base64 do background.js (SW) tải sẵn — CDN mới cookie-gated,
    # urllib Python 403 nên đây là đường CHÍNH của transport UI.
    blob = getattr(bridge, "media_blobs", {}).get(str(media_id).lower())
    if blob:
        try:
            data = base64.b64decode(blob)
            with open(output_path, "wb") as f:
                f.write(data)
            log.info("Saved: %s (%.1f MB) [SW base64]", output_path, len(data) / (1024 * 1024))
            return True
        except Exception as e:  # noqa: BLE001
            log.error("Giai base64 video hong: %s", e)

    if _save_from_signed_url(bridge, media_id, output_path, "URL ky san"):
        return True

    # Du phong: get_media. Response co the mang video.fifeUrl (URL ky san) hoac
    # video.encodedVideo (base64 - duong cu, hien Google tu choi).
    url_path = ENDPOINTS["get_media"].format(media_id=media_id)
    result = await bridge.api_request(url_path, {}, captcha_action="", method="GET")
    if harvest_media_urls(bridge, result):
        if _save_from_signed_url(bridge, media_id, output_path, "URL trong get_media"):
            return True
    data = result.get("data", result)

    video_b64 = ""
    if isinstance(data, dict):
        v = data.get("video", {})
        if isinstance(v, dict):
            video_b64 = v.get("encodedVideo", "")
        elif isinstance(v, str):
            video_b64 = v

    if not video_b64:
        err = ""
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            err = f" - Google tra: {data['error'].get('status')} {data['error'].get('message','')}"
        log.error(
            "Khong tai duoc video %s: KHONG co URL ky san (dang giu %d URL) va "
            "duong base64 cung hong%s. -> MO TAB GOOGLE FLOW roi tai lai trang de "
            "extension bat duoc URL, sau do thu lai.",
            media_id[:8], len(getattr(bridge, "media_urls", {})), err)
        return False

    video_bytes = base64.b64decode(video_b64)
    with open(output_path, "wb") as f:
        f.write(video_bytes)
    log.info("Saved: %s (%.1f MB) [base64]", output_path,
             len(video_bytes) / (1024 * 1024))
    return True
