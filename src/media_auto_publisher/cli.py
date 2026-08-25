from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .adapters import SocialAutoUploadAdapter, XianyuAutoReplyAdapter
from .config import AppConfig, load_config
from .models import ContentKind, Platform, PublishJob


def _config_path(value: str | None) -> str | None:
    if value:
        return value
    default = Path("config.toml")
    return str(default) if default.is_file() else None


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _body(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).expanduser().read_text(encoding="utf-8")
    return args.body or ""


def _adapters(config: AppConfig) -> dict[Platform, Any]:
    social = SocialAutoUploadAdapter(config.social_auto_upload, config.execution)
    return {
        Platform.DOUYIN: social,
        Platform.XIAOHONGSHU: social,
        Platform.XIANYU: XianyuAutoReplyAdapter(config.xianyu, config.execution),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mapub", description="抖音、小红书和闲鱼本地发布工具")
    parser.add_argument("--config", help="配置文件，默认读取 ./config.toml")
    commands = parser.add_subparsers(dest="command", required=True)

    login = commands.add_parser("login", help="首次登录一个平台账号")
    login.add_argument("platform", choices=[item.value for item in Platform])
    login.add_argument("--account", default="main", help="本地账号名称")

    post = commands.add_parser("post", help="预览或直接发布一条内容")
    post.add_argument("--platform", required=True, choices=[item.value for item in Platform])
    post.add_argument("--account", default="main", help="登录时使用的本地账号名称")
    post.add_argument("--kind", choices=[ContentKind.NOTE.value, ContentKind.VIDEO.value])
    post.add_argument("--title", required=True)
    post_body = post.add_mutually_exclusive_group(required=True)
    post_body.add_argument("--body")
    post_body.add_argument("--body-file")
    post.add_argument("--media", nargs="+", required=True)
    post.add_argument("--tags", default="", help="逗号分隔的话题")
    post.add_argument("--price", type=float, help="闲鱼售价")
    post.add_argument("--original-price", type=float, help="闲鱼原价")
    post.add_argument("--address", help="闲鱼所在地，例如：上海市浦东新区")
    post.add_argument("--shipping-method", choices=["free", "none"], default="free")
    post.add_argument("--publish", action="store_true", help="确认真实发布；不加时只预览")

    commands.add_parser("doctor", help="检查本地运行环境")
    web = commands.add_parser("web", help="启动本地操作页面")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    return parser


def _job(args: argparse.Namespace) -> PublishJob:
    platform = Platform(args.platform)
    if platform is Platform.XIANYU:
        if args.price is None or not args.address:
            raise ValueError("闲鱼发布需要 --price 和 --address")
        kind = ContentKind.LISTING
        metadata = {
            "price": args.price,
            "original_price": args.original_price,
            "address": args.address,
            "shipping_method": args.shipping_method,
        }
    else:
        kind = ContentKind(args.kind or ContentKind.NOTE.value)
        metadata = {}
    return PublishJob(
        platform=platform,
        account=args.account,
        kind=kind,
        title=args.title,
        body=_body(args),
        media=tuple(args.media),
        tags=tuple(part.strip() for part in args.tags.split(",") if part.strip()),
        metadata=metadata,
    )


def _login(config: AppConfig, platform: Platform, account: str) -> int:
    if platform is Platform.XIANYU:
        adapter = XianyuAutoReplyAdapter(config.xianyu, config.execution)
        command = adapter.login_command(account)
        working_directory = None
    else:
        command = [
            *config.social_auto_upload.command,
            platform.value,
            "login",
            "--account",
            account,
            "--headed",
        ]
        working_directory = config.social_auto_upload.working_directory
    return subprocess.run(command, cwd=working_directory, check=False).returncode


def _doctor(config: AppConfig) -> dict[str, Any]:
    social_command = config.social_auto_upload.command[0]
    social_path = Path(social_command).expanduser()
    social_found = bool(shutil.which(social_command) or social_path.is_file())
    social_runnable = False
    if social_found:
        try:
            completed = subprocess.run(
                [*config.social_auto_upload.command, "--help"],
                cwd=config.social_auto_upload.working_directory,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            social_runnable = completed.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass

    xianyu_command = config.xianyu.command[0]
    xianyu_path = Path(xianyu_command).expanduser()
    return {
        "douyin_xiaohongshu": {"installed": social_found, "runnable": social_runnable},
        "xianyu": {
            "installed": bool(shutil.which(xianyu_command) or xianyu_path.is_file()),
            "saved_accounts": len(list(config.xianyu.account_directory.glob("xianyu_*.json")))
            if config.xianyu.account_directory.is_dir()
            else 0,
        },
        "docker_required": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(_config_path(args.config))
        if args.command == "login":
            return _login(config, Platform(args.platform), args.account)
        if args.command == "post":
            job = _job(args)
            adapter = _adapters(config)[job.platform]
            if not args.publish:
                _print({"published": False, "preview": adapter.preview(job)})
                return 0
            result = adapter.publish(job, live_authorized=True)
            _print(result.safe_dict())
            return 0 if result.success else 2
        if args.command == "doctor":
            _print(_doctor(config))
            return 0
        if args.command == "web":
            import uvicorn

            uvicorn.run(
                "media_auto_publisher.web:app",
                host=args.host,
                port=args.port,
                log_level="info",
            )
            return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1
