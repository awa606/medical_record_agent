from __future__ import annotations

import json
import tempfile
from pathlib import Path
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright

from tests.auth_helpers import DEFAULT_ADMIN_PASSWORD
from tests.test_doctor_itemized_approval_playwright import RunningServer


DOCTOR_TEST_PASSWORD = "a1234567"


def _create_user(api, *, username: str, password: str, display_name: str, role: str = "doctor") -> None:
    response = api.post(
        "/api/auth/users",
        data=json.dumps(
            {
                "username": username,
                "password": password,
                "display_name": display_name,
                "role": role,
                "is_active": True,
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    assert response.status in {200, 201}, response.text()


def _login_user(page, base_url: str, *, username: str, password: str, display_name: str) -> None:
    page.goto(f"{base_url}/static/doctor.html", wait_until="networkidle")
    if page.locator("#authUserLabel").is_visible() and display_name in page.locator("#authUserLabel").inner_text():
        return
    page.fill("#loginUsername", username)
    page.fill("#loginPassword", password)
    page.click("#loginForm button[type='submit']")
    expect(page.locator("#authUserLabel")).to_contain_text(display_name)


def test_doctor_a_local_encounter_flow_is_hidden_from_doctor_b() -> None:
    server = RunningServer()
    download_dir = Path(tempfile.mkdtemp(prefix="mra-local-encounter-downloads-"))
    try:
        with sync_playwright() as playwright:
            admin_api = playwright.request.new_context(base_url=server.base_url)
            login_response = admin_api.post(
                "/api/auth/login",
                data=json.dumps({"username": "admin", "password": DEFAULT_ADMIN_PASSWORD}),
                headers={"Content-Type": "application/json"},
            )
            assert login_response.status == 200
            _create_user(admin_api, username="doctor-a", password=DOCTOR_TEST_PASSWORD, display_name="Doctor A")
            _create_user(admin_api, username="doctor-b", password=DOCTOR_TEST_PASSWORD, display_name="Doctor B")
            admin_api.dispose()

            browser = playwright.chromium.launch(headless=True)
            context_a = browser.new_context(accept_downloads=True)
            page_a = context_a.new_page()
            _login_user(
                page_a,
                server.base_url,
                username="doctor-a",
                password=DOCTOR_TEST_PASSWORD,
                display_name="Doctor A",
            )

            page_a.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
            page_a.click("#createLocalEncounterButton")
            row = page_a.locator("#dashboardEncounterList article").filter(has_text="张示例")
            expect(row).to_contain_text("已报到")
            expect(page_a.locator("body")).to_have_attribute("data-product-view", "workbench")
            start = row.get_by_role("button", name="开始接诊", exact=True)
            encounter_id = int(start.get_attribute("data-encounter-id"))
            start.click()
            expect(page_a.locator("#patientName")).to_have_text("张示例")
            expect(page_a.locator("#patientDemoBadge")).to_be_visible()
            page_a.locator('#encounterView [data-input-method="text"]').click()
            page_a.fill("#conversationInput", "患者发热39度，伴咳嗽两天，胸闷气促，青霉素过敏。")
            page_a.click("#submitTextButton")
            expect(page_a.locator("#editRecordButton")).to_be_enabled(timeout=30000)
            task_id = int(page_a.evaluate("window.__MRA_APP_STATE__.currentTaskId"))
            page_a.click("#editRecordButton")
            editor = page_a.locator('[data-record-field-input="chief_complaint"]')
            editor.fill("发热伴咳嗽2天")
            page_a.locator('[data-product-view-target="workbench"]').first.click()
            expect(editor).to_have_value("发热伴咳嗽2天")
            expect(page_a.locator("body")).to_have_attribute("data-product-view", "encounter")
            page_a.click("#saveDraftButton")
            expect(page_a.locator("#confirmFieldsButton")).to_be_enabled(timeout=15000)

            linkage = page_a.evaluate(
                """async ({encounterId, taskId}) => {
                  const encounter = await fetch(`/api/encounters/${encounterId}`).then((response) => response.json());
                  const task = await fetch(`/api/tasks/${taskId}`).then((response) => response.json());
                  return {
                    encounterTaskId: encounter.task_id,
                    taskEncounterId: task.encounter_id,
                    checkInStatus: encounter.check_in_status,
                  };
                }""",
                {"encounterId": encounter_id, "taskId": task_id},
            )
            assert linkage["encounterTaskId"] == task_id
            assert linkage["taskEncounterId"] == encounter_id
            assert linkage["checkInStatus"] == "in_progress"

            page_a.locator("[data-approval-confirm-regular]").click()
            for selector in ('[data-approval-action="accept_missing"]', '[data-approval-action="confirm_candidate"]', '[data-approval-risk-key]'):
                # Capture stable keys, then use real visible clicks despite re-rendering.
                buttons = page_a.locator(selector + ":visible")
                for _ in range(buttons.count()):
                    buttons.first.click()
                assert buttons.count() == 0
            page_a.click("#confirmFieldsButton")
            page_a.wait_for_function("window.__MRA_APP_STATE__?.currentTask?.current_stage === 'approved'", timeout=15000)

            with page_a.expect_download(timeout=30000) as download_info:
                page_a.click("#exportButton")
            download = download_info.value
            docx_path = download_dir / download.suggested_filename
            download.save_as(docx_path)
            assert docx_path.exists()
            assert docx_path.stat().st_size > 0
            with ZipFile(docx_path) as docx:
                assert "word/document.xml" in docx.namelist()

            context_b = browser.new_context()
            page_b = context_b.new_page()
            _login_user(
                page_b,
                server.base_url,
                username="doctor-b",
                password=DOCTOR_TEST_PASSWORD,
                display_name="Doctor B",
            )
            expect(page_b.locator("#dashboardEncounterList")).not_to_contain_text("张示例")
            blocked = page_b.evaluate(
                """async ({encounterId, taskId}) => {
                  const requests = [
                    fetch(`/api/encounters/${encounterId}`),
                    fetch(`/api/tasks/${taskId}`),
                    fetch(`/api/tasks/${taskId}/steps`),
                    fetch(`/api/tasks/${taskId}/trace`),
                    fetch(`/api/tasks/${taskId}/events`),
                    fetch(`/api/tasks/${taskId}/export-readiness`),
                    fetch(`/api/tasks/${taskId}/export`, { method: 'POST' }),
                    fetch(`/api/tasks/${taskId}/exports/docx`),
                  ];
                  return Promise.all(requests).then((responses) => responses.map((response) => response.status));
                }""",
                {"encounterId": encounter_id, "taskId": task_id},
            )
            assert blocked == [403, 403, 403, 403, 403, 403, 403, 403]
            page_b.goto(f"{server.base_url}/api/tasks/{task_id}")
            expect(page_b.locator("body")).not_to_contain_text("青霉素过敏")

            page_a.reload(wait_until="networkidle")
            _login_user(
                page_a,
                server.base_url,
                username="doctor-a",
                password=DOCTOR_TEST_PASSWORD,
                display_name="Doctor A",
            )
            page_a.locator('[data-product-view-target="workbench"]').first.click()
            page_a.locator(f'#dashboardEncounterList [data-restore-encounter="{encounter_id}"]').click()
            page_a.wait_for_function(
                "(id) => window.__MRA_APP_STATE__?.currentEncounter?.id === id && window.__MRA_APP_STATE__?.currentTaskId",
                arg=encounter_id,
                timeout=15000,
            )
            restored = page_a.evaluate(
                """() => ({
                  encounterId: window.__MRA_APP_STATE__.currentEncounter.id,
                  taskId: window.__MRA_APP_STATE__.currentTaskId,
                  status: window.__MRA_APP_STATE__.currentEncounter.check_in_status,
                })"""
            )
            assert restored == {"encounterId": encounter_id, "taskId": task_id, "status": "in_progress"}

            browser.close()
    finally:
        server.close()
