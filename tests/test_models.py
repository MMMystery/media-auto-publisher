from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from media_auto_publisher.models import ContentKind, Platform, PublishJob


class PublishJobTests(unittest.TestCase):
    def test_media_path_is_resolved(self) -> None:
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
                tags=("B", "a"),
            )
            self.assertEqual(job.media, (str(image.resolve()),))

    def test_xianyu_requires_listing_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory, "cover.png")
            image.write_bytes(b"image")
            with self.assertRaisesRegex(ValueError, "only supports listing"):
                PublishJob(
                    platform=Platform.XIANYU,
                    account="1",
                    kind=ContentKind.NOTE,
                    title="Title",
                    body="Body",
                    media=(str(image),),
                )


if __name__ == "__main__":
    unittest.main()
