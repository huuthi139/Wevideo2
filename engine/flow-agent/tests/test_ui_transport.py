"""[FLOW V2 11/09] Test transport UI: ui.py (unwrap/aspect/generate) + bridge.ui_generate (route response,
nạp media_urls + last_credits). Phép thử vàng: bỏ lưu URL/credits hay đổi method WS → test FAIL."""
import asyncio
import json
import unittest

from omniflash.bridge import ExtensionBridge
from omniflash.generators import ui as ui_mod


class UnwrapTests(unittest.TestCase):
    def test_unwrap_ok(self):
        self.assertEqual(ui_mod._unwrap({"result": {"mediaId": "m"}}, "x"), {"mediaId": "m"})

    def test_unwrap_error_code(self):
        with self.assertRaises(ValueError) as cm:
            ui_mod._unwrap({"error": "boom", "code": "NO_POPOVER"}, "dry")
        self.assertIn("NO_POPOVER", str(cm.exception))

    def test_unwrap_none(self):
        with self.assertRaises(ValueError):
            ui_mod._unwrap(None, "x")

    def test_aspect_map(self):
        self.assertEqual(ui_mod._ASPECT_UI["VIDEO_ASPECT_RATIO_PORTRAIT"], "9:16")
        self.assertEqual(ui_mod._ASPECT_UI["VIDEO_ASPECT_RATIO_LANDSCAPE"], "16:9")


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send_text(self, s):
        self.sent.append(json.loads(s))


class BridgeUiGenerateTests(unittest.TestCase):
    def test_routes_result_and_stores_url_credits(self):
        async def main():
            b = ExtensionBridge(); b._loop = asyncio.get_running_loop(); b._ws = FakeWS()
            task = asyncio.create_task(b.ui_generate({"prompt": "p", "aspect": "9:16", "duration": 4, "timeoutMs": 5000}))
            await asyncio.sleep(0.01)
            msg = b._ws.sent[-1]
            self.assertEqual(msg["method"], "ui_generate")
            self.assertEqual(msg["params"]["prompt"], "p")
            b._route_response(msg["id"], {"id": msg["id"], "result": {
                "mediaId": "AB-1", "videoUrl": "https://flow-content.google/video/x?sig=1",
                "videoBase64": "QUJD", "credits": 1043}})
            res = await task
            self.assertEqual(res["result"]["mediaId"], "AB-1")
            self.assertEqual(b.media_urls["ab-1"], "https://flow-content.google/video/x?sig=1")
            self.assertEqual(b.media_blobs["ab-1"], "QUJD")  # bytes video base64 do SW tải
            self.assertEqual(b.last_credits, 1043)
            self.assertIsNotNone(b.last_credits_at)
        asyncio.run(main())

    def test_error_passthrough(self):
        async def main():
            b = ExtensionBridge(); b._loop = asyncio.get_running_loop(); b._ws = FakeWS()
            task = asyncio.create_task(b.ui_generate({"prompt": "p", "timeoutMs": 5000}))
            await asyncio.sleep(0.01)
            msg = b._ws.sent[-1]
            b._route_response(msg["id"], {"id": msg["id"], "error": "NO_FLOW_PROJECT_TAB", "code": "NO_FLOW_PROJECT_TAB"})
            res = await task
            self.assertEqual(res["code"], "NO_FLOW_PROJECT_TAB")
            self.assertIsNone(b.last_credits)
            self.assertEqual(b.media_urls, {})
        asyncio.run(main())

    def test_not_connected(self):
        async def main():
            b = ExtensionBridge(); b._loop = asyncio.get_running_loop()
            res = await b.ui_generate({"prompt": "p"})
            self.assertEqual(res["code"], "EXT_DISCONNECTED")
        asyncio.run(main())


class GenerateVideoUiTests(unittest.TestCase):
    def test_collects_media_ids_and_maps_params(self):
        class B:
            def __init__(self): self.calls = []
            async def ui_generate(self, params):
                self.calls.append(params)
                return {"result": {"mediaId": f"m{len(self.calls)}", "videoUrl": "u", "credits": 1}}
        b = B()
        ids = asyncio.run(ui_mod.generate_video_ui(b, "hello", "VIDEO_ASPECT_RATIO_PORTRAIT", "proj", duration=4, count=2))
        self.assertEqual(ids, ["m1", "m2"])
        self.assertEqual(b.calls[0]["aspect"], "9:16")
        self.assertEqual(b.calls[0]["duration"], 4)
        self.assertNotIn("dryRun", b.calls[0])

    def test_raises_on_driver_error_no_retry(self):
        class B:
            def __init__(self): self.n = 0
            async def ui_generate(self, params):
                self.n += 1
                return {"error": 'chip="video 8 giay x2"', "code": "SETTINGS_MISMATCH"}
        b = B()
        with self.assertRaises(ValueError) as cm:
            asyncio.run(ui_mod.generate_video_ui(b, "x", "VIDEO_ASPECT_RATIO_PORTRAIT", "p", 4, 1))
        self.assertIn("SETTINGS_MISMATCH", str(cm.exception))
        self.assertEqual(b.n, 1)  # không retry

    def test_dry_run_sets_flag(self):
        class B:
            async def ui_generate(self, params):
                assert params["dryRun"] is True
                return {"result": {"dryRun": True, "chipText": "video · 720p · 4 giây · x1", "promptOk": True}}
        info = asyncio.run(ui_mod.dry_run_ui(B(), "x", "VIDEO_ASPECT_RATIO_PORTRAIT", 4))
        self.assertTrue(info["promptOk"])


if __name__ == "__main__":
    unittest.main()


class DownloadFromBlobTests(unittest.TestCase):
    """[FLOW V2] download_video ghi bytes từ bridge.media_blobs (base64) — không gọi mạng.
    Phép thử vàng: bỏ tầng media_blobs → test này fail vì rơi xuống urllib/get_media."""
    def test_writes_base64_blob_to_file(self):
        import base64, os, tempfile
        from omniflash.generators.common import download_video

        class B:
            def __init__(self): self.media_urls = {}; self.media_blobs = {"ab-1": base64.b64encode(b"\x00\x00\x00\x18ftypmp42REST").decode()}
            async def api_request(self, *a, **k):
                raise AssertionError("KHÔNG được gọi mạng khi đã có blob")
        d = tempfile.mkdtemp(); out = os.path.join(d, "clip.mp4")
        ok = asyncio.run(download_video(B(), "AB-1", out))
        self.assertTrue(ok)
        self.assertTrue(os.path.getsize(out) > 10)
        self.assertEqual(open(out, "rb").read()[4:8], b"ftyp")
