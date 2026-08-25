from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from typing import Any


RESULT_PREFIX = "MAPUB_RESULT="


def _upstream_paths() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[2] / "third_party" / "xianyu-auto-reply"
    return root, root / "backend-web"


def _load_publisher_class() -> type[Any]:
    root, backend = _upstream_paths()
    publisher_path = backend / "app" / "services" / "xianyu_publisher.py"
    if not publisher_path.is_file():
        raise RuntimeError("xianyu-auto-reply submodule is missing")
    sys.path[:0] = [str(root), str(backend)]

    # Both upstream package __init__ files import the entire database backend.
    # The local tool only needs two lightweight helper modules, so expose their
    # package paths without importing the unrelated SQLAlchemy services.
    for name, path in (
        ("common.services", root / "common" / "services"),
        ("common.utils", root / "common" / "utils"),
    ):
        package = types.ModuleType(name)
        package.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = package

    spec = importlib.util.spec_from_file_location("mapub_xianyu_publisher", publisher_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the Xianyu publisher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.XianyuPublisher


def _cookie_string(state: dict[str, Any]) -> str:
    saved = str(state.get("cookie_string") or "").strip()
    if saved:
        return saved
    allowed_domains = ("goofish.com", "taobao.com", "alipay.com")
    pairs: dict[str, str] = {}
    for cookie in state.get("cookies") or []:
        domain = str(cookie.get("domain") or "")
        name = str(cookie.get("name") or "")
        value = str(cookie.get("value") or "")
        if name and value and any(domain.endswith(item) for item in allowed_domains):
            pairs[name] = value
    return "; ".join(f"{name}={value}" for name, value in pairs.items())


def _has_login(state: dict[str, Any]) -> bool:
    if str(state.get("cookie_string") or "").strip() and str(state.get("unb") or "").strip():
        return True
    names = {
        str(cookie.get("name") or "")
        for cookie in state.get("cookies") or []
        if str(cookie.get("value") or "")
    }
    return bool(names & {"unb", "munb"})


async def _login(state_path: Path) -> int:
    from playwright.async_api import async_playwright

    state_path.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.goofish.com", wait_until="domcontentloaded")
        print("请在打开的浏览器里登录闲鱼；确认首页已显示你的账号后，回到终端按回车。")
        await asyncio.to_thread(input)
        state = await context.storage_state()
        cookies = _cookie_string(state)
        if not cookies or not _has_login(state):
            await browser.close()
            print("没有检测到闲鱼登录信息，请重新登录。", file=sys.stderr)
            return 2
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.chmod(state_path, 0o600)
        await browser.close()
    print(f"闲鱼登录已保存：{state_path}")
    return 0


async def _post(args: argparse.Namespace) -> int:
    state_path = Path(args.state).expanduser().resolve()
    if not state_path.is_file():
        print(f"missing login state: {state_path}", file=sys.stderr)
        return 2
    state = json.loads(state_path.read_text(encoding="utf-8"))
    cookie = _cookie_string(state)
    if not cookie or not _has_login(state):
        print("saved Xianyu login is empty; log in again", file=sys.stderr)
        return 2

    XianyuPublisher = _load_publisher_class()

    images = [path for path in args.media if Path(path).suffix.lower() not in {".mp4", ".mov", ".m4v", ".webm"}]
    videos = [path for path in args.media if path not in images]
    item_data = {
        "title": args.title,
        "description": args.body,
        "images": images,
        "videos": videos,
        "price": args.price,
        "original_price": args.original_price,
        "quantity": 1,
        "address": args.address,
        "shipping_method": args.shipping_method,
    }
    publisher = XianyuPublisher()
    result = await publisher.publish_item(item_data, {"cookie": cookie})
    result.pop("screenshot", None)
    print(f"{RESULT_PREFIX}{json.dumps(result, ensure_ascii=False)}")
    return 0 if result.get("success") else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Xianyu login and publisher")
    commands = parser.add_subparsers(dest="command", required=True)
    login = commands.add_parser("login")
    login.add_argument("--account", required=True)
    login.add_argument("--state", required=True)
    post = commands.add_parser("post")
    post.add_argument("--account", required=True)
    post.add_argument("--state", required=True)
    post.add_argument("--title", required=True)
    post.add_argument("--body", required=True)
    post.add_argument("--media", nargs="+", required=True)
    post.add_argument("--price", type=float, required=True)
    post.add_argument("--original-price", type=float)
    post.add_argument("--address", required=True)
    post.add_argument("--shipping-method", choices=["free", "none"], default="free")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "login":
            return asyncio.run(_login(Path(args.state).expanduser().resolve()))
        return asyncio.run(_post(args))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
