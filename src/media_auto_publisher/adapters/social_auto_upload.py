from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from ..config import ExecutionConfig, SocialAutoUploadConfig
from ..models import ContentKind, Platform, PublishJob
from .base import PublishResult, PublisherAdapter


CHALLENGE_MARKERS = (
    "captcha",
    "challenge",
    "verify",
    "verification",
    "验证码",
    "滑块",
    "人脸",
    "扫码验证",
    "账号异常",
    "风险验证",
)
URL_PATTERN = re.compile(r"https?://[^\s\]\[<>'\"]+")


class SocialAutoUploadAdapter(PublisherAdapter):
    def __init__(self, config: SocialAutoUploadConfig, execution: ExecutionConfig) -> None:
        self.config = config
        self.execution = execution

    def build_command(self, job: PublishJob) -> list[str]:
        if job.platform not in {Platform.DOUYIN, Platform.XIAOHONGSHU}:
            raise ValueError(f"unsupported social platform: {job.platform}")

        command = [*self.config.command, job.platform.value]
        tags = ",".join(tag.lstrip("#").strip() for tag in job.tags if tag.strip())

        if job.kind is ContentKind.VIDEO:
            command.extend(
                [
                    "upload-video",
                    "--account",
                    job.account,
                    "--file",
                    job.media[0],
                    "--title",
                    job.title,
                    "--desc",
                    job.body,
                ]
            )
        elif job.kind is ContentKind.NOTE:
            command.extend(["upload-note", "--account", job.account, "--images", *job.media])
            command.extend(["--title", job.title, "--note", job.body])
        else:
            raise ValueError(f"unsupported content kind: {job.kind}")

        if tags:
            command.extend(["--tags", tags])
        return command

    def preview(self, job: PublishJob) -> dict[str, Any]:
        command = self.build_command(job)
        return {
            "adapter": "social-auto-upload",
            "platform": job.platform.value,
            "account": job.account,
            "command": command,
            "working_directory": str(self.config.working_directory or Path.cwd()),
        }

    def publish(self, job: PublishJob) -> PublishResult:
        command = self.build_command(job)
        try:
            completed = subprocess.run(
                command,
                cwd=self.config.working_directory,
                capture_output=True,
                text=True,
                timeout=self.execution.subprocess_timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            return PublishResult(
                success=False,
                message=f"publisher command not found: {self.config.command[0]}",
            )
        except subprocess.TimeoutExpired:
            return PublishResult(
                success=False,
                message="publisher timed out; manual reconciliation is required before retry",
                retryable=False,
            )

        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        lowered = output.lower()
        challenge = any(marker in lowered for marker in CHALLENGE_MARKERS)
        urls = URL_PATTERN.findall(output)
        message = output[-1000:] if output else f"publisher exited with code {completed.returncode}"
        return PublishResult(
            success=completed.returncode == 0 and not challenge,
            message=message,
            external_url=urls[-1] if urls else None,
            challenge_required=challenge,
            retryable=completed.returncode != 0 and not challenge,
            details={"exit_code": completed.returncode},
        )

