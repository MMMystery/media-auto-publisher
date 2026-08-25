from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sys
import types
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .adapters import SocialAutoUploadAdapter, XianyuAutoReplyAdapter
from .config import ExecutionConfig, SocialAutoUploadConfig, XianyuConfig
from .models import ContentKind, Platform, PublishJob


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_BROWSER_ROOT = PROJECT_ROOT / ".playwright-browsers"
if LOCAL_BROWSER_ROOT.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(LOCAL_BROWSER_ROOT))
SOCIAL_ROOT = PROJECT_ROOT / "third_party" / "social-auto-upload"
XIANYU_ROOT = PROJECT_ROOT / "third_party" / "xianyu-auto-reply"
DATA_ROOT = Path(os.environ.get("MAPUB_DATA_DIR", PROJECT_ROOT / ".media-auto-publisher")).resolve()
ACCOUNT_ROOT = DATA_ROOT / "accounts"
UPLOAD_ROOT = DATA_ROOT / "uploads"
STATIC_ROOT = Path(__file__).with_name("web_static")

JOBS: dict[str, dict[str, Any]] = {}
_XIANYU_QR_MANAGER: Any = None


def _now_job(kind: str, platform: str, account: str) -> tuple[str, dict[str, Any]]:
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "kind": kind,
        "platform": platform,
        "account": account,
        "status": "starting",
        "message": "正在准备…",
        "qr_code": None,
        "result": None,
    }
    JOBS[job_id] = job
    return job_id, job


def _safe_account(value: str) -> str:
    cleaned = re.sub(r"[^\w-]+", "_", value.strip(), flags=re.UNICODE).strip("_")
    if not cleaned:
        raise ValueError("账号名称不能为空")
    return cleaned


def _social_account_file(platform: str, account: str) -> Path:
    return SOCIAL_ROOT / "cookies" / f"{platform}_{_safe_account(account)}.json"


def _xianyu_config() -> XianyuConfig:
    return XianyuConfig(
        command=(sys.executable, "-m", "media_auto_publisher.xianyu_local"),
        account_directory=ACCOUNT_ROOT,
    )


def _publisher(platform: Platform):
    execution = ExecutionConfig()
    if platform in {Platform.DOUYIN, Platform.XIAOHONGSHU}:
        return SocialAutoUploadAdapter(
            SocialAutoUploadConfig(
                command=(sys.executable, "-m", "media_auto_publisher.social_local"),
                working_directory=SOCIAL_ROOT,
            ),
            execution,
        )
    return XianyuAutoReplyAdapter(_xianyu_config(), execution)


def _prepare_social_imports() -> None:
    if not (SOCIAL_ROOT / "conf.py").is_file():
        example = SOCIAL_ROOT / "conf.example.py"
        if example.is_file():
            (SOCIAL_ROOT / "conf.py").write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    if str(SOCIAL_ROOT) not in sys.path:
        sys.path.insert(0, str(SOCIAL_ROOT))


async def _run_social_login(job_id: str, platform: Platform, account: str) -> None:
    job = JOBS[job_id]
    try:
        _prepare_social_imports()
        account_file = _social_account_file(platform.value, account)
        account_file.parent.mkdir(parents=True, exist_ok=True)

        async def on_qrcode(payload: dict[str, Any]) -> None:
            job.update(
                status="waiting_scan",
                message=f"请使用{('抖音' if platform is Platform.DOUYIN else '小红书')} App 扫码",
                qr_code=payload.get("image_data_url"),
            )

        if platform is Platform.DOUYIN:
            from uploader.douyin_uploader.main import douyin_setup

            result = await douyin_setup(
                str(account_file),
                handle=True,
                return_detail=True,
                qrcode_callback=on_qrcode,
                headless=True,
            )
        else:
            from uploader.xiaohongshu_uploader.main import xiaohongshu_setup

            result = await xiaohongshu_setup(
                str(account_file),
                handle=True,
                return_detail=True,
                qrcode_callback=on_qrcode,
                headless=True,
            )
        if result.get("success"):
            job.update(status="succeeded", message="登录成功", qr_code=None)
        else:
            job.update(status="failed", message=str(result.get("message") or "登录失败"))
    except Exception as exc:
        job.update(status="failed", message=f"登录失败：{str(exc)[:300]}")


