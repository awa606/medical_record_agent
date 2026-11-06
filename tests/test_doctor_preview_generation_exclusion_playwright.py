from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect, sync_playwright

from tests.test_doctor_itemized_approval_playwright import RunningServer, _login
from tests.test_doctor_role_review_recovery_playwright import _inject_role_result


@pytest.fixture
def preview_page():
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)
            _inject_role_result(page, status="passed")
            calls = {"preview": 0, "generate": 0}

            def preview(route):
                calls["preview"] += 1
                route.fulfill(status=503, json={"detail": "isolated preview fixture"})

            page.route("**/api/records/preview", preview)
            yield page, calls
            browser.close()
    finally:
        server.close()


def test_visible_role_save_starts_one_formal_task_without_paid_preview(preview_page):
    page, calls = preview_page
    asr_result = page.evaluate("window.__MRA_APP_STATE__.currentAsrResult")
    page.route(
        "**/api/asr/sessions/role-session/result",
        lambda route: route.fulfill(json={"audio_id": "role-audio", "asr_result": asr_result}),
    )
    failed_task = {
        "id": 2301, "status": "FAILED", "current_stage": "FIELD_EXTRACTION",
        "input_text": "患者：发热。", "result_json": {},
    }

    def generate(route):
        calls["generate"] += 1
        route.fulfill(json={"task_id": 2301, "status": "CREATED", "events_url": "/api/tasks/2301/events"})

    page.route("**/api/audio/role-audio/generate-record*", generate)
    page.route(
        "**/api/tasks/2301/events",
        lambda route: route.fulfill(
            content_type="text/event-stream",
            body="event: FAILED\ndata: " + json.dumps({"task_id": 2301, "status": "FAILED", "task": failed_task}) + "\n\n",
        ),
    )
    page.evaluate("window.__MRA_APP_STATE__.pendingGenerateAfterRoleReview = true; openRoleReview()")
    expect(page.locator("[data-save-role-review]")).to_be_visible()
    page.locator("[data-save-role-review]").click()
    page.wait_for_function("window.__MRA_APP_STATE__.currentTaskId === 2301 && !window.__MRA_APP_STATE__.eventSource")
    assert calls == {"preview": 0, "generate": 1}
    # A late ASR result or a queued callback must not become a second inference.
    page.evaluate("scheduleRecordPreview({ force: true }); fetchRecordPreview('患者：发热。', [])")
    page.wait_for_timeout(2200)
    assert calls == {"preview": 0, "generate": 1}


def test_queued_preview_and_create_failure_do_not_implicitly_retry(preview_page):
    page, calls = preview_page

    def generate(route):
        calls["generate"] += 1
        route.fulfill(status=503, json={"detail": "isolated formal generation failure"})

    page.route("**/api/audio/role-audio/generate-record*", generate)
    page.evaluate(
        """async () => {
          scheduleRecordPreview({ force: true });
          await startRecordGenerationFromAudio('role-audio').catch(() => {});
          // No task ID was returned. An old timer still must not call the model.
          scheduleRecordPreview({ force: true });
          await fetchRecordPreview('患者：发热。', []);
        }"""
    )
    page.wait_for_timeout(2200)
    assert page.evaluate("window.__MRA_APP_STATE__.currentTaskId") is None
    assert calls == {"preview": 0, "generate": 1}

    # An explicit new input releases the exclusion; collection preview remains available.
    page.evaluate("resetTaskState({ keepAsr: true, keepEncounter: true })")
    _inject_role_result(page, status="passed")
    page.evaluate("fetchRecordPreview('患者：发热。', [])")
    assert calls == {"preview": 1, "generate": 1}


def test_existing_failed_task_does_not_request_preview_on_refresh(preview_page):
    page, calls = preview_page
    page.evaluate(
        """async () => {
          const state = window.__MRA_APP_STATE__;
          await refreshTask(2302, {
            id: 2302, status: 'FAILED', result_json: {}, input_text: '患者：发热。'
          }, { refreshEncounter: false });
          scheduleRecordPreview({ force: true });
          await fetchRecordPreview('患者：发热。', []);
        }"""
    )
    page.wait_for_timeout(500)
    assert calls == {"preview": 0, "generate": 0}
