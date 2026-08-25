from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_auto_publisher.adapters.social_auto_upload import SocialAutoUploadAdapter
from media_auto_publisher.config import ExecutionConfig, SocialAutoUploadConfig
from media_auto_publisher.models import ContentKind, Platform, PublishJob


class SocialAdapterTests(unittest.TestCase):
    def test_builds_xiaohongshu_note_command_without_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory, "cover.png")
            image.write_bytes(b"image")
            job = PublishJob(
                platform=Platform.XIAOHONGSHU,
                account="main",
                kind=ContentKind.NOTE,
                title="Title",
                body="Body",
                media=(str(image),),
                tags=("旅行", "攻略"),
            )
            adapter = SocialAutoUploadAdapter(
                SocialAutoUploadConfig(command=("python", "sau_cli.py")),
                ExecutionConfig(),
            )
            command = adapter.build_command(job)
            self.assertEqual(command[:4], ["python", "sau_cli.py", "xiaohongshu", "upload-note"])
            self.assertIn("旅行,攻略", command)
            self.assertNotIn("shell=True", command)
            self.assertNotIn("--headed", command)

    def test_douyin_uses_visible_browser_for_reliable_publish_click(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory, "cover.png")
            image.write_bytes(b"image")
            job = PublishJob(
                platform=Platform.DOUYIN,
                account="main",
                kind=ContentKind.NOTE,
                title="Title",
                body="Body",
                media=(str(image),),
            )
            adapter = SocialAutoUploadAdapter(
                SocialAutoUploadConfig(command=("python", "sau_cli.py")),
                ExecutionConfig(),
            )

            self.assertEqual(adapter.build_command(job)[-1], "--headed")

    def test_publish_requires_explicit_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory, "cover.png")
            image.write_bytes(b"image")
            job = PublishJob(
                platform=Platform.XIAOHONGSHU,
                account="main",
                kind=ContentKind.NOTE,
                title="Title",
                body="Body",
                media=(str(image),),
            )
            adapter = SocialAutoUploadAdapter(SocialAutoUploadConfig(), ExecutionConfig())
            with self.assertRaisesRegex(RuntimeError, "--publish"):
                adapter.publish(job, live_authorized=False)

    def test_timeout_keeps_the_last_publisher_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory, "cover.png")
            image.write_bytes(b"image")
            job = PublishJob(
                platform=Platform.DOUYIN,
                account="main",
                kind=ContentKind.NOTE,
                title="Title",
                body="Body",
                media=(str(image),),
            )
            adapter = SocialAutoUploadAdapter(
                SocialAutoUploadConfig(command=("python", "sau_cli.py")),
                ExecutionConfig(),
            )
            timeout = __import__("subprocess").TimeoutExpired(
                cmd=["python", "sau_cli.py"],
                timeout=10,
                output="已填写标题\n等待发布跳转",
            )

            with patch("subprocess.run", side_effect=timeout):
                result = adapter.publish(job, live_authorized=True)

            self.assertFalse(result.success)
            self.assertTrue(result.reconciliation_required)
            self.assertIn("等待发布跳转", result.message)


if __name__ == "__main__":
    unittest.main()
