from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    database_path: Path = Path(".media-auto-publisher/state.db")
    allow_live_publish: bool = False
    subprocess_timeout_seconds: int = 900


@dataclass(frozen=True, slots=True)
class RiskConfig:
    max_posts_per_account_per_day: int = 2
    min_interval_minutes: int = 180
    duplicate_window_days: int = 30
    stop_on_challenge: bool = True


@dataclass(frozen=True, slots=True)
class SocialAutoUploadConfig:
    command: tuple[str, ...] = ("sau",)
    working_directory: Path | None = None


@dataclass(frozen=True, slots=True)
class XianyuConfig:
    base_url: str = "http://127.0.0.1:8089/api/v1"
    secret_env: str = "XIANYU_DISTRIBUTION_SECRET"
    request_timeout_seconds: int = 180


@dataclass(frozen=True, slots=True)
class AppConfig:
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    social_auto_upload: SocialAutoUploadConfig = field(default_factory=SocialAutoUploadConfig)
    xianyu: XianyuConfig = field(default_factory=XianyuConfig)


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"configuration section {key!r} must be a table")
    return value


def load_config(path: str | Path | None = None) -> AppConfig:
    if path is None:
        return AppConfig()

    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    execution = _section(data, "execution")
    risk = _section(data, "risk")
    social = _section(data, "social_auto_upload")
    xianyu = _section(data, "xianyu")

    workdir = str(social.get("working_directory", "")).strip()
    command = social.get("command", ["sau"])
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        raise ValueError("social_auto_upload.command must be a non-empty string array")

    return AppConfig(
        execution=ExecutionConfig(
            database_path=Path(execution.get("database_path", ".media-auto-publisher/state.db")),
            allow_live_publish=bool(execution.get("allow_live_publish", False)),
            subprocess_timeout_seconds=int(execution.get("subprocess_timeout_seconds", 900)),
        ),
        risk=RiskConfig(
            max_posts_per_account_per_day=int(risk.get("max_posts_per_account_per_day", 2)),
            min_interval_minutes=int(risk.get("min_interval_minutes", 180)),
            duplicate_window_days=int(risk.get("duplicate_window_days", 30)),
            stop_on_challenge=bool(risk.get("stop_on_challenge", True)),
        ),
        social_auto_upload=SocialAutoUploadConfig(
            command=tuple(command),
            working_directory=Path(workdir).expanduser().resolve() if workdir else None,
        ),
        xianyu=XianyuConfig(
            base_url=str(xianyu.get("base_url", "http://127.0.0.1:8089/api/v1")).rstrip("/"),
            secret_env=str(xianyu.get("secret_env", "XIANYU_DISTRIBUTION_SECRET")),
            request_timeout_seconds=int(xianyu.get("request_timeout_seconds", 180)),
        ),
    )

