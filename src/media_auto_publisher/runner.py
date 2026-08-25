from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters import PublisherAdapter, SocialAutoUploadAdapter, XianyuAutoReplyAdapter
from .config import AppConfig
from .models import Platform, StoredJob
from .risk import RiskGuard
from .store import JobStore


@dataclass(frozen=True, slots=True)
class RunOutcome:
    job_id: str
    status: str
    message: str
    result: dict[str, Any] | None = None


class PublisherRunner:
    def __init__(self, config: AppConfig, store: JobStore) -> None:
        self.config = config
        self.store = store
        social = SocialAutoUploadAdapter(config.social_auto_upload, config.execution)
        self.adapters: dict[Platform, PublisherAdapter] = {
            Platform.DOUYIN: social,
            Platform.XIAOHONGSHU: social,
            Platform.XIANYU: XianyuAutoReplyAdapter(config.xianyu),
        }
        self.risk = RiskGuard(config.risk, store)

    def plan(self, *, limit: int = 10) -> list[dict[str, Any]]:
        plans: list[dict[str, Any]] = []
        for stored in self.store.due(limit=limit):
            decision = self.risk.evaluate(stored.job)
            plans.append(
                {
                    "job_id": stored.job.id,
                    "allowed": decision.allowed,
                    "risk_code": decision.code,
                    "risk_message": decision.message,
                    "execution": self.adapters[stored.job.platform].preview(stored.job),
                }
            )
        return plans

    def run_once(self) -> RunOutcome | None:
        due = self.store.due(limit=50)
        if not due:
            return None
        first_rejection: RunOutcome | None = None
        selected: StoredJob | None = None
        for candidate in due:
            decision = self.risk.evaluate(candidate.job)
            if decision.allowed:
                selected = candidate
                break
            if decision.code in {"account_locked", "duplicate"}:
                self.store.mark_blocked(candidate.job.id, decision.message)
            if first_rejection is None:
                first_rejection = RunOutcome(candidate.job.id, "skipped", decision.message)
        if selected is None:
            return first_rejection

        job = selected.job
        if not self.store.claim(job.id):
            return RunOutcome(job.id, "skipped", "job was claimed by another worker")

        try:
            result = self.adapters[job.platform].publish(job)
        except Exception as exc:
            message = f"publisher raised an unexpected error: {exc}"
            self.store.mark_failed(job.id, message)
            return RunOutcome(job.id, "failed", message)
        safe_result = result.safe_dict()
        if result.challenge_required and self.config.risk.stop_on_challenge:
            reason = f"challenge detected: {result.message[:300]}"
            self.store.lock_account(job.platform, job.account, reason)
            self.store.mark_blocked(job.id, reason, safe_result)
            return RunOutcome(job.id, "blocked", reason, safe_result)
        if result.success:
            self.store.mark_succeeded(job.id, safe_result)
            return RunOutcome(job.id, "succeeded", result.message, safe_result)

        self.store.mark_failed(job.id, result.message, safe_result)
        return RunOutcome(job.id, "failed", result.message, safe_result)
