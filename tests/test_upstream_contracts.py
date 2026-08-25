from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpstreamContractTests(unittest.TestCase):
    def test_all_locked_forks_are_checked_out(self) -> None:
        lock = json.loads((ROOT / "upstreams.lock.json").read_text(encoding="utf-8"))
        for name, item in lock.items():
            with self.subTest(name=name):
                path = ROOT / item["path"]
                self.assertTrue(path.is_dir(), f"missing submodule: {path}")
                self.assertTrue((path / "LICENSE").is_file(), f"missing license: {path}")
                completed = subprocess.run(
                    ["git", "-C", str(path), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertEqual(completed.stdout.strip(), item["commit"])

    def test_social_cli_contract_used_by_adapter_exists(self) -> None:
        documentation = (ROOT / "third_party/social-auto-upload/docs/CLI.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("sau douyin upload-video", documentation)
        self.assertIn("sau douyin upload-note", documentation)
        self.assertIn("sau xiaohongshu upload-video", documentation)
        self.assertIn("sau xiaohongshu upload-note", documentation)

    def test_xianyu_browser_publisher_used_by_adapter_exists(self) -> None:
        publisher = (
            ROOT
            / "third_party/xianyu-auto-reply/backend-web/app/services/xianyu_publisher.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class XianyuPublisher", publisher)
        self.assertIn("async def publish_item", publisher)
        self.assertIn("await self._upload_images(images)", publisher)
        self.assertIn("await self._click_publish_button(result)", publisher)


if __name__ == "__main__":
    unittest.main()
