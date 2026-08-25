from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from media_auto_publisher.config import AppConfig, ExecutionConfig, RiskConfig
from media_auto_publisher.models import ContentKind, JobStatus, Platform, PublishJob
from media_auto_publisher.runner import PublisherRunner
from media_auto_publisher.store import JobStore


class _BrokenAdapter:
    def preview(self, job: PublishJob) -> dict[str, str]:
        return {"job_id": job.id}

    def publish(self, job: PublishJob) -> None:
        raise RuntimeError("upstream crashed")


class RunnerTests(unittest.TestCase):
    def test_unexpected_adapter_error_does_not_leave_job_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "video.mp4"
            media.write_bytes(b"test")
            store = JobStore(root / "state.db")
            job = PublishJob(
                platform=Platform.DOUYIN,
                account="main",
                kind=ContentKind.VIDEO,
                title="test",
                body="body",
                media=(str(media),),
            )
            store.enqueue(job, approved=True)
            config = AppConfig(
                execution=ExecutionConfig(database_path=root / "state.db"),
                risk=RiskConfig(min_interval_minutes=0),
            )
            runner = PublisherRunner(config, store)
            runner.adapters[Platform.DOUYIN] = _BrokenAdapter()  # type: ignore[assignment]

            outcome = runner.run_once()

            self.assertIsNotNone(outcome)
            self.assertEqual(outcome.status, "failed")
            stored = store.list(limit=1)[0]
            self.assertEqual(stored.status, JobStatus.FAILED)
            self.assertIn("upstream crashed", stored.last_error or "")


if __name__ == "__main__":
    unittest.main()
