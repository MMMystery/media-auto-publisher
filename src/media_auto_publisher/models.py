from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass(frozen=True, slots=True)
class PublishJob:
    platform: Platform
    account: str
    kind: ContentKind
    title: str
    body: str
    media: tuple[str, ...]
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.account.strip() or not self.title.strip():
            raise ValueError("account and title must not be empty")
        if not self.media:
            raise ValueError("at least one media file is required")
        if self.platform is Platform.XIANYU and self.kind is not ContentKind.LISTING:
            raise ValueError("xianyu only supports listing jobs")
        if self.platform is not Platform.XIANYU and self.kind is ContentKind.LISTING:
            raise ValueError("listing jobs are only supported by xianyu")

        resolved = tuple(str(Path(path).expanduser().resolve()) for path in self.media)
        missing = [path for path in resolved if not Path(path).is_file()]
        if missing:
            raise ValueError(f"media files do not exist: {', '.join(missing)}")
        object.__setattr__(self, "media", resolved)
