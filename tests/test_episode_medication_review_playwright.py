"""A cited, but incomplete, present illness must stay readable and unsigned."""
import json
import sqlite3
from contextlib import closing

import pymupdf
from playwright.sync_api import expect, sync_playwright

from app.agents import MedicalRecordOrchestrator
from app.db import bind_task_to_encounter
from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.llm.llm_record_generator import LLMRecordGenerator
from scripts.demo_flow import DEFAULT_CONVERSATION
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login
from tests.test_doctor_workflow_state_contract_playwright import _server_database
from tests.test_generation_failure_contract import ResponseProvider


def test_readable_uncovered_medication_requires_saved_correction_to_sign(tmp_path):
    server = RunningServer()
    try:
        with sync_playwright() as browser_api:
            browser = browser_api.chromium.launch()
            page = browser.new_page(accept_downloads=True)
            _login(page, server.base_url)
            if not page.locator("#localSyntheticPatient").is_visible():
                page.locator("#localRegistrationDisclosure summary").click()
            page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
            page.click("#createLocalEncounterButton")
            page.locator('#dashboardEncounterList [data-encounter-action="start"]').click()
            page.wait_for_function("Boolean(appState.currentEncounter?.id)")
            encounter_id, owner = page.evaluate("[appState.currentEncounter.id, appState.authUser.id]")

            # Deterministic equivalent of the recorded E-1 omission. Seed via the
            # complete generator, never from a manually marked/injected gap.
            symptom = "发热、咳嗽、咽痛两天，最高体温38.2℃，没有胸痛，没有药物过敏史"
            medication = "昨天吃过一次布洛芬"
            raw = MedicalRecordFields(
                chief_complaint=MedicalField(value="发热、咳嗽、咽痛两天",
                    source_spans=[SourceSpan(text=symptom, index=1)]),
                present_illness=MedicalField(value=symptom, source_spans=[SourceSpan(text=symptom, index=1)]),
                previous_treatment=MedicalField(value=medication, source_spans=[SourceSpan(text=medication, index=3)]),
            )
            replay = ResponseProvider(raw.model_dump(mode="json"))
            generator = LLMRecordGenerator(provider=replay, mode="edge", allow_mock_fallback=False)
            generator.max_retries = 0
            with _server_database(server):
                orchestrator = MedicalRecordOrchestrator(generator)
                task_id = orchestrator.create_text_task(DEFAULT_CONVERSATION)
                bind_task_to_encounter(task_id, encounter_id, owner_user_id=owner)
                orchestrator.run_existing_text_task(task_id, DEFAULT_CONVERSATION)
            page.reload()
            card = page.locator('[data-field="present_illness"]')
            expect(card.locator(".field-value")).to_have_text(symptom)
            expect(card.locator(".field-status-text")).to_contain_text("漏记")
            expect(card.locator(".field-coverage-notice")).to_contain_text("原文第4段")
            expect(card.locator(".field-coverage-notice")).to_contain_text(medication)
            expect(card.locator(".field-value")).not_to_contain_text(medication)

            task_url = f"{server.base_url}/api/tasks/{task_id}"
            readiness = page.request.get(task_url + "/export-readiness").json()
            first_id = readiness["revision_id"]
            result = page.request.get(task_url).json()["result_json"]
            decisions = [
                {"key": key, "action": "accept_missing"}
                for key in ("accompanying_symptoms", "past_history", "physical_exam", "allergy_history")
            ] + [{"key": "present_illness", "action": "confirm_content"}]
            blocked = page.request.post(task_url + "/approve", data={
                "revision_id": first_id, "content_hash": readiness["content_hash"],
                "confirm_all_regular_fields": True, "fields": decisions,
                "diagnoses": [{"index": i, "action": "confirm_candidate", "high_risk_confirmed": True}
                              for i, _ in enumerate(result["fields"]["candidate_diagnoses"])],
            })
            assert blocked.status == 409, blocked.text()
            assert any("用药" in message for message in blocked.json()["detail"]["errors"])
            with closing(sqlite3.connect(server.root / "edge.sqlite3")) as db:
                assert db.execute("select count(*) from approval").fetchone() == (0,)
                assert db.execute("select count(*) from export_event").fetchone() == (0,)

            card.get_by_role("button", name="修改", exact=True).click()
            card.get_by_role("textbox").fill(symptom + "；" + medication)
            page.click("#saveDraftButton")
            expect(card.locator(".field-coverage-notice")).to_have_count(0)
            expect(card.locator(".field-value")).to_contain_text(medication)
            panel = page.locator(".approval-disclosure")
            if panel.get_attribute("open") is None:
                panel.locator("summary").click()
            panel.locator("[data-approval-confirm-regular]").click()
            for selector in ('[data-approval-action="accept_missing"]', '[data-approval-action="confirm_candidate"]',
                             "[data-approval-risk-key]"):
                pending = panel.locator(selector + ":visible")
                for _ in range(pending.count()):
                    pending.first.click()
            page.click("#confirmFieldsButton")
            expect(page.locator("#exportButton")).to_be_enabled()
            with page.expect_download() as download:
                page.click("#exportButton")
            pdf_path = tmp_path / "signed.pdf"
            download.value.save_as(pdf_path)
            with pymupdf.open(pdf_path) as pdf:
                assert medication in "".join(p.get_text() for p in pdf)
            with closing(sqlite3.connect(server.root / "edge.sqlite3")) as db:
                revs = db.execute("select id,result_json from record_revision order by id").fetchall()
                assert len(revs) == 2
                assert medication not in json.loads(revs[0][1])["fields"]["present_illness"]["value"]
                assert db.execute("select revision_id from export_event").fetchall() == [(revs[1][0],)]
            assert replay.calls == 1
            browser.close()
    finally:
        server.close()
