from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import RiskConfig
from .models import PublishJob, utc_now
from .store import JobStore


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    code: str
    message: str


class RiskGuard:
    def __init__(self, config: RiskConfig, store: JobStore) -> None:
        self.config = config
        self.store = store

    def evaluate(self, job: PublishJob, *, now: datetime | None = None) -> RiskDecision:
        current = now or utc_now()
        lock_reason = self.store.account_lock_reason(job.platform, job.account)
        if lock_reason:
            return RiskDecision(False, "account_locked", lock_reason)

        day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_count = self.store.count_successes_since(job.platform, job.account, day_start)
        if daily_count >= self.config.max_posts_per_account_per_day:
            return RiskDecision(
                False,
                "daily_limit",
                f"daily limit reached ({daily_count}/{self.config.max_posts_per_account_per_day})",
            )

        last_success = self.store.last_success_at(job.platform, job.account)
        minimum_gap = timedelta(minutes=self.config.min_interval_minutes)
        if last_success and current - last_success < minimum_gap:
            remaining = minimum_gap - (current - last_success)
            return RiskDecision(
                False,
                "minimum_interval",
                f"wait another {int(remaining.total_seconds() // 60) + 1} minutes",
            )

        if self.store.has_recent_success(
            job.fingerprint,
            days=self.config.duplicate_window_days,
            now=current,
        ):
            return RiskDecision(
                False,
                "duplicate",
                f"same content was published within {self.config.duplicate_window_days} days",
            )

        return RiskDecision(True, "allowed", "risk checks passed")

