"""Isolated layout regression; no ASR or online model invocation."""
import pytest
from playwright.sync_api import expect, sync_playwright

from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


@pytest.mark.parametrize("width,height", [(1440, 900), (320, 640)])
def test_text_import_drawer_keeps_controls_content_sized(width, height):
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            _login(page, server.base_url)
            # Open only the form; creating a patient or model result is unrelated
            # to grid track sizing and must not be required for this regression.
            page.evaluate("openDrawer('textImportPanel', '文本导入生成病历')")
            panel = page.locator("#textImportPanel")
            button = page.locator("#submitTextButton")
            editor = page.locator("#conversationInput")
            expect(panel).to_be_visible()
            editor.fill("[医生]哪里不舒服？\n[患者]昨天开始咳嗽。")
            button.scroll_into_view_if_needed()
            action = button.bounding_box()
            text = editor.bounding_box()
            hint = panel.locator(".form-help").bounding_box()
            assert 42 <= action["height"] <= 64, action
            assert text["y"] - (hint["y"] + hint["height"]) <= 24
            assert action["y"] - (text["y"] + text["height"]) <= 24
            assert action["x"] >= 0 and action["x"] + action["width"] <= width + 1
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            expect(editor).to_have_value("[医生]哪里不舒服？\n[患者]昨天开始咳嗽。")
            assert page.evaluate("appState.currentTaskId") is None
            browser.close()
    finally:
        server.close()
