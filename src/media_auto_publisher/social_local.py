from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Sequence


SOCIAL_ROOT = Path(__file__).resolve().parents[2] / "third_party" / "social-auto-upload"
DOUYIN_TITLE_SELECTOR = 'input[placeholder*="作品标题"]:visible'
DOUYIN_DESCRIPTION_SELECTOR = (
    'div[contenteditable="true"][data-placeholder*="作品描述"]:visible, '
    'div.zone-container[contenteditable="true"]:visible'
)
DOUYIN_NOTE_DEFAULT_DECLARATION = "无需添加自主声明"
DOUYIN_NOTE_SUCCESS_URL_PART = "/creator-micro/content/manage"
DOUYIN_NOTE_SUBMIT_TIMEOUT_SECONDS = 90


async def fill_douyin_title_and_description(
    self: Any,
    page: Any,
    title: str,
    description: str,
    tags: list[str] | None = None,
) -> None:
    """Fill both the old and current Douyin creator form variants."""
    title_input = page.locator(DOUYIN_TITLE_SELECTOR).first
    await title_input.wait_for(state="visible", timeout=120000)
    await title_input.fill(title[:20])

    description_editor = page.locator(DOUYIN_DESCRIPTION_SELECTOR).first
    await description_editor.wait_for(state="visible", timeout=120000)
    await description_editor.click()
    await page.keyboard.press("Control+KeyA")
    await page.keyboard.press("Delete")

    if description and description.strip():
        await page.keyboard.type(description.strip())
    for tag in tags or []:
        await page.keyboard.type(" #" + tag)
        await page.keyboard.press("Space")
    await page.keyboard.press("Escape")

    declaration = getattr(self, "_mapub_default_declaration", None)
    if declaration:
        selected = await self.set_self_declaration(page, declaration)
        if not selected:
            raise RuntimeError(f"抖音自主声明“{declaration}”设置失败")


async def _visible_douyin_feedback(page: Any) -> list[str]:
    """Return concise, currently visible feedback from Douyin's publish page."""
    messages: list[str] = []
    selectors = (
        '[role="alert"]:visible',
        ".semi-toast-content:visible",
        ".semi-notification-content:visible",
        ".semi-modal-content:visible",
    )
    for selector in selectors:
        try:
            for value in await page.locator(selector).all_text_contents():
                normalized = " ".join(value.split())
                if normalized and normalized not in messages:
                    messages.append(normalized[:240])
        except Exception:
            continue
    return messages


async def _confirm_douyin_publish_dialog(page: Any) -> bool:
    """Confirm a real publish confirmation dialog once, when Douyin shows one."""
    try:
        dialog = page.locator(".semi-modal-content:visible").last
        if not await dialog.count():
            return False
        text = " ".join((await dialog.inner_text()).split())
        if not any(marker in text for marker in ("确认发布", "是否发布", "继续发布")):
            return False
        for name in ("确认发布", "继续发布", "确定"):
            button = dialog.get_by_role("button", name=name, exact=True).first
            if await button.count() and await button.is_visible() and await button.is_enabled():
                await button.click(timeout=5000)
                return True
    except Exception:
        return False
    return False


