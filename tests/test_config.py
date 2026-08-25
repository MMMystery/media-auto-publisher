from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from media_auto_publisher.config import load_config


class ConfigTests(unittest.TestCase):
    def test_relative_paths_are_resolved_from_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_file = root / "config.toml"
            config_file.write_text(
                """
[social_auto_upload]
command = ["scripts/run-social-auto-upload"]
working_directory = "third_party/social-auto-upload"

[xianyu]
command = ["scripts/run-xianyu-local"]
account_directory = "accounts"
""",
                encoding="utf-8",
            )

            config = load_config(config_file)

            self.assertEqual(
                config.social_auto_upload.command[0],
                str((root / "scripts/run-social-auto-upload").resolve()),
            )
            self.assertEqual(
                config.social_auto_upload.working_directory,
                (root / "third_party/social-auto-upload").resolve(),
            )
            self.assertEqual(
                config.xianyu.command[0],
                str((root / "scripts/run-xianyu-local").resolve()),
            )
            self.assertEqual(config.xianyu.account_directory, (root / "accounts").resolve())

    def test_empty_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_file = Path(directory, "config.toml")
            config_file.write_text(
                '[xianyu]\ncommand = []\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "non-empty"):
                load_config(config_file)


if __name__ == "__main__":
    unittest.main()
