from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request

from .config import AppConfig, load_config
from .models import ContentKind, JobStatus, Platform, PublishJob
from .runner import PublisherRunner
from .store import JobStore


def _config_path(value: str | None) -> str | None:
    if value:
        return value
    default = Path("config.toml")
    return str(default) if default.is_file() else None


def _load(value: str | None) -> tuple[AppConfig, JobStore]:
    config = load_config(_config_path(value))
    return config, JobStore(config.execution.database_path)


def _scheduled(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("schedule must be ISO-8601, e.g. 2026-08-26T20:30:00+08:00") from exc


def _body(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).expanduser().read_text(encoding="utf-8")
    return args.body or ""


def _metadata(args: argparse.Namespace) -> dict[str, Any]:
    if Platform(args.platform) is not Platform.XIANYU:
        return {}
    return {
        "price": args.price,
        "original_price": args.original_price,
        "quantity": args.quantity,
        "address": args.address,
        "address_expected_text": args.address_expected_text,
        "shipping_method": args.shipping_method,
        "platform_category_id": args.category_id,
        "platform_category_name": args.category_name,
    }


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mapub", description="Risk-aware media publishing orchestrator")
    parser.add_argument("--config", help="TOML configuration path; defaults to ./config.toml")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="Initialize the local job database")

    enqueue = commands.add_parser("enqueue", help="Create a publish job")
    enqueue.add_argument("--platform", required=True, choices=[item.value for item in Platform])
    enqueue.add_argument("--account", required=True, help="Account name or Xianyu account_id")
    enqueue.add_argument("--kind", required=True, choices=[item.value for item in ContentKind])
    enqueue.add_argument("--title", required=True)
    body = enqueue.add_mutually_exclusive_group(required=True)
    body.add_argument("--body")
    body.add_argument("--body-file")
    enqueue.add_argument("--media", nargs="+", required=True)
    enqueue.add_argument("--tags", default="", help="Comma-separated tags")
    enqueue.add_argument("--schedule", type=_scheduled)
    enqueue.add_argument("--approve", action="store_true", help="Approve this exact job immediately")
    enqueue.add_argument("--price", type=float)
    enqueue.add_argument("--original-price", type=float)
    enqueue.add_argument("--quantity", type=int, default=1)
    enqueue.add_argument("--address")
    enqueue.add_argument("--address-expected-text", default="")
    enqueue.add_argument("--shipping-method", choices=["free", "none"], default="free")
    enqueue.add_argument("--category-id")
    enqueue.add_argument("--category-name")

    approve = commands.add_parser("approve", help="Approve one waiting job")
    approve.add_argument("job_id")

    listing = commands.add_parser("list", help="List recent jobs")
    listing.add_argument("--limit", type=int, default=50)

    plan = commands.add_parser("plan", help="Preview due jobs without external side effects")
    plan.add_argument("--limit", type=int, default=10)

    run_once = commands.add_parser("run-once", help="Execute at most one due job")
    run_once.add_argument(
        "--live",
        action="store_true",
        help="Perform real publishing; execution.allow_live_publish must also be true",
    )

    unlock = commands.add_parser("unlock-account", help="Unlock an account after manual verification")
    unlock.add_argument("--platform", required=True, choices=[item.value for item in Platform])
    unlock.add_argument("--account", required=True)

    commands.add_parser("doctor", help="Check local adapter dependencies")
    return parser


def _job_view(stored: Any) -> dict[str, Any]:
    return {
        "id": stored.job.id,
        "platform": stored.job.platform.value,
        "account": stored.job.account,
        "kind": stored.job.kind.value,
        "title": stored.job.title,
        "status": stored.status.value,
        "scheduled_at": stored.job.scheduled_at,
        "attempts": stored.attempts,
        "last_error": stored.last_error,
        "result": stored.result,
    }


def _doctor(config: AppConfig) -> dict[str, Any]:
    command = config.social_auto_upload.command[0]
    sau_found = bool(shutil.which(command) or Path(command).expanduser().is_file())
    xianyu_health = f"{config.xianyu.base_url}/health"
    health: dict[str, Any] = {"url": xianyu_health, "reachable": False}
    try:
        with request.urlopen(xianyu_health, timeout=3) as response:
            health.update(reachable=True, status=response.status)
    except (error.URLError, TimeoutError) as exc:
        health["error"] = str(exc)
    return {
        "social_auto_upload": {"command": list(config.social_auto_upload.command), "found": sau_found},
        "xianyu": health,
        "live_publish_enabled": config.execution.allow_live_publish,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config, store = _load(args.config)
        if args.command == "init":
            _print({"database": str(store.path), "initialized": True})
            return 0
        if args.command == "enqueue":
            platform = Platform(args.platform)
            if platform is Platform.XIANYU and (args.price is None or not args.address):
                raise ValueError("xianyu requires --price and --address")
            job = PublishJob(
                platform=platform,
                account=args.account,
                kind=ContentKind(args.kind),
                title=args.title,
                body=_body(args),
                media=tuple(args.media),
                tags=tuple(part.strip() for part in args.tags.split(",") if part.strip()),
                scheduled_at=args.schedule,
                metadata=_metadata(args),
            )
            stored = store.enqueue(job, approved=args.approve)
            _print(_job_view(stored))
            return 0
        if args.command == "approve":
            approved = store.approve(args.job_id)
            _print({"job_id": args.job_id, "approved": approved})
            return 0 if approved else 1
        if args.command == "list":
            _print([_job_view(item) for item in store.list(limit=args.limit)])
            return 0
        if args.command == "plan":
            _print(PublisherRunner(config, store).plan(limit=args.limit))
            return 0
        if args.command == "run-once":
            if not args.live:
                _print(
                    {
                        "executed": False,
                        "reason": "dry safety gate: pass --live to publish",
                        "plan": PublisherRunner(config, store).plan(limit=1),
                    }
                )
                return 0
            if not config.execution.allow_live_publish:
                raise RuntimeError(
                    "live publishing is disabled; set execution.allow_live_publish=true after dry-run verification"
                )
            outcome = PublisherRunner(config, store).run_once()
            _print(asdict(outcome) if outcome else {"executed": False, "reason": "no due jobs"})
            return 0 if outcome is None or outcome.status in {"succeeded", "skipped"} else 2
        if args.command == "unlock-account":
            unlocked = store.unlock_account(Platform(args.platform), args.account)
            _print({"platform": args.platform, "account": args.account, "unlocked": unlocked})
            return 0 if unlocked else 1
        if args.command == "doctor":
            _print(_doctor(config))
            return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1
