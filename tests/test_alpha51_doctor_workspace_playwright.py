"""Approved V3.4 layout wired to the real doctor page and API test server.

The server fixture uses a synthetic patient and Mock provider; these checks prove
layout and controls, never the three real-provider paths required by WBS 5.1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from tests.test_doctor_itemized_approval_playwright import (
    RunningServer,
    _login,
    _prepare_review_fixture,
)


ROOT = Path(__file__).resolve().parents[1]


def test_step_labels_fit_their_own_boxes_and_remain_keyboard_reachable() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright, playwright.chromium.launch() as browser:
            page = browser.new_page()
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            steps = page.locator("#workflowSteps")
            for width in (390, 360, 1366):
                page.set_viewport_size({"width": width, "height": 844})
                steps.focus()
                page.keyboard.press("Tab")
                page.keyboard.press("Shift+Tab")
                assert steps.evaluate("list => list === document.activeElement")
                assert steps.locator(".workflow-index").all_text_contents() == ["1", "2", "3", "4", "5"]
                assert steps.locator(".workflow-label").all_text_contents()[:4] == ["选择就诊", "采集信息", "AI处理", "病历审核"]
                bounds = steps.evaluate("""list => [...list.children].map(item => {
                  const range = document.createRange();
                  range.selectNodeContents(item.querySelector('.workflow-label'));
                  const text = range.getBoundingClientRect(), box = item.getBoundingClientRect();
                  const number = item.querySelector('.workflow-index').getBoundingClientRect();
                  return text.left >= box.left - 1 && text.right <= box.right + 1
                     && (number.bottom <= text.top + 1 || number.right <= text.left + 1);
                })""")
                assert all(bounds), (width, bounds)
                for key, side in [("ArrowLeft", "first"), ("ArrowRight", "last")]:
                    page.keyboard.press(key)
                    page.wait_for_function("""side => {
                      const list = document.querySelector('#workflowSteps');
                      const item = side === 'first' ? list.firstElementChild : list.lastElementChild;
                      const range = document.createRange(); range.selectNodeContents(item.querySelector('.workflow-label'));
                      const box = list.getBoundingClientRect(), text = range.getBoundingClientRect();
                      return text.left >= box.left - 1 && text.right <= box.right + 1;
                    }""", arg=side)
                assert page.evaluate("document.documentElement.scrollWidth") == width
    finally:
        server.close()


@pytest.mark.parametrize("width,height", [
    (1366, 768), (1440, 900), (1920, 1080), (1000, 720),
    (1093, 614), (910, 512), (800, 600),
    # Narrow viewport regression only; actual Edge zoom requires separate evidence.
])
def test_doctor_workspace_layout_and_real_record_entry(width: int, height: int) -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            _login(page, server.base_url)
            if not page.locator("#localSyntheticPatient").is_visible():
                page.locator("#localRegistrationDisclosure summary").click()
            page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
            page.click("#createLocalEncounterButton")
            page.locator('#dashboardEncounterList [data-encounter-action="start"]').click()
            if width < 900:
                page.locator("#showTranscriptButton").click()
            page.get_by_role("button", name="开始录音", exact=True).wait_for()
            assert page.get_by_role("button", name="开始录音", exact=True).count() == 1
            assert page.get_by_text("张示例", exact=True).count() >= 1
            assert page.locator("#patientProfile").inner_text().startswith("患者标识 SIM-DEMO-0929-FEVER · 本次就诊 E-")
            assert "active" in (page.locator("#workflowSteps .workflow-step").nth(1).get_attribute("class") or "")
            assert not page.locator(".encounter-action-bar").is_visible()
            if width < 900:
                page.locator("#closeWorkspaceAuxButton").click()
            layout = page.evaluate(
                """() => {
                  const box = (selector) => {
                    const rect = document.querySelector(selector).getBoundingClientRect();
                    return {left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom};
                  };
                  return {
                    viewport: innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    patient: box('.encounter-patient-banner'),
                    steps: box('.encounter-command-center'),
                    transcript: box('.transcript-column'),
                    record: box('.field-column'),
                    reference: box('.assist-column'),
                    recordFont: getComputedStyle(document.querySelector('.field-column .field-list')).fontSize,
                    transcriptFont: getComputedStyle(document.querySelector('.transcript-row-text') || document.querySelector('.transcript-list')).fontSize
                  };
                }"""
            )
            assert layout["documentWidth"] <= width + 1, layout
            assert layout["patient"]["bottom"] + 4 <= layout["steps"]["top"], layout
            assert layout["steps"]["bottom"] + 4 <= layout["record"]["top"], layout
            if width >= 900:
                assert layout["transcript"]["right"] - layout["transcript"]["left"] > 170, layout
                assert layout["record"]["right"] - layout["record"]["left"] > 400, layout
                assert layout["reference"]["right"] - layout["reference"]["left"] > 160, layout
                assert layout["transcript"]["right"] + 6 <= layout["record"]["left"], layout
                assert layout["record"]["right"] + 6 <= layout["reference"]["left"], layout
            screenshot_dir = os.environ.get("ALPHA51_SCREENSHOT_DIR")
            if screenshot_dir:
                target = Path(screenshot_dir)
                target.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(target / f"doctor-empty-{width}.png"), full_page=True)
            browser.close()
    finally:
        server.close()


def test_doctor_workspace_draft_keeps_edit_evidence_and_review_visible() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            assert page.locator(".encounter-action-bar").is_visible()
            assert page.locator("#recordFields .field-card").count() >= 7
            assert page.locator("#editRecordButton").is_visible()
            assert page.locator("#exportButton").is_disabled()
            assert page.evaluate(
                "parseFloat(getComputedStyle(document.querySelector('#recordFields .field-value')).fontSize)"
            ) >= 17
            screenshot_dir = os.environ.get("ALPHA51_SCREENSHOT_DIR")
            if screenshot_dir:
                target = Path(screenshot_dir)
                target.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(target / "doctor-draft-1440.png"), full_page=True)
            browser.close()
    finally:
        server.close()
