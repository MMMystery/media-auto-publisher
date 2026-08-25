from __future__ import annotations

import os
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
SENSITIVE_PATTERN = re.compile(
    r"(?i)(authorization|cookie|password|secret|token|api[-_]?key)(\s*[:=]\s*)([^\s,;]+)"
)


def _redact_output(value: str, sensitive_values: tuple[str, ...]) -> str:
    redacted = SENSITIVE_PATTERN.sub(r"\1\2<redacted>", value)
    for secret in sensitive_values:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return redacted


class SocialAutoUploadAdapter(PublisherAdapter):
    def __init__(
        self,
        config: SocialAutoUploadConfig,
        execution: ExecutionConfig,
        *,
        sensitive_env_names: tuple[str, ...] = (),
    ) -> None:
        self.config = config
        self.execution = execution
        self.sensitive_env_names = sensitive_env_names

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
        # The current Douyin creator page may silently ignore its final submit
        # action in headless Chromium. Keep Douyin visible so trusted input and
        # any platform challenge can be handled; Xiaohongshu stays headless.
        if job.platform is Platform.DOUYIN:
            command.append("--headed")
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

    def publish(self, job: PublishJob, *, live_authorized: bool = False) -> PublishResult:
        if not live_authorized:
            raise RuntimeError("pass --publish to perform a real post")
        command = self.build_command(job)
        child_env = os.environ.copy()
        sensitive_values = tuple(child_env.pop(name, "") for name in self.sensitive_env_names)
        try:
            completed = subprocess.run(
                command,
                cwd=self.config.working_directory,
                capture_output=True,
                text=True,
                timeout=self.execution.subprocess_timeout_seconds,
                check=False,
                env=child_env,
            )
        except FileNotFoundError:
            return PublishResult(
                success=False,
                message=f"publisher command not found: {self.config.command[0]}",
            )
        except subprocess.TimeoutExpired as exc:
            parts: list[str] = []
            for value in (exc.stdout, exc.stderr):
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="replace")
                if value:
                    parts.append(value)
            recent_output = _redact_output("\n".join(parts), sensitive_values).strip()
            message = "发布器运行超时；重试前请先到平台后台确认是否已经发布"
            if recent_output:
                message += f"\n\n最后运行日志：\n{recent_output[-1200:]}"
            return PublishResult(
                success=False,
                message=message,
                retryable=False,
                reconciliation_required=True,
            )

        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        output = _redact_output(output, sensitive_values)
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
