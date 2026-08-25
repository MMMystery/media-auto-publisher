from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()

