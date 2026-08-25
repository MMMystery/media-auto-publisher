from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    subprocess_timeout_seconds: int = 900


@dataclass(frozen=True, slots=True)
class SocialAutoUploadConfig:
    command: tuple[str, ...] = ("sau",)
    working_directory: Path | None = None


@dataclass(frozen=True, slots=True)
class XianyuConfig:
    command: tuple[str, ...] = ("scripts/run-xianyu-local",)
    account_directory: Path = Path(".media-auto-publisher/accounts")
    subprocess_timeout_seconds: int = 900
    max_image_bytes: int = 5 * 1024 * 1024
    max_video_bytes: int = 100 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class AppConfig:
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    social_auto_upload: SocialAutoUploadConfig = field(default_factory=SocialAutoUploadConfig)
    xianyu: XianyuConfig = field(default_factory=XianyuConfig)


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"configuration section {key!r} must be a table")
    return value


def _positive_int(
    section: dict[str, Any],
    key: str,
    default: int,
    *,
    allow_zero: bool = False,
) -> int:
    value = section.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"configuration value {key!r} must be an integer")
    parsed = int(value)
    minimum = 0 if allow_zero else 1
    if parsed < minimum:
        raise ValueError(f"configuration value {key!r} must be >= {minimum}")
    return parsed


def load_config(path: str | Path | None = None) -> AppConfig:
    if path is None:
        return AppConfig()

    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    execution = _section(data, "execution")
    social = _section(data, "social_auto_upload")
    xianyu = _section(data, "xianyu")

    workdir = str(social.get("working_directory", "")).strip()
    command = social.get("command", ["sau"])
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        raise ValueError("social_auto_upload.command must be a non-empty string array")
    normalized_command = list(command)
    executable = Path(normalized_command[0]).expanduser()
    if not executable.is_absolute() and len(executable.parts) > 1:
        normalized_command[0] = str((config_path.parent / executable).resolve())

    xianyu_command = xianyu.get("command", ["scripts/run-xianyu-local"])
    if (
        not isinstance(xianyu_command, list)
        or not xianyu_command
        or not all(isinstance(item, str) for item in xianyu_command)
    ):
        raise ValueError("xianyu.command must be a non-empty string array")
    normalized_xianyu_command = list(xianyu_command)
    xianyu_executable = Path(normalized_xianyu_command[0]).expanduser()
    if not xianyu_executable.is_absolute() and len(xianyu_executable.parts) > 1:
        normalized_xianyu_command[0] = str((config_path.parent / xianyu_executable).resolve())

    account_directory = Path(
        xianyu.get("account_directory", ".media-auto-publisher/accounts")
    ).expanduser()
    if not account_directory.is_absolute():
        account_directory = (config_path.parent / account_directory).resolve()

    working_directory: Path | None = None
    if workdir:
        working_directory = Path(workdir).expanduser()
        if not working_directory.is_absolute():
            working_directory = config_path.parent / working_directory
        working_directory = working_directory.resolve()

    return AppConfig(
        execution=ExecutionConfig(
            subprocess_timeout_seconds=_positive_int(execution, "subprocess_timeout_seconds", 900),
        ),
        social_auto_upload=SocialAutoUploadConfig(
            command=tuple(normalized_command),
            working_directory=working_directory,
        ),
        xianyu=XianyuConfig(
            command=tuple(normalized_xianyu_command),
            account_directory=account_directory,
            subprocess_timeout_seconds=_positive_int(
                xianyu, "subprocess_timeout_seconds", 900
            ),
            max_image_bytes=_positive_int(xianyu, "max_image_bytes", 5 * 1024 * 1024),
            max_video_bytes=_positive_int(xianyu, "max_video_bytes", 100 * 1024 * 1024),
        ),
    )