def _load_xianyu_qr_manager() -> Any:
    global _XIANYU_QR_MANAGER
    if _XIANYU_QR_MANAGER is not None:
        return _XIANYU_QR_MANAGER

    backend = XIANYU_ROOT / "backend-web"
    qr_root = backend / "app" / "services" / "qr_login"
    if not (qr_root / "manager.py").is_file():
        raise RuntimeError("xianyu-auto-reply 子模块不完整")
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    for name, path in (
        ("app", backend / "app"),
        ("app.services", backend / "app" / "services"),
        ("app.services.qr_login", qr_root),
    ):
        package = types.ModuleType(name)
        package.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = package

    face_name = "app.services.qr_login.face_verification"
    face_spec = importlib.util.spec_from_file_location(face_name, qr_root / "face_verification.py")
    if face_spec is None or face_spec.loader is None:
        raise RuntimeError("无法加载闲鱼验证模块")
    face_module = importlib.util.module_from_spec(face_spec)
    sys.modules[face_name] = face_module
    face_spec.loader.exec_module(face_module)

    manager_name = "app.services.qr_login.manager"
    manager_spec = importlib.util.spec_from_file_location(manager_name, qr_root / "manager.py")
    if manager_spec is None or manager_spec.loader is None:
        raise RuntimeError("无法加载闲鱼登录模块")
    manager_module = importlib.util.module_from_spec(manager_spec)
    sys.modules[manager_name] = manager_module
    manager_spec.loader.exec_module(manager_module)
    _XIANYU_QR_MANAGER = manager_module.QRLoginManager()
    return _XIANYU_QR_MANAGER


