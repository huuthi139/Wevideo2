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
    # [ASPECT 17/09] Ảnh có ĐỦ 5 tỉ lệ trên UI (16:9 4:3 1:1 3:4 9:16) — trước đây gom hết về
    # 9:16 (vuông/4x3/3x4 ra sai). map_size_to_aspect trả square/landscape/portrait/4x3/3x4.
    a = str(aspect or "").lower()
    m = {
        "landscape": "16:9", "16:9": "16:9", "16x9": "16:9",
        "4x3": "4:3", "4:3": "4:3",
        "square": "1:1", "1:1": "1:1",
        "3x4": "3:4", "3:4": "3:4",
        "portrait": "9:16", "9:16": "9:16", "9x16": "9:16",
    }
    return m.get(a, "9:16")


async def generate_image_ui(bridge, prompt: str, aspect: str, project_id: str,
                            count: int = 1, images_b64: list[str] | None = None,
                            ref_name: str | None = None, ref_id: str | None = None) -> list[dict]:
    """[FLOW V2] Sinh ẢNH qua UI transport (omni image mặc định) — API aisandbox chết trên v2.

    Submit prompt (KHÔNG đổi model → dùng model ảnh mặc định) rồi CHỜ URL /image/ mới xuất hiện
    ở `bridge.media_urls`. Trả list {"media_id", "image_url"} cho đúng shape generate_image (API).

    [I2I 16/09] `images_b64` (data URL) → driver đính ảnh vào composer trước khi gõ prompt
    (upload API cũ chết trên v2) → Flow dùng ảnh làm tham chiếu = image-to-image.
    """
    import asyncio
    ui_aspect = _img_aspect_ui(aspect)
    out: list[dict] = []
    for i in range(max(1, int(count))):
        # [FIX 17/09] Sau mỗi lần gen, Flow điều hướng tab sang /edit/<id> → lần gen sau vướng
        # guard NO_PROJECT_PAGE (submit chỉ chạy ở gallery /project/<id>). Video path đã xử bằng
        # __GALLERY__ ở đầu; image path trước đây thiếu → đưa tab về gallery TRƯỚC khi submit.
        try:
            await bridge.ui_generate({"prompt": "__GALLERY__", "timeoutMs": 12000})
            await asyncio.sleep(4)
        except Exception as e:
            log.debug("image __GALLERY__ bỏ qua: %s", e)
        log.info('Generating image (UI%s): "%s" %s (%d/%d)',
                 " i2i x%d" % len(images_b64) if images_b64 else "", prompt[:50], ui_aspect, i + 1, count)
        before = set(bridge.media_urls.keys())
        payload = {
            "prompt": prompt, "aspect": ui_aspect, "duration": 4,
            "kind": "image", "timeoutMs": 200000,
        }
        if images_b64:
            payload["imagesB64"] = images_b64
        if ref_id:
            payload["refId"] = ref_id  # [CHAR-REF 17/09] cố định nhân vật theo data-media-id (CHẮC)
        elif ref_name:
            payload["refName"] = ref_name  # fallback: chọn asset gốc theo mã/tên caption
        res = await bridge.ui_generate(payload)
        r = _unwrap(res, "ui_generate_image")  # ném lỗi nếu driver báo error
        att = r.get("attach") if isinstance(r, dict) else None
        if images_b64 and att and not att.get("thumb"):
            log.warning("i2i: driver đính ảnh qua %s nhưng KHÔNG thấy thumbnail xác nhận — "
                        "ảnh ra có thể là t2i thuần, cần soi kết quả", att.get("via"))
        # [I2I FIX 17/09] Khi đính ảnh tham chiếu, MỖI ảnh đính cũng sinh 1 URL /image/ MỚI
        # (Flow upload → signed URL) xuất hiện TRƯỚC ảnh gen ra. Nếu lấy URL mới đầu tiên sẽ
        # vớ nhầm chính ảnh tham chiếu (đã gặp: i2i trả lại ảnh gốc 256px, không áp prompt).
        # → bỏ qua đúng n_ref ảnh đầu (tham chiếu, theo thứ tự chèn), lấy ảnh KẾ TIẾP = kết quả.
        n_ref = len(images_b64) if images_b64 else 0
        deadline = asyncio.get_event_loop().time() + int(POLL_TIMEOUT)
        mid = url = None
        while asyncio.get_event_loop().time() < deadline:
            fresh = [(m, u) for m, u in list(bridge.media_urls.items()) if m not in before]
            imgs = [(m, u) for m, u in fresh if "/image/" in (u or "")]
            if n_ref:
                # cần > n_ref URL ảnh: n_ref đầu là tham chiếu, cái sau cùng là kết quả gen
                if len(imgs) > n_ref:
                    mid, url = imgs[-1]
                    break
            else:
                # [FIX 16/09] t2i: URL không luôn chứa "/image/" → fallback URL mới không phải video
                new_img = imgs or [(m, u) for m, u in fresh if "/video/" not in (u or "")]
                if new_img:
                    mid, url = new_img[-1]
                    break
            await asyncio.sleep(2)
        if not url:
            raise ValueError("omni image: không thấy URL ảnh mới sau submit (quá %ds)" % int(POLL_TIMEOUT))
        log.info("Done image (UI)! media_id=%s path=%s", mid, (url or "").split("?")[0][-70:])
        out.append({"media_id": mid, "image_url": url})
    return out


