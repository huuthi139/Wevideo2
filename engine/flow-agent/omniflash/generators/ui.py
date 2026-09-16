"""Omni Flash — [FLOW V2 11/09] Text-to-Video qua UI Flow v2 (flow.google.com).

Flow v2 không còn API aisandbox-pa; extension lái UI (chip cài đặt → Slate → gửi) rồi
nghe batchexecute để lấy mediaId + URL video ký sẵn. Xem SPEC-flow-v2-ui-transport.md.
"""

import logging

from ..config import POLL_TIMEOUT

log = logging.getLogger("omniflash.generators.ui")

_ASPECT_UI = {
    "VIDEO_ASPECT_RATIO_PORTRAIT": "9:16",
    "VIDEO_ASPECT_RATIO_LANDSCAPE": "16:9",
}


def _unwrap(res, what: str) -> dict:
    """Extension trả {result:{…}} hoặc {error, code}. Lỗi → ValueError(code: msg)."""
    if not isinstance(res, dict):
        raise ValueError(f"{what}: NO_RESPONSE")
    if res.get("error"):
        raise ValueError(f"{what}: {res.get('code', 'DRIVER_ERROR')}: {res.get('error')}")
    return res.get("result") or {}


async def dry_run_ui(bridge, prompt: str, aspect: str, duration: int) -> dict:
    """Kiểm driver (0 credit): chọn cài đặt + chèn prompt rồi xoá, KHÔNG gửi."""
    res = await bridge.ui_generate({
        "prompt": prompt, "aspect": _ASPECT_UI.get(aspect, "9:16"),
        "duration": int(duration), "dryRun": True, "timeoutMs": 60000,
    })
    return _unwrap(res, "dry_run")


def _img_aspect_ui(aspect: str) -> str:
    a = str(aspect or "").lower()
    if "landscape" in a or a == "16:9":
        return "16:9"
    return "9:16"


async def generate_image_ui(bridge, prompt: str, aspect: str, project_id: str,
                            count: int = 1) -> list[dict]:
    """[FLOW V2] Sinh ẢNH qua UI transport (omni image mặc định) — API aisandbox chết trên v2.

    Submit prompt (KHÔNG đổi model → dùng model ảnh mặc định) rồi CHỜ URL /image/ mới xuất hiện
    ở `bridge.media_urls`. Trả list {"media_id", "image_url"} cho đúng shape generate_image (API).
    """
    import asyncio
    ui_aspect = _img_aspect_ui(aspect)
    out: list[dict] = []
    for i in range(max(1, int(count))):
        log.info('Generating image (UI): "%s" %s (%d/%d)', prompt[:50], ui_aspect, i + 1, count)
        before = set(bridge.media_urls.keys())
        res = await bridge.ui_generate({
            "prompt": prompt, "aspect": ui_aspect, "duration": 4,
            "kind": "image", "timeoutMs": 200000,
        })
        _unwrap(res, "ui_generate_image")  # ném lỗi nếu driver báo error
        deadline = asyncio.get_event_loop().time() + int(POLL_TIMEOUT)
        mid = url = None
        while asyncio.get_event_loop().time() < deadline:
            new_img = [(m, u) for m, u in list(bridge.media_urls.items())
                       if m not in before and "/image/" in (u or "")]
            if new_img:
                mid, url = new_img[-1]
                break
            await asyncio.sleep(2)
        if not url:
            raise ValueError("omni image: không thấy URL /image/ mới sau submit (quá %ds)" % int(POLL_TIMEOUT))
        log.info("Done image (UI)! media_id=%s", mid)
        out.append({"media_id": mid, "image_url": url})
    return out


async def generate_video_ui(bridge, prompt: str, aspect: str, project_id: str,
                            duration: int = 8, count: int = 1) -> list[str]:
    """Submit T2V qua UI; mỗi lần 1 clip (count>1 → lặp tuần tự). Trả list mediaId.

    URL video đã được bridge nạp vào `bridge.media_urls[mediaId]` → download_video
    dùng thẳng URL ký sẵn, KHÔNG cần poll_status (driver đã chờ render xong).
    """
    import asyncio
    media_ids: list[str] = []
    for i in range(max(1, int(count))):
        # (0) Đảm bảo tab Ở GALLERY trước khi submit (clip trước có thể để tab ở /edit/).
        #     __GALLERY__ chỉ chạy ở ĐẦU — KHÔNG rời trang SAU khi đã capture (kẻo cắt capture).
        await bridge.ui_generate({"prompt": "__GALLERY__", "timeoutMs": 12000})
        await asyncio.sleep(4)
        log.info('Generating (UI): "%s" %ds %s (%d/%d)', prompt[:50], duration,
                 _ASPECT_UI.get(aspect, "9:16"), i + 1, count)
        res = await bridge.ui_generate({
            "prompt": prompt, "aspect": _ASPECT_UI.get(aspect, "9:16"),
            "duration": int(duration), "timeoutMs": int(POLL_TIMEOUT) * 1000,
        })
        r = _unwrap(res, "ui_generate")
        mid = r.get("mediaId")
        if not mid:
            # [OMNI 15/09] Extension chỉ SUBMIT. Sau render, Flow THƯỜNG tự fetch URL /video/ ký sẵn
            # (injected bắt vào media_urls) → engine tự lo TRỌN, KHÔNG cần LLM/Claude-in-Chrome:
            #   (1) chờ URL /video/ MỚI xuất hiện TRỰC TIẾP (case phổ biến).
            #   (2) fallback: nếu render xong (poster /image/ mới) mà /video/ chưa tự về → __PLAYTILE__
            #       (click tile mới nhất → /edit/ phát clip → ép Flow fetch /video/) 1 lần.
            #   Lấy new_vid[0] (insertion order = clip vừa gen). KHÔNG __GALLERY__ sau capture.
            log.info("OMNI submit ok (editor=%s) — chờ URL /video/…", str(r.get("editorText"))[:40])
            deadline = asyncio.get_event_loop().time() + int(POLL_TIMEOUT)
            vid_before = {m for m, u in bridge.media_urls.items() if "/video/" in (u or "")}
            img_before = {m for m, u in bridge.media_urls.items() if "/image/" in (u or "")}
            await asyncio.sleep(15)   # render tối thiểu cho clip omni ngắn
            played = False
            while asyncio.get_event_loop().time() < deadline:
                new_vid = [m for m, u in list(bridge.media_urls.items())
                           if m not in vid_before and "/video/" in (u or "")]
                if new_vid:
                    mid = new_vid[0]
                    log.info("  bắt URL /video/: %s (số mới=%d)", mid, len(new_vid))
                    break
                if not played and [m for m, u in list(bridge.media_urls.items())
                                   if m not in img_before and "/image/" in (u or "")]:
                    log.info("  render xong, /video/ chưa tự về → click tile ép fetch")
                    await bridge.ui_generate({"prompt": "__PLAYTILE__", "timeoutMs": 25000})
                    played = True
                await asyncio.sleep(4)
            if not mid:
                raise ValueError("omni: không lấy được URL /video/ sau %ds" % int(POLL_TIMEOUT))
        url = bridge.media_urls.get(mid) or bridge.media_urls.get(str(mid).lower())
        log.info("Done (UI)! media_id=%s url=%s", mid, "yes" if url else "NO")
        media_ids.append(mid)
    return media_ids
