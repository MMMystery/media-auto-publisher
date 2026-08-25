from __future__ import annotations

import json
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request

from ..config import XianyuConfig
from ..models import ContentKind, Platform, PublishJob
from .base import PublishResult, PublisherAdapter


CHALLENGE_MARKERS = ("captcha", "challenge", "验证码", "滑块", "人脸", "风控", "验证")


def _multipart(fields: dict[str, str], file_path: str) -> tuple[bytes, str]:
    boundary = f"----mapub-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    path = Path(file_path)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class XianyuAutoReplyAdapter(PublisherAdapter):
    def __init__(self, config: XianyuConfig) -> None:
        self.config = config

    def _secret(self) -> str:
        secret = os.environ.get(self.config.secret_env, "").strip()
        if not secret:
            raise RuntimeError(f"missing environment variable: {self.config.secret_env}")
        return secret

    def _validate(self, job: PublishJob) -> None:
        if job.platform is not Platform.XIANYU or job.kind is not ContentKind.LISTING:
            raise ValueError("xianyu adapter only accepts listing jobs")
        if not job.metadata.get("price"):
            raise ValueError("xianyu listing requires metadata.price")
        if not str(job.metadata.get("address", "")).strip():
            raise ValueError("xianyu listing requires metadata.address")

    def preview(self, job: PublishJob) -> dict[str, Any]:
        self._validate(job)
        return {
            "adapter": "xianyu-auto-reply",
            "platform": job.platform.value,
            "account_id": job.account,
            "media_count": len(job.media),
            "price": job.metadata["price"],
            "address": job.metadata["address"],
            "endpoint": f"{self.config.base_url}/external/publish/single",
            "secret_source": f"environment:{self.config.secret_env}",
        }

    def _json_request(self, url: str, *, data: bytes, content_type: str) -> dict[str, Any]:
        req = request.Request(
            url,
            data=data,
            headers={"Content-Type": content_type, "Accept": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.config.request_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _upload_media(self, job: PublishJob, path: str, media_type: str) -> str:
        body, content_type = _multipart(
            {
                "secret_key": self._secret(),
                "account_id": job.account,
                "media_type": media_type,
            },
            path,
        )
        payload = self._json_request(
            f"{self.config.base_url}/external/publish/media",
            data=body,
            content_type=content_type,
        )
        if not payload.get("success"):
            raise RuntimeError(str(payload.get("message") or "media upload failed"))
        media_id = (payload.get("data") or {}).get("media_id")
        if not media_id:
            raise RuntimeError("media upload response did not include media_id")
        return str(media_id)

    def publish(self, job: PublishJob) -> PublishResult:
        try:
            self._validate(job)
            image_ids: list[str] = []
            video_ids: list[str] = []
            for path in job.media:
                is_video = Path(path).suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}
                target = video_ids if is_video else image_ids
                target.append(self._upload_media(job, path, "video" if is_video else "image"))

            payload = {
                "secret_key": self._secret(),
                "account_id": job.account,
                "title": job.title,
                "description": job.body,
                "price": float(job.metadata["price"]),
                "original_price": job.metadata.get("original_price"),
                "image_media_ids": image_ids,
                "video_media_ids": video_ids,
                "quantity": int(job.metadata.get("quantity", 1)),
                "address": str(job.metadata["address"]),
                "address_expected_text": str(job.metadata.get("address_expected_text", "")),
                "shipping_method": str(job.metadata.get("shipping_method", "free")),
                "platform_category_id": job.metadata.get("platform_category_id"),
                "platform_category_name": job.metadata.get("platform_category_name"),
            }
            response = self._json_request(
                f"{self.config.base_url}/external/publish/single",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
            )
            message = str(response.get("message") or "publish request completed")
            lowered = message.lower()
            challenge = any(marker in lowered for marker in CHALLENGE_MARKERS)
            data = response.get("data") or {}
            return PublishResult(
                success=bool(response.get("success")) and not challenge,
                message=message,
                external_id=str(data.get("item_id")) if data.get("item_id") else None,
                external_url=str(data.get("item_url")) if data.get("item_url") else None,
                challenge_required=challenge,
                retryable=not challenge and not bool(response.get("success")),
                details={
                    "log_id": data.get("log_id"),
                    "sync_status": data.get("sync_status"),
                },
            )
        except (error.URLError, TimeoutError) as exc:
            return PublishResult(False, f"xianyu service unavailable: {exc}", retryable=True)
        except Exception as exc:
            message = str(exc)
            challenge = any(marker in message.lower() for marker in CHALLENGE_MARKERS)
            return PublishResult(
                False,
                message,
                challenge_required=challenge,
                retryable=not challenge,
            )

