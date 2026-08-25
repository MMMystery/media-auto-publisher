from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..models import PublishJob


@dataclass(frozen=True, slots=True)
class PublishResult:
    success: bool
    message: str
    external_id: str | None = None
    external_url: str | None = None
    challenge_required: bool = False
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def safe_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message[:500],
            "external_id": self.external_id,
            "external_url": self.external_url,
            "challenge_required": self.challenge_required,
            "retryable": self.retryable,
            "details": self.details,
        }


class PublisherAdapter(ABC):
    @abstractmethod
    def preview(self, job: PublishJob) -> dict[str, Any]:
        """Return a secret-free execution preview."""

    @abstractmethod
    def publish(self, job: PublishJob) -> PublishResult:
        """Publish one job and return a normalized result."""

