"""Edit, sign and export an ICD code through visible controls in an isolated service."""
from pathlib import Path
import os
import time

import pymupdf
from playwright.sync_api import expect, sync_playwright

from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


def test_code_edit_requires_saved_revision_before_approval_and_pdf():
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(accept_downloads=True)
            _login(page, server.base_url)
            encounter_url = server.base_url + "/api/encounters"
            encounter = page.request.post(encounter_url, data={"patient_deidentified_id": "SIM-ICD-REVIEW"})
            assert encounter.ok, encounter.text()
            encounter_id = encounter.json()["id"]
            for action in ("check-in", "start"):
                changed = page.request.post(f"{encounter_url}/{encounter_id}/{action}")
                assert changed.ok, changed.text()
            generated = page.request.post(f"{server.base_url}/api/records/generate",
                                          data={"encounter_id": encounter_id, "conversation_text": "患者：我发热两天，伴咳嗽、咽痛。"})
            assert generated.ok, generated.text()
            task_id = generated.json()["task_id"]
            task_url = f"{server.base_url}/api/tasks/{task_id}"
            deadline = time.monotonic() + 20
            while True:
                original = page.request.get(task_url).json()
                if original.get("current_record_revision_id") or original.get("status") == "FAILED" or time.monotonic() >= deadline:
                    break
                time.sleep(0.1)
            assert original.get("result_json"), (original.get("status"), original.get("error_message"))
            assert original["result_json"]["fields"]["candidate_diagnoses"]
            page.goto(f"{server.base_url}/static/doctor.html?encounter_id={encounter_id}#encounter")
            page.locator(".approval-disclosure > summary").click()
            page.locator('[data-edit-diagnosis-code="0"]').click()
            code = page.locator('[data-diagnosis-code-index="0"]')
            code.fill("R50.9")
            expect(page.locator("#confirmFieldsButton")).to_be_disabled()
            expect(page.locator("#exportButton")).to_be_disabled()
            expect(page.locator("#saveDraftButton")).to_be_enabled()
            assert page.request.get(task_url).json()["current_record_revision_id"] == original["current_record_revision_id"]
            with page.expect_response(lambda r: r.url == task_url + "/review") as saved:
                page.locator("#saveDraftButton").click()
            assert saved.value.ok, saved.value.text()
            revised = saved.value.json()
            assert revised["current_record_revision_id"] != original["current_record_revision_id"]
            expect(page.locator('[data-field="preliminary_diagnosis"]')).to_contain_text("R50.9")
            disclosure = page.locator(".approval-disclosure")
            if disclosure.get_attribute("open") is None:
                disclosure.locator("summary").click()
            page.locator("[data-approval-confirm-regular]").click()
            for attr, value in [("data-approval-action","accept_missing"), ("data-approval-action","confirm_candidate")]:
                buttons = disclosure.locator(f'button[{attr}="{value}"]:visible')
                while buttons.count():
                    buttons.first.click()
            risks = disclosure.locator("button[data-approval-risk-key]:visible")
            while risks.count():
                risks.first.click()
            with page.expect_response(lambda r: r.url == task_url + "/approve") as signed:
                page.locator("#confirmFieldsButton").click()
            assert signed.value.ok, signed.value.text()
            assert signed.value.json()["result_json"]["fields"]["candidate_diagnoses"][0]["icd10_code"] == "R50.9"
            expect(page.locator("#exportButton")).to_be_enabled()
            with page.expect_download() as download:
                page.locator("#exportButton").click()
            with pymupdf.open(download.value.path()) as pdf:
                assert "R50.9" in "".join(p.get_text() for p in pdf)
            artifacts = os.environ.get("MRA_REVIEW_EVIDENCE_DIR")
            if artifacts:
                if page.locator("#closeDrawerButton").is_visible():
                    page.locator("#closeDrawerButton").click()
                page.locator('[data-record-anchor="management"]').click()
                page.screenshot(path=str(Path(artifacts) / "revised-icd-approved.png"))
            browser.close()
    finally:
        server.close()