async def _run_xianyu_login(job_id: str, account: str) -> None:
    job = JOBS[job_id]
    try:
        manager = _load_xianyu_qr_manager()
        generated = await manager.generate_qr_code()
        if not generated.get("success"):
            job.update(status="failed", message=str(generated.get("message") or "二维码生成失败"))
            return
        session_id = str(generated["session_id"])
        job.update(
            status="waiting_scan",
            message="请使用闲鱼 App 扫码",
            qr_code=generated.get("qr_code_url"),
        )
        for _ in range(375):
            status = manager.get_session_status(session_id)
            current = str(status.get("status") or "waiting")
            if current == "success":
                ACCOUNT_ROOT.mkdir(parents=True, exist_ok=True)
                target = XianyuAutoReplyAdapter(_xianyu_config(), ExecutionConfig()).account_file(account)
                target.write_text(
                    json.dumps(
                        {"cookie_string": status.get("cookies"), "unb": status.get("unb")},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                os.chmod(target, 0o600)
                job.update(status="succeeded", message="登录成功", qr_code=None)
                return
            if current == "verification_required":
                job.update(
                    status="waiting_scan",
                    message=str(status.get("message") or "请完成人脸验证"),
                    qr_code=status.get("face_qr_url") or job.get("qr_code"),
                )
            elif current == "scanned":
                job.update(status="waiting_scan", message="已扫码，请在手机上确认")
            elif current in {"expired", "cancelled", "not_found"}:
                job.update(status="failed", message="二维码已失效，请重新登录")
                return
            await asyncio.sleep(0.8)
        job.update(status="failed", message="等待扫码超时，请重新登录")
    except Exception as exc:
        job.update(status="failed", message=f"登录失败：{str(exc)[:300]}")


async def _run_publish(job_id: str, publish_job: PublishJob) -> None:
    job = JOBS[job_id]
    job.update(status="running", message="正在打开发布页面并上传素材…")
    try:
        result = await asyncio.to_thread(
            _publisher(publish_job.platform).publish,
            publish_job,
            live_authorized=True,
        )
        job.update(
            status="succeeded" if result.success else "failed",
            message=result.message,
            result=result.safe_dict(),
        )
    except Exception as exc:
        job.update(status="failed", message=f"发布失败：{str(exc)[:500]}")


def create_app() -> FastAPI:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    ACCOUNT_ROOT.mkdir(parents=True, exist_ok=True)
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="发稿台", docs_url="/api/docs", redoc_url=None)
    app.mount("/assets", StaticFiles(directory=STATIC_ROOT), name="assets")

    @app.middleware("http")
    async def disable_local_ui_cache(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    @app.get("/api/health")
    async def health(account: str = "main") -> dict[str, Any]:
        safe = _safe_account(account)
        xianyu_file = XianyuAutoReplyAdapter(_xianyu_config(), ExecutionConfig()).account_file(safe)
        return {
            "ok": True,
            "accounts": {
                "douyin": _social_account_file("douyin", safe).is_file(),
                "xiaohongshu": _social_account_file("xiaohongshu", safe).is_file(),
                "xianyu": xianyu_file.is_file(),
            },
        }

    @app.post("/api/login")
    async def login(platform: str = Form(...), account: str = Form("main")) -> dict[str, str]:
        try:
            target = Platform(platform)
            safe = _safe_account(account)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        job_id, _ = _now_job("login", target.value, safe)
        if target is Platform.XIANYU:
            asyncio.create_task(_run_xianyu_login(job_id, safe))
        else:
            asyncio.create_task(_run_social_login(job_id, target, safe))
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        if job_id not in JOBS:
            raise HTTPException(status_code=404, detail="任务不存在")
        return JOBS[job_id]

    @app.post("/api/publish")
    async def publish(
        platform: str = Form(...),
        account: str = Form("main"),
        kind: str = Form("note"),
        title: str = Form(...),
        body: str = Form(...),
        tags: str = Form(""),
        price: str = Form(""),
        original_price: str = Form(""),
        address: str = Form(""),
        shipping_method: str = Form("free"),
        media: list[UploadFile] = File(...),
    ) -> dict[str, str]:
        try:
            target = Platform(platform)
            safe = _safe_account(account)
            if not title.strip() or not body.strip():
                raise ValueError("请填写标题和正文")
            if target is Platform.DOUYIN and len(title.strip()) > 20:
                raise ValueError(f"抖音标题最多 20 个字符，当前 {len(title.strip())} 个字符")
            job_id, _ = _now_job("publish", target.value, safe)
            upload_dir = UPLOAD_ROOT / job_id
            upload_dir.mkdir(parents=True, exist_ok=False)
            media_paths: list[str] = []
            for index, upload in enumerate(media, 1):
                suffix = Path(upload.filename or "").suffix.lower()
                if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v", ".webm"}:
                    raise ValueError(f"不支持的素材格式：{upload.filename}")
                target_file = upload_dir / f"{index:02d}{suffix}"
                with target_file.open("wb") as handle:
                    while chunk := await upload.read(1024 * 1024):
                        handle.write(chunk)
                media_paths.append(str(target_file))

            metadata: dict[str, Any] = {}
            content_kind = ContentKind(kind)
            if target is Platform.XIANYU:
                if not price or not address.strip():
                    raise ValueError("闲鱼商品需要填写价格和所在地")
                content_kind = ContentKind.LISTING
                metadata = {
                    "price": float(price),
                    "original_price": float(original_price) if original_price else None,
                    "address": address,
                    "shipping_method": shipping_method,
                }
            publish_job = PublishJob(
                platform=target,
                account=safe,
                kind=content_kind,
                title=title,
                body=body,
                media=tuple(media_paths),
                tags=tuple(item.strip().lstrip("#") for item in tags.split(",") if item.strip()),
                metadata=metadata,
            )
            asyncio.create_task(_run_publish(job_id, publish_job))
            return {"job_id": job_id}
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()
