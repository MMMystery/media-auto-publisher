from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..config import ExecutionConfig, XianyuConfig
from ..models import ContentKind, Platform, PublishJob
from .base import PublishResult, PublisherAdapter


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
RESULT_PREFIX = "MAPUB_RESULT="


class XianyuAutoReplyAdapter(PublisherAdapter):
    """Thin local wrapper around the fork's Playwright Xianyu publisher."""

    def __init__(self, config: XianyuConfig, execution: ExecutionConfig) -> None:
        self.config = config
        self.execution = execution

    def _validate(self, job: PublishJob) -> None:
        if job.platform is not Platform.XIANYU or job.kind is not ContentKind.LISTING:
            raise ValueError("xianyu adapter only accepts listing jobs")
        if not job.metadata.get("price"):
            raise ValueError("xianyu listing requires a price")
        if not str(job.metadata.get("address", "")).strip():
            raise ValueError("xianyu listing requires an address")
        if float(job.metadata["price"]) <= 0:
            raise ValueError("xianyu price must be greater than zero")

        image_count = 0
        video_count = 0
        for media_path in job.media:
            path = Path(media_path)
            suffix = path.suffix.lower()
            if suffix in VIDEO_SUFFIXES:
                if path.stat().st_size > self.config.max_video_bytes:
                    raise ValueError(f"video file is too large: {path.name}")
                video_count += 1
            elif suffix in IMAGE_SUFFIXES:
                if path.stat().st_size > self.config.max_image_bytes:
                    raise ValueError(f"image file is too large: {path.name}")
                image_count += 1
            else:
                raise ValueError(f"unsupported xianyu media type: {path.name}")
        if not 1 <= image_count <= 9 or video_count > 3:
            raise ValueError("xianyu requires 1-9 images and allows at most 3 videos")

    def account_file(self, account: str) -> Path:
        safe_name = "".join(
            char if char.isalnum() or char in {"-", "_"} else "_" for char in account
        ).strip("_")
        if not safe_name:
            raise ValueError("account name must contain a letter or number")
        return self.config.account_directory / f"xianyu_{safe_name}.json"

    def login_command(self, account: str) -> list[str]:
        return [
            *self.config.command,
            "login",
            "--account",
            account,
            "--state",
            str(self.account_file(account)),
        ]

    def build_command(self, job: PublishJob) -> list[str]:
        self._validate(job)
        command = [
            *self.config.command,
            "post",
            "--account",
            job.account,
            "--state",
            str(self.account_file(job.account)),
            "--title",
            job.title,
            "--body",
            job.body,
            "--price",
            str(job.metadata["price"]),
            "--address",
            str(job.metadata["address"]),
            "--shipping-method",
            str(job.metadata.get("shipping_method", "free")),
            "--media",
            *job.media,
        ]
        original_price = job.metadata.get("original_price")
        if original_price:
            command.extend(["--original-price", str(original_price)])
        return command

    def preview(self, job: PublishJob) -> dict[str, Any]:
        self._validate(job)
        return {
            "adapter": "xianyu-auto-reply/local-browser",
            "platform": job.platform.value,
            "account": job.account,
            "title": job.title,
            "media": list(job.media),
            "price": job.metadata["price"],
            "address": job.metadata["address"],
            "logged_in": self.account_file(job.account).is_file(),
        }

    def publish(self, job: PublishJob, *, live_authorized: bool = False) -> PublishResult:
        if not live_authorized:
            raise RuntimeError("pass --publish to perform a real post")
        if not self.account_file(job.account).is_file():
            return PublishResult(
                False,
                f"xianyu account is not logged in; run: mapub login xianyu --account {job.account}",
            )

        try:
            completed = subprocess.run(
                self.build_command(job),
                capture_output=True,
                text=True,
                timeout=self.config.subprocess_timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            return PublishResult(False, f"publisher command not found: {self.config.command[0]}")
        except subprocess.TimeoutExpired:
            return PublishResult(False, "xianyu publisher timed out; check the platform manually")

        result_line = next(
            (
                line[len(RESULT_PREFIX) :]
                for line in reversed(completed.stdout.splitlines())
                if line.startswith(RESULT_PREFIX)
            ),
            "",
        )
        if not result_line:
            message = (completed.stderr or completed.stdout or "xianyu publisher failed")[-1000:]
            return PublishResult(False, message, details={"exit_code": completed.returncode})
        try:
            payload = json.loads(result_line)
        except json.JSONDecodeError:
            return PublishResult(False, "xianyu publisher returned an invalid result")
        return PublishResult(
            success=bool(payload.get("success")),
            message=str(payload.get("message") or "xianyu publish finished"),
            external_id=str(payload["item_id"]) if payload.get("item_id") else None,
            external_url=str(payload["item_url"]) if payload.get("item_url") else None,
            details={"exit_code": completed.returncode},
        )
