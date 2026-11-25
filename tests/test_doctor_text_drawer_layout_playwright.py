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
            page.locator("#localRegistrationDisclosure > summary").click()
            page.locator("#createLocalEncounterButton").click()
            page.get_by_role("button", name="开始接诊", exact=True).first.click()
            page.locator("#encounterView").wait_for()
            text_action = page.locator('.transcript-input-toolbar [data-input-method="text"]')
            opener = text_action
            if width == 320:
                opener = page.locator("#showTranscriptButton")
                opener.click()
            text_action.press("Enter")
            panel = page.locator("#textImportPanel")
            button = page.locator("#submitTextButton")
            editor = page.locator("#conversationInput")
            expect(panel).to_be_visible()
            expect(page.locator("#toast")).not_to_have_text("已开始接诊，请选择撰写方式。")
            close_button = page.locator("#closeDrawerButton")
            expect(close_button).to_be_focused()
            assert page.locator(".doctor-app").evaluate("el => el.inert")
            for key, expected in [("Tab", editor), ("Tab", button), ("Tab", close_button),
                                  ("Shift+Tab", button)]:
                page.keyboard.press(key)
                expect(expected).to_be_focused()
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
            page.keyboard.press("Escape")
            expect(page.locator("#drawer")).to_have_attribute("aria-hidden", "true")
            expect(opener).to_be_focused()
            assert not page.locator(".doctor-app").evaluate("el => el.inert")
            assert page.evaluate("appState.currentTaskId") is None
            browser.close()
    finally:
        server.close()
