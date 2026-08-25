from __future__ import annotations

import asyncio
import unittest

from media_auto_publisher.social_local import (
    DOUYIN_NOTE_DEFAULT_DECLARATION,
    DOUYIN_TITLE_SELECTOR,
    fill_douyin_title_and_description,
    install_compatibility_patches,
    upload_douyin_note_content,
)


class RecordingLocator:
    def __init__(self) -> None:
        self.first = self
        self.filled = ""

    async def wait_for(self, **_: object) -> None:
        return None

    async def fill(self, value: str) -> None:
        self.filled = value

    async def click(self) -> None:
        return None


class RecordingKeyboard:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    async def press(self, value: str) -> None:
        self.actions.append(("press", value))

    async def type(self, value: str) -> None:
        self.actions.append(("type", value))


class RecordingPage:
    def __init__(self) -> None:
        self.title = RecordingLocator()
        self.description = RecordingLocator()
        self.keyboard = RecordingKeyboard()

    def locator(self, selector: str) -> RecordingLocator:
        return self.title if selector == DOUYIN_TITLE_SELECTOR else self.description


class SocialLocalCompatibilityTests(unittest.TestCase):
    def test_douyin_title_selector_matches_old_and_new_placeholders(self) -> None:
        self.assertIn('placeholder*="作品标题"', DOUYIN_TITLE_SELECTOR)

        for placeholder in ("填写作品标题", "添加作品标题"):
            self.assertIn("作品标题", placeholder)

    def test_patch_can_be_called_as_an_instance_method(self) -> None:
        class Uploader:
            fill = fill_douyin_title_and_description

            def __init__(self) -> None:
                self._mapub_default_declaration = DOUYIN_NOTE_DEFAULT_DECLARATION
                self.selected_declaration = ""

            async def set_self_declaration(self, _: object, declaration: str) -> bool:
                self.selected_declaration = declaration
                return True

        page = RecordingPage()
        uploader = Uploader()
        asyncio.run(uploader.fill(page, "兼容标题", "兼容正文", ["测试"]))

        self.assertEqual(page.title.filled, "兼容标题")
        self.assertIn(("type", "兼容正文"), page.keyboard.actions)
        self.assertIn(("type", " #测试"), page.keyboard.actions)
        self.assertEqual(uploader.selected_declaration, "无需添加自主声明")

    def test_note_reuses_the_overlay_helper_required_by_declaration(self) -> None:
        install_compatibility_patches()
        from uploader.douyin_uploader.main import DouYinNote

        self.assertTrue(callable(DouYinNote._clear_blocking_overlays))

    def test_note_uses_finite_single_submit_compatibility_flow(self) -> None:
        install_compatibility_patches()
        from uploader.douyin_uploader.main import DouYinNote

        self.assertIs(DouYinNote.upload_note_content, upload_douyin_note_content)


if __name__ == "__main__":
    unittest.main()
