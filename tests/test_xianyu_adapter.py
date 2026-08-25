from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from media_auto_publisher.adapters.xianyu_auto_reply import XianyuAutoReplyAdapter
from media_auto_publisher.config import ExecutionConfig, XianyuConfig
from media_auto_publisher.models import ContentKind, Platform, PublishJob


class XianyuAdapterTests(unittest.TestCase):
    def test_builds_local_browser_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "item.jpg"
            image.write_bytes(b"image")
            job = PublishJob(
                platform=Platform.XIANYU,
                account="main",
                kind=ContentKind.LISTING,
                title="title",
                body="description",
                media=(str(image),),
                metadata={"price": 10, "address": "上海"},
            )
            adapter = XianyuAutoReplyAdapter(
                XianyuConfig(command=("xianyu-local",), account_directory=root),
                ExecutionConfig(),
            )
            command = adapter.build_command(job)
            self.assertEqual(command[:2], ["xianyu-local", "post"])
            self.assertIn(str(image.resolve()), command)
            self.assertFalse(adapter.preview(job)["logged_in"])

    def test_reads_normalized_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "item.jpg"
            image.write_bytes(b"image")
            job = PublishJob(
                platform=Platform.XIANYU,
                account="main",
                kind=ContentKind.LISTING,
                title="title",
                body="description",
                media=(str(image),),
                metadata={"price": 10, "address": "上海"},
            )
            adapter = XianyuAutoReplyAdapter(
                XianyuConfig(command=("xianyu-local",), account_directory=root),
                ExecutionConfig(),
            )
            adapter.account_file("main").write_text("{}", encoding="utf-8")
            payload = {"success": True, "message": "ok", "item_id": "123", "item_url": "https://example.invalid/123"}
            completed = CompletedProcess(
                args=[], returncode=0, stdout=f"MAPUB_RESULT={json.dumps(payload)}\n", stderr=""
            )
            with patch("subprocess.run", return_value=completed):
                result = adapter.publish(job, live_authorized=True)
            self.assertTrue(result.success)
            self.assertEqual(result.external_id, "123")


if __name__ == "__main__":
    unittest.main()