async def upload_douyin_note_content(self: Any, page: Any) -> None:
    """Upload a Douyin note and submit it exactly once with a finite result wait.

    The upstream implementation clicks Publish in an unbounded loop and only
    accepts one legacy redirect URL.  Current Douyin pages may redirect without
    that query string, which made a successful click look like a permanent hang
    and could issue duplicate submissions.
    """
    from uploader.douyin_uploader.main import _msg, douyin_logger

    douyin_logger.info(_msg("🏃", f"小人开始搬运图文，共 {len(self.image_paths)} 张图片"))
    douyin_logger.info(_msg("🔀", "小人正在切换到图文发布"))
    await page.get_by_text("发布图文", exact=True).click()
    await page.wait_for_timeout(1000)

    douyin_logger.info(_msg("📤", "小人正在上传图片"))
    await page.locator("div[class^='container'] input[accept*='image']").set_input_files(self.image_paths)
    await page.wait_for_url("**/creator-micro/content/post/image?**", timeout=120000)
    douyin_logger.info(_msg("🥳", "已经进入图文发布页面"))

    await page.wait_for_timeout(1000)
    douyin_logger.info(_msg("✍️", "小人开始填标题、描述和话题"))
    await self.fill_title_and_description(page, self.title, self.note, self.tags)
    title_len = len(self.title) if self.title else 0
    tags_text = " ".join(f"#{tag}" for tag in self.tags) if self.tags else ""
    desc_and_tags_len = len(self.note or "") + (len(tags_text) + 2 if self.tags else 0)
    douyin_logger.info(_msg("📝", f"标题总字数: {title_len}，描述+话题总字数: {desc_and_tags_len}"))
    douyin_logger.info(_msg("🏷️", f"小人一共贴了 {len(self.tags)} 个话题"))

    if self.bgm:
        await self.select_bgm(page, self.bgm)
    if self.publish_strategy == "scheduled" and self.publish_date != 0:
        await self.set_schedule_time_douyin(page, self.publish_date)

    await self._clear_blocking_overlays(page)
    publish_button = page.get_by_role("button", name="发布", exact=True).first
    await publish_button.wait_for(state="visible", timeout=30000)
    if not await publish_button.is_enabled():
        feedback = await _visible_douyin_feedback(page)
        detail = "；".join(feedback) or "发布按钮不可用，请检查封面、图片和必填项"
        raise RuntimeError(f"抖音未接受发布：{detail}")

    douyin_logger.info(_msg("🚀", "发布信息已填写完成，正在提交一次"))
    try:
        await publish_button.click(timeout=10000, no_wait_after=True)
    except Exception as exc:
        feedback = await _visible_douyin_feedback(page)
        detail = "；".join(feedback) or str(exc)
        raise RuntimeError(f"抖音发布按钮点击失败：{detail}") from exc
    await page.wait_for_timeout(500)
    if await _confirm_douyin_publish_dialog(page):
        douyin_logger.info(_msg("✅", "已确认抖音发布提示"))

    hard_error_markers = (
        "发布失败",
        "上传失败",
        "不能为空",
        "请设置封面",
        "没有选择封面",
        "请添加图片",
        "请填写",
        "违规",
        "审核不通过",
    )
    last_feedback: list[str] = []
    deadline = asyncio.get_running_loop().time() + DOUYIN_NOTE_SUBMIT_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        current_url = page.url
        if DOUYIN_NOTE_SUCCESS_URL_PART in current_url or any(
            marker in current_url.lower() for marker in ("publish-success", "publish_success")
        ):
            douyin_logger.success(_msg("🥳", "图文发布成功，小人开心收工"))
            return

        try:
            success_text = page.get_by_text("发布成功", exact=False).first
            if await success_text.count() and await success_text.is_visible():
                douyin_logger.success(_msg("🥳", "图文发布成功，小人开心收工"))
                return
        except Exception:
            pass

        feedback = await _visible_douyin_feedback(page)
        if feedback:
            last_feedback = feedback
            joined = "；".join(feedback)
            if any(marker in joined for marker in hard_error_markers):
                raise RuntimeError(f"抖音拒绝发布：{joined}")
        await page.wait_for_timeout(1000)

    detail = "；".join(last_feedback) or "页面未返回成功或失败提示"
    raise RuntimeError(f"抖音提交后 {DOUYIN_NOTE_SUBMIT_TIMEOUT_SECONDS} 秒仍无结果：{detail}；当前页面 {page.url}")


def install_compatibility_patches() -> Any:
    if not (SOCIAL_ROOT / "sau_cli.py").is_file():
        raise RuntimeError("social-auto-upload submodule is missing")
    if str(SOCIAL_ROOT) not in sys.path:
        sys.path.insert(0, str(SOCIAL_ROOT))

    import sau_cli
    from uploader.douyin_uploader.main import DouYinBaseUploader, DouYinNote, DouYinVideo

    DouYinBaseUploader.fill_title_and_description = fill_douyin_title_and_description
    DouYinNote._clear_blocking_overlays = DouYinVideo._clear_blocking_overlays
    DouYinNote._mapub_default_declaration = DOUYIN_NOTE_DEFAULT_DECLARATION
    DouYinNote.upload_note_content = upload_douyin_note_content
    return sau_cli


def main(argv: Sequence[str] | None = None) -> int:
    sau_cli = install_compatibility_patches()
    return int(sau_cli.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
