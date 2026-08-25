from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from media_auto_publisher.config import RiskConfig
from media_auto_publisher.models import ContentKind, Platform, PublishJob
from media_auto_publisher.risk import RiskGuard
from media_auto_publisher.store import JobStore


class RiskGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.image = Path(self.tempdir.name, "cover.png")
        self.image.write_bytes(b"image")
        self.store = JobStore(Path(self.tempdir.name, "state.db"))
        self.now = datetime(2026, 8, 25, 4, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def job(self, title: str = "Title") -> PublishJob:
        return PublishJob(
            platform=Platform.DOUYIN,
            account="main",
            kind=ContentKind.NOTE,
            title=title,
            body="Body",
            media=(str(self.image),),
        )

    def test_duplicate_success_is_rejected(self) -> None:
        job = self.job()
        self.store.seed_success([job], when=self.now)
        guard = RiskGuard(RiskConfig(min_interval_minutes=0), self.store)
        decision = guard.evaluate(self.job(), now=self.now)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "duplicate")

    def test_account_lock_stops_publishing(self) -> None:
        job = self.job()
        self.store.lock_account(job.platform, job.account, "captcha")
        decision = RiskGuard(RiskConfig(), self.store).evaluate(job, now=self.now)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "account_locked")


if __name__ == "__main__":
    unittest.main()