async def generate_video_ui(bridge, prompt: str, aspect: str, project_id: str,
                            duration: int = 8, count: int = 1,
                            animate_from: str | None = None) -> list[str]:
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
        # [FIX 16/09] __GALLERY__ khiến gallery LAZY-LOAD các /video/ CŨ dần dần. Nếu chốt vid_before
        # quá sớm, clip cũ ùa về SAU đó bị nhận nhầm là "mới" → engine VƠ CLIP CŨ, báo thành công GIẢ
        # (thấy trên iMac: xin 4s ra clip 10s cũ). Chờ tập /video/ ỔN ĐỊNH rồi mới chốt vid_before TRƯỚC
        # khi submit → chỉ RENDER THẬT (media_id chưa từng có) mới tính là mới. Mac mini ổn định nhanh.
        def _vidset():
            return {m for m, u in list(bridge.media_urls.items()) if "/video/" in (u or "")}
        _stab = _vidset(); _stab_t = asyncio.get_event_loop().time()
        _settle = asyncio.get_event_loop().time() + 25
        while asyncio.get_event_loop().time() < _settle:
            await asyncio.sleep(2)
            _cur = _vidset()
            if _cur != _stab:
                _stab = _cur; _stab_t = asyncio.get_event_loop().time()
            elif asyncio.get_event_loop().time() - _stab_t >= 5:
                break
        vid_before = _vidset()
        img_before = {m for m, u in bridge.media_urls.items() if "/image/" in (u or "")}
        log.info('Generating (UI): "%s" %ds %s (%d/%d) — %d clip cũ trong gallery', prompt[:50],
                 duration, _ASPECT_UI.get(aspect, "9:16"), i + 1, count, len(vid_before))
        _vpayload = {
            "prompt": prompt, "aspect": _ASPECT_UI.get(aspect, "9:16"),
            "duration": int(duration), "timeoutMs": int(POLL_TIMEOUT) * 1000,
        }
        if animate_from:
            # [ANIMATE 17/09] Ảnh→video: driver right-click ảnh nguồn → "Tạo ảnh động" (menu tự set
            # video mode + khung đầu). Tỉ lệ/thời lượng theo mặc định menu (16:9/4s) — bỏ qua aspect.
            _vpayload["animateFrom"] = animate_from
        res = await bridge.ui_generate(_vpayload)
        r = _unwrap(res, "ui_generate")
        mid = r.get("mediaId")
        if not mid:
            # Extension chỉ SUBMIT. Sau render Flow tự fetch URL /video/ ký sẵn (injected bắt vào
            # media_urls). CHỈ nhận media_id KHÔNG có trong vid_before (đã chốt sau khi gallery ổn định)
            # → đúng clip vừa render, không vơ clip cũ. Fallback __PLAYTILE__ nếu có poster /image/ mới.
            log.info("OMNI submit ok (editor=%s) — chờ URL /video/ MỚI…", str(r.get("editorText"))[:40])
            deadline = asyncio.get_event_loop().time() + int(POLL_TIMEOUT)
            await asyncio.sleep(15)   # render tối thiểu cho clip omni ngắn
            played = False
            while asyncio.get_event_loop().time() < deadline:
                new_vid = [m for m, u in list(bridge.media_urls.items())
                           if m not in vid_before and "/video/" in (u or "")]
                if new_vid:
                    mid = new_vid[0]
                    log.info("  bắt URL /video/ MỚI: %s (số mới=%d)", mid, len(new_vid))
                    break
                if not played and [m for m, u in list(bridge.media_urls.items())
                                   if m not in img_before and "/image/" in (u or "")]:
                    log.info("  render xong, /video/ chưa tự về → click tile ép fetch")
                    await bridge.ui_generate({"prompt": "__PLAYTILE__", "timeoutMs": 25000})
                    played = True
                await asyncio.sleep(4)
            if not mid:
                raise ValueError("omni: không có clip /video/ MỚI sau %ds — Flow không render "
                                 "(hết credit Veo / account không có video / bị chặn nhịp)" % int(POLL_TIMEOUT))
        url = bridge.media_urls.get(mid) or bridge.media_urls.get(str(mid).lower())
        log.info("Done (UI)! media_id=%s url=%s", mid, "yes" if url else "NO")
        media_ids.append(mid)
    return media_ids
