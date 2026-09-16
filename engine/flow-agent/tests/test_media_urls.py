"""[VÁ RIÊNG 11/09] Kiểm tra gặt URL ký sẵn từ response poll / get_media.

Chạy: cd flow-agent && .venv/bin/python -m unittest tests.test_media_urls -v
Fixture lấy theo hình dạng response thật ghi trong WEVIDEO core/tests/test_flow_sdk.py.
"""
import io
import os
import tempfile
import unittest
from unittest import mock

from omniflash.generators import common

UUID = "f0b6561a-73f2-4360-96aa-35e071aac9ce"
SIGNED = f"https://flow-content.google/video/{UUID}?Expires=1&Signature=x"


class FakeBridge:
    def __init__(self, responses):
        self.media_urls = {}
        self._responses = list(responses)
        self.calls = []

    async def api_request(self, url_path, body, captcha_action="", method="POST", **kw):
        self.calls.append((url_path, method))
        return self._responses.pop(0)


class HarvestTests(unittest.TestCase):
    def test_operations_shape_fife_url(self):
        b = FakeBridge([])
        resp = {"data": {"operations": [{"status": "MEDIA_GENERATION_STATUS_SUCCESSFUL",
                 "operation": {"name": "op-1", "metadata": {"video": {
                     "mediaGenerationId": "CAUS-not-a-uuid", "fifeUrl": SIGNED}}}}]}}
        self.assertEqual(common.harvest_media_urls(b, resp), 1)
        self.assertEqual(b.media_urls[UUID], SIGNED)

    def test_media_shape_and_json_escaped_ampersand(self):
        b = FakeBridge([])
        raw = ('{"data":{"media":[{"name":"%s","video":{"fifeUrl":'
               '"https:\\/\\/flow-content.google\\/video\\/%s?Expires=1\\u0026Signature=y"}}]}}' % (UUID, UUID))
        self.assertEqual(common.harvest_media_urls(b, raw), 1)
        self.assertEqual(b.media_urls[UUID], f"https://flow-content.google/video/{UUID}?Expires=1&Signature=y")

    def test_legacy_gcs_host_and_no_url(self):
        b = FakeBridge([])
        gcs = f"https://storage.googleapis.com/ai-sandbox-videofx/video/{UUID}?sig=z"
        self.assertEqual(common.harvest_media_urls(b, {"x": gcs}), 1)
        self.assertEqual(b.media_urls[UUID], gcs)
        self.assertEqual(common.harvest_media_urls(b, {"error": {"code": 401}}), 0)
        self.assertEqual(common.harvest_media_urls(object(), {"x": gcs}), 0)  # bridge không có media_urls


class DownloadTests(unittest.IsolatedAsyncioTestCase):
    def _out(self):
        d = tempfile.mkdtemp()
        return os.path.join(d, "v.mp4")

    async def test_poll_harvests_then_download_uses_url_without_get_media(self):
        poll_ok = {"data": {"media": [{"name": UUID, "mediaMetadata": {"mediaStatus": {
            "mediaGenerationStatus": "MEDIA_GENERATION_STATUS_SUCCESSFUL"}},
            "video": {"fifeUrl": SIGNED}}]}}
        b = FakeBridge([poll_ok])
        self.assertTrue(await common.poll_status(b, UUID, "proj"))
        self.assertEqual(b.media_urls[UUID], SIGNED)
        out = self._out()
        with mock.patch.object(common.urllib.request, "urlopen") as uo:
            uo.return_value.__enter__.return_value = io.BytesIO(b"\x00\x00\x00\x18ftypmp42")
            self.assertTrue(await common.download_video(b, UUID, out))
            self.assertEqual(uo.call_args[0][0].full_url, SIGNED)
        self.assertEqual(open(out, "rb").read()[4:8], b"ftyp")
        self.assertEqual(b.calls, [(common.ENDPOINTS["poll_status"], "POST")])  # không gọi get_media

    async def test_get_media_fife_url_without_encoded_video(self):
        # Đường 18/08 hỏng (không có URL từ tab) + Google không trả encodedVideo,
        # nhưng /v1/media trả video.fifeUrl → vẫn tải được.
        b = FakeBridge([{"status": 200, "data": {"video": {"fifeUrl": SIGNED}}}])
        out = self._out()
        with mock.patch.object(common.urllib.request, "urlopen") as uo:
            uo.return_value.__enter__.return_value = io.BytesIO(b"mp4bytes")
            self.assertTrue(await common.download_video(b, UUID, out))
        self.assertEqual(open(out, "rb").read(), b"mp4bytes")
        self.assertEqual(b.calls[0][1], "GET")

    async def test_nothing_available_returns_false(self):
        b = FakeBridge([{"status": 400, "data": {"error": {"status": "INVALID_ARGUMENT", "message": "x"}}}])
        out = self._out()
        self.assertFalse(await common.download_video(b, UUID, out))
        self.assertFalse(os.path.exists(out))

    async def test_signed_url_fetch_failure_falls_back_to_base64(self):
        import base64
        b = FakeBridge([{"data": {"video": {"encodedVideo": base64.b64encode(b"B64").decode()}}}])
        b.media_urls[UUID] = SIGNED
        out = self._out()
        with mock.patch.object(common.urllib.request, "urlopen", side_effect=OSError("403")):
            self.assertTrue(await common.download_video(b, UUID, out))
        self.assertEqual(open(out, "rb").read(), b"B64")


if __name__ == "__main__":
    unittest.main()
