from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import ContentKind, JobStatus, Platform, PublishJob, StoredJob, utc_now


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class JobStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    account TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    media_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    scheduled_at TEXT,
                    metadata_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_due
                    ON jobs(status, scheduled_at, created_at);
                CREATE INDEX IF NOT EXISTS idx_jobs_risk
                    ON jobs(platform, account, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint
                    ON jobs(fingerprint, status, updated_at);

                CREATE TABLE IF NOT EXISTS account_locks (
                    platform TEXT NOT NULL,
                    account TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(platform, account)
                );
                """
            )

    def enqueue(self, job: PublishJob, *, approved: bool = False) -> StoredJob:
        now = utc_now()
        status = JobStatus.PENDING if approved else JobStatus.WAITING_APPROVAL
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, platform, account, kind, title, body, media_json, tags_json,
                    scheduled_at, metadata_json, fingerprint, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.platform.value,
                    job.account,
                    job.kind.value,
                    job.title,
                    job.body,
                    json.dumps(job.media, ensure_ascii=False),
                    json.dumps(job.tags, ensure_ascii=False),
                    _iso(job.scheduled_at),
                    json.dumps(job.metadata, ensure_ascii=False, sort_keys=True),
                    job.fingerprint,
                    status.value,
                    _iso(now),
                    _iso(now),
                ),
            )
        return StoredJob(job=job, status=status, created_at=now, updated_at=now)

    def approve(self, job_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
                (JobStatus.PENDING.value, _iso(utc_now()), job_id, JobStatus.WAITING_APPROVAL.value),
            )
            return cursor.rowcount == 1

    def due(self, *, limit: int = 10, now: datetime | None = None) -> list[StoredJob]:
        current = now or utc_now()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM jobs
                WHERE status = ? AND (scheduled_at IS NULL OR scheduled_at <= ?)
                ORDER BY COALESCE(scheduled_at, created_at), created_at
                LIMIT ?
                """,
                (JobStatus.PENDING.value, _iso(current), limit),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def list(self, *, limit: int = 50) -> list[StoredJob]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def claim(self, job_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET status = ?, attempts = attempts + 1, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (JobStatus.RUNNING.value, _iso(utc_now()), job_id, JobStatus.PENDING.value),
            )
            return cursor.rowcount == 1

    def mark_succeeded(self, job_id: str, result: dict[str, Any]) -> None:
        self._finish(job_id, JobStatus.SUCCEEDED, result=result)

    def mark_failed(self, job_id: str, error: str, result: dict[str, Any] | None = None) -> None:
        self._finish(job_id, JobStatus.FAILED, error=error, result=result)

    def mark_blocked(self, job_id: str, error: str, result: dict[str, Any] | None = None) -> None:
        self._finish(job_id, JobStatus.BLOCKED, error=error, result=result)

    def _finish(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, last_error = ?, result_json = ?, updated_at = ? WHERE id = ?",
                (
                    status.value,
                    error,
                    json.dumps(result or {}, ensure_ascii=False, sort_keys=True),
                    _iso(utc_now()),
                    job_id,
                ),
            )

    def count_successes_since(
        self,
        platform: Platform,
        account: str,
        since: datetime,
    ) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count FROM jobs
                WHERE platform = ? AND account = ? AND status = ? AND updated_at >= ?
                """,
                (platform.value, account, JobStatus.SUCCEEDED.value, _iso(since)),
            ).fetchone()
        return int(row["count"])

    def last_success_at(self, platform: Platform, account: str) -> datetime | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT updated_at FROM jobs
                WHERE platform = ? AND account = ? AND status = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (platform.value, account, JobStatus.SUCCEEDED.value),
            ).fetchone()
        return _dt(row["updated_at"]) if row else None

    def has_recent_success(self, fingerprint: str, *, days: int, now: datetime | None = None) -> bool:
        cutoff = (now or utc_now()) - timedelta(days=days)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM jobs
                WHERE fingerprint = ? AND status = ? AND updated_at >= ? LIMIT 1
                """,
                (fingerprint, JobStatus.SUCCEEDED.value, _iso(cutoff)),
            ).fetchone()
        return row is not None

    def lock_account(self, platform: Platform, account: str, reason: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO account_locks(platform, account, reason, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(platform, account) DO UPDATE SET reason = excluded.reason, created_at = excluded.created_at
                """,
                (platform.value, account, reason, _iso(utc_now())),
            )

    def unlock_account(self, platform: Platform, account: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM account_locks WHERE platform = ? AND account = ?",
                (platform.value, account),
            )
            return cursor.rowcount == 1

    def account_lock_reason(self, platform: Platform, account: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT reason FROM account_locks WHERE platform = ? AND account = ?",
                (platform.value, account),
            ).fetchone()
        return str(row["reason"]) if row else None

    def _from_row(self, row: sqlite3.Row) -> StoredJob:
        job = PublishJob(
            id=row["id"],
            platform=Platform(row["platform"]),
            account=row["account"],
            kind=ContentKind(row["kind"]),
            title=row["title"],
            body=row["body"],
            media=tuple(json.loads(row["media_json"])),
            tags=tuple(json.loads(row["tags_json"])),
            scheduled_at=_dt(row["scheduled_at"]),
            metadata=json.loads(row["metadata_json"]),
        )
        return StoredJob(
            job=job,
            status=JobStatus(row["status"]),
            attempts=int(row["attempts"]),
            last_error=row["last_error"],
            result=json.loads(row["result_json"]),
            created_at=_dt(row["created_at"]) or utc_now(),
            updated_at=_dt(row["updated_at"]) or utc_now(),
        )

    def seed_success(self, jobs: Iterable[PublishJob], *, when: datetime | None = None) -> None:
        """Test helper that records approved jobs as successful."""
        timestamp = when or utc_now()
        for job in jobs:
            self.enqueue(job, approved=True)
            with self._connect() as connection:
                connection.execute(
                    "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                    (JobStatus.SUCCEEDED.value, _iso(timestamp), job.id),
                )

