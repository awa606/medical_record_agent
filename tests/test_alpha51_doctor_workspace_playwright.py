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


@pytest.mark.parametrize("width,height", [
    (1366, 768), (1440, 900), (1920, 1080), (1000, 720),
    (1093, 614),  # 1366x768 at approximately 125% browser zoom
    (910, 512),   # 1366x768 at approximately 150% browser zoom
])
def test_doctor_workspace_layout_and_real_record_entry(width: int, height: int) -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            _login(page, server.base_url)
            page.evaluate(
                """() => {
                  window.__MRA_APP_STATE__.currentEncounter = {
                    id: 'sim-alpha51',
                    patient_display_name: '模拟患者',
                    patient_deidentified_id: 'SIM-001',
                    check_in_status: 'checked_in'
                  };
                  setProductView('encounter');
                  renderAll();
                }"""
            )
            page.get_by_role("button", name="开始录音", exact=True).wait_for()
            assert page.get_by_role("button", name="开始录音", exact=True).count() == 1
            assert page.get_by_text("模拟患者", exact=True).count() >= 1
            assert page.locator("#patientProfile").inner_text().startswith("本次就诊：")
            assert "active" in (page.locator("#workflowSteps .workflow-step").nth(1).get_attribute("class") or "")
            assert not page.locator(".encounter-action-bar").is_visible()
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
            if width >= 1220:
                assert layout["transcript"]["right"] + 10 <= layout["record"]["left"], layout
                assert layout["record"]["right"] + 10 <= layout["reference"]["left"], layout
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
