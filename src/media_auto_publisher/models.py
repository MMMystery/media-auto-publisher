from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


class Platform(StrEnum):
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    XIANYU = "xianyu"


class ContentKind(StrEnum):
    VIDEO = "video"
    NOTE = "note"
    LISTING = "listing"


class JobStatus(StrEnum):
    WAITING_APPROVAL = "waiting_approval"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class PublishJob:
    platform: Platform
    account: str
    kind: ContentKind
    title: str
    body: str
    media: tuple[str, ...]
    tags: tuple[str, ...] = ()
    scheduled_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.account.strip():
            raise ValueError("account must not be empty")
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.media:
            raise ValueError("at least one media file is required")
        if self.platform is Platform.XIANYU and self.kind is not ContentKind.LISTING:
            raise ValueError("xianyu only supports listing jobs")
        if self.platform is not Platform.XIANYU and self.kind is ContentKind.LISTING:
            raise ValueError("listing jobs are only supported by xianyu")

        missing = [path for path in self.media if not Path(path).expanduser().is_file()]
        if missing:
            raise ValueError(f"media files do not exist: {', '.join(missing)}")

        object.__setattr__(self, "scheduled_at", normalize_datetime(self.scheduled_at))
        object.__setattr__(
            self,
            "media",
            tuple(str(Path(path).expanduser().resolve()) for path in self.media),
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "platform": self.platform.value,
            "account": self.account.strip(),
            "kind": self.kind.value,
            "title": self.title.strip(),
            "body": self.body.strip(),
            "tags": sorted(tag.strip().lower() for tag in self.tags if tag.strip()),
            "media": [Path(path).name for path in self.media],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class StoredJob:
    job: PublishJob
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    attempts: int = 0
    last_error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)

