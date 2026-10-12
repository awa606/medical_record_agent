"""Visible-button regression; recorded failures and test server, no real ASR/LLM."""
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from app.agents import MedicalRecordOrchestrator
from app.db import bind_task_to_encounter
from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.llm.llm_record_generator import LLMRecordGenerator
from tests.test_generation_failure_contract import ResponseProvider
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login
from tests.test_doctor_workflow_state_contract_playwright import _server_database


def seed_partial(page, server):
    page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
    page.click("#createLocalEncounterButton")
    page.locator('#dashboardEncounterList [data-encounter-action="start"]').click()
    page.wait_for_function("window.__MRA_APP_STATE__.currentEncounter?.id")
    encounter, owner = page.evaluate("[window.__MRA_APP_STATE__.currentEncounter.id,window.__MRA_APP_STATE__.authUser.id]")
    source = "患者：发热两天。患者：没有药物过敏。"
    fields = MedicalRecordFields(
        chief_complaint=MedicalField(value="发热两天", source_spans=[SourceSpan(text="发热两天", index=0)]),
        allergy_history=MedicalField(value="错误模型过敏内容", source_spans=[SourceSpan(text="损坏引文", index=9)]),
    )
    generator = LLMRecordGenerator(provider=ResponseProvider(fields.model_dump(mode="json")), allow_mock_fallback=False)
    generator.max_retries = 0
    with _server_database(server):
        orchestrator = MedicalRecordOrchestrator(generator)
        task_id = orchestrator.create_text_task(source)
        bind_task_to_encounter(task_id, encounter, owner_user_id=owner)
        result = orchestrator.run_existing_text_task(task_id, source)
        assert result["status"] == "WAITING_DOCTOR_REVIEW"
    page.reload()
    page.get_by_role("button", name="继续处理", exact=True).first.click()
    expect(page.locator("#recordFields")).to_contain_text("发热两天")
    return result["task_id"]


@pytest.mark.parametrize("method", ["doctor_entry", "source_correction"])
def test_partial_draft_visible_resolution_save_and_embedded_help(method):
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _login(page, server.base_url)
            task_id = seed_partial(page, server)
            expect(page.locator(".partial-draft-summary")).to_contain_text("1项证据冲突已隔离")
            field = page.locator('[data-field="allergy_history"]')
            expect(field).not_to_contain_text("错误模型过敏内容")
            expect(field).to_contain_text("待核对")
            field.get_by_role("button", name="查看原文证据").click()
            expect(page.locator("#detailDrawerContent")).to_contain_text("错误模型过敏内容")
            page.locator("#closeDrawerButton").click()
            field.locator(f'[data-field-resolution="{method}"]').click()
            editor = page.locator('[data-record-field-input="allergy_history"]')
            editor.fill("没有药物过敏")
            if method == "source_correction":
                page.locator('[data-record-source-field="allergy_history"]').select_option(index=2)
            page.click("#openEmbeddedHelpButton")
            expect(page.locator("#helpDialog")).to_be_visible()
            frame = page.frame_locator("#embeddedHelpFrame")
            frame.get_by_role("link", name="核对与修改病历").click()
            expect(frame.locator("#edit")).to_contain_text("医生补录")
            assert len(browser.contexts[0].pages) == 1
            frame.locator("body").press("Escape")
            expect(page.locator("#helpDialog")).not_to_be_visible()
            expect(page.locator("#openEmbeddedHelpButton")).to_be_focused()
            expect(editor).to_have_value("没有药物过敏")
            page.click("#saveDraftButton")
            page.wait_for_function("!window.__MRA_APP_STATE__.recordEditMode", timeout=15000)
            stored = page.request.get(server.base_url + f"/api/tasks/{task_id}").json()["result_json"]
            assert stored["fields"]["allergy_history"]["status"] != "conflicting"
            assert stored["llm_trace"]["field_resolution_history"][-1]["method"] == method
            assert not stored["approved"]
            page.locator('[data-field="allergy_history"]').get_by_role("button", name="查看原文证据").click()
            expect(page.locator("#detailDrawerContent")).to_contain_text("错误模型过敏内容")
            page.locator("#closeDrawerButton").click()
            out = Path(".artifacts/partial-draft-20261012")
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / f"review-{method}.png"))
            browser.close()
    finally:
        server.close()


def test_help_before_login_and_return_to_workspace():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(server.base_url + "/static/doctor.html#help")
            expect(page.locator("#helpDialog")).to_be_visible()
            page.frame_locator("#embeddedHelpFrame").get_by_role("link", name="返回工作台").click()
            expect(page.locator("#helpDialog")).not_to_be_visible()
            expect(page.locator("#loginPanel")).to_be_visible()
            page.click("#loginHelpButton")
            expect(page.locator("#helpDialog")).to_be_visible()
            page.locator("#closeEmbeddedHelpButton").click()
            expect(page.locator("#loginHelpButton")).to_be_focused()
            browser.close()
    finally:
        server.close()


def test_closed_knowledge_search_does_not_reopen_over_edit_and_help():
    """A late response must respect the doctor's closed panel, without retries."""
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _login(page, server.base_url)
            seed_partial(page, server)
            page.route("**/api/knowledge/retrieve", lambda route: route.fulfill(
                status=200, content_type="application/json", body='{"results": []}'))
            # Hold the response at the page boundary to reproduce delayed retrieval.
            page.evaluate("""() => {
              const original = window.fetch;
              window.fetch = async (...args) => {
                const response = await original(...args);
                if (String(args[0]).includes('/api/knowledge/retrieve')) {
                  await new Promise(resolve => { window.releaseKnowledgeResponse = resolve; });
                }
                return response;
              };
            }""")
            page.locator('[data-field="chief_complaint"] [data-knowledge-field]').click()
            page.wait_for_function("Boolean(window.releaseKnowledgeResponse)")
            page.click("#closeDrawerButton")
            page.locator('[data-field="allergy_history"] [data-field-resolution="doctor_entry"]').click()
            editor = page.locator('[data-record-field-input="allergy_history"]')
            editor.fill("没有药物过敏")
            page.click("#openEmbeddedHelpButton")
            page.evaluate("window.releaseKnowledgeResponse()")
            page.wait_for_function("window.__MRA_APP_STATE__.fieldKnowledgeSearch.chief_complaint.status === 'ready'")
            expect(page.locator("#drawer")).to_have_attribute("aria-hidden", "true")
            expect(page.locator("#helpDialog")).to_be_visible()
            page.click("#closeEmbeddedHelpButton")
            expect(editor).to_have_value("没有药物过敏")
            browser.close()
    finally:
        server.close()
