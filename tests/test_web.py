from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from media_auto_publisher.web import app


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_homepage_is_served(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("发稿台", response.text)
        self.assertIn("/assets/app.js?v=", response.text)
        self.assertIn("no-store", response.headers["cache-control"])

    def test_static_assets_are_not_cached(self) -> None:
        response = self.client.get("/assets/app.js")

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["cache-control"])

    def test_health_reports_every_supported_platform(self) -> None:
        response = self.client.get("/api/health", params={"account": "main"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(
            set(payload["accounts"]),
            {"douyin", "xiaohongshu", "xianyu"},
        )

    def test_unknown_job_returns_not_found(self) -> None:
        response = self.client.get("/api/jobs/does-not-exist")

        self.assertEqual(response.status_code, 404)

    def test_douyin_title_is_limited_before_upload(self) -> None:
        response = self.client.post(
            "/api/publish",
            data={
                "platform": "douyin",
                "account": "main",
                "kind": "note",
                "title": "这是一条明显超过二十个字符限制的抖音图文标题内容",
                "body": "正文",
            },
            files={"media": ("cover.jpg", b"not-uploaded", "image/jpeg")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("最多 20 个字符", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
