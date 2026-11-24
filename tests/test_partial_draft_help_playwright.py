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


def seed_partial(page, server, source="患者：发热两天。患者：没有药物过敏。"):
    if not page.locator("#localSyntheticPatient").is_visible():
        page.locator("#localRegistrationDisclosure summary").click()
    page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
    page.click("#createLocalEncounterButton")
    page.locator('#dashboardEncounterList [data-encounter-action="start"]').click()
    page.wait_for_function("window.__MRA_APP_STATE__.currentEncounter?.id")
    encounter, owner = page.evaluate("[window.__MRA_APP_STATE__.currentEncounter.id,window.__MRA_APP_STATE__.authUser.id]")
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
    expect(page.locator("#patientName")).to_have_text("张示例")
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
            field.locator('[data-open-detail="field:allergy_history"]').click()
            expect(page.locator("#detailDrawerContent")).to_contain_text("错误模型过敏内容")
            page.locator("#closeDrawerButton").click()
            field.locator(f'[data-field-resolution="{method}"]').click()
            editor = page.locator('[data-record-field-input="allergy_history"]')
            editor.fill("没有药物过敏")
            if method == "source_correction":
                choice = field.get_by_role("checkbox", name="第 2 句 · 患者")
                choice.check()
                expect(field.get_by_role("button", name="查看已选原话", exact=True)).to_be_visible()
                choice.uncheck()
                expect(field.get_by_role("button", name="查看字段记录", exact=True)).to_be_visible()
                choice.check()
            page.click("#openEmbeddedHelpButton")
            expect(page.locator("#helpDialog")).to_be_visible()
            frame = page.frame_locator("#embeddedHelpFrame")
            frame.get_by_role("link", name="核对与修改病历").click()
            expect(frame.locator("#edit")).to_contain_text("医生补录")
            assert len(browser.contexts[0].pages) == 1
            session_checks = []
            page.on("request", lambda request: session_checks.append(request.url)
                    if request.url.endswith("/api/auth/me") else None)
            frame.locator("body").press("Escape")
            expect(page.locator("#helpDialog")).not_to_be_visible()
            expect(page.locator("#openEmbeddedHelpButton")).to_be_focused()
            assert not session_checks
            expect(editor).to_have_value("没有药物过敏")
            page.click("#saveDraftButton")
            page.wait_for_function("!window.__MRA_APP_STATE__.recordEditMode", timeout=15000)
            stored = page.request.get(server.base_url + f"/api/tasks/{task_id}").json()["result_json"]
            assert stored["fields"]["allergy_history"]["status"] != "conflicting"
            assert stored["llm_trace"]["field_resolution_history"][-1]["method"] == method
            assert not stored["approved"]
            action = "查看字段记录" if method == "doctor_entry" else "查看问诊原文"
            field.get_by_role("button", name=action, exact=True).click()
            expect(page.locator("#detailDrawerContent")).to_contain_text("错误模型过敏内容")
            if method == "doctor_entry":
                expect(page.locator("#detailDrawerContent")).to_contain_text("此字段没有保存原文引用")
            page.locator("#closeDrawerButton").click()
            out = Path(".artifacts/partial-draft-20261012")
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / f"review-{method}.png"))
            browser.close()
    finally:
        server.close()


@pytest.mark.parametrize("width", [1366, 390])
def test_multispan_editor_keeps_only_explicit_choices_after_failed_save(width):
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": 844})
            _login(page, server.base_url)
            source = "患者：发热两天。医生：请继续。患者：昨天吃过一次布洛芬，" + "那天出门前又核对了记录，" * 8 + "之后把时间写下。"
            task = seed_partial(page, server, source)
            card = page.locator('article[data-field="chief_complaint"]')
            card.get_by_role("button", name="修改", exact=True).click()
            resolve = card.get_by_role("button", name="根据原文修正")
            resolve.press("Enter")
            group = card.get_by_role("group", name="本次核对的原话")
            expect(group).to_contain_text("已选 0 条")
            old = card.locator("summary", has_text="上版引用（只读对照）")
            old.press("Enter")
            expect(card.locator(".previous-source-quotes")).to_contain_text("发热两天")
            old.press("Enter")
            card.locator("textarea").fill("发热两天，昨天吃过一次布洛芬。")
            first = group.get_by_role("checkbox", name="第 1 句 · 患者")
            last = group.get_by_role("checkbox", name="第 3 句 · 患者")
            region = group.get_by_role("region", name="候选原话全文")
            region.focus()
            page.keyboard.press("Tab")
            expect(first).to_be_focused()
            page.keyboard.press("Space")
            page.keyboard.press("Tab")
            page.keyboard.press("Tab")
            expect(last).to_be_focused()
            page.keyboard.press("Space")
            expect(group).to_contain_text("已选 2 条")
            page.keyboard.press("Shift+Tab")
            page.keyboard.press("Shift+Tab")
            page.keyboard.press("Space")
            expect(first).not_to_be_checked()
            expect(last).to_be_checked()
            page.keyboard.press("Space")
            assert region.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            payloads = []

            def reject(route):
                payloads.append(route.request.post_data_json)
                route.fulfill(status=422, json={"detail": {"message": "请重新核对本次原话。"}})

            page.route(f"**/api/tasks/{task}/review", reject)
            with page.expect_response(lambda response: response.url.endswith("/review")):
                page.locator("#saveDraftButton").click()
            expect(first).to_be_checked()
            expect(last).to_be_checked()
            assert len(payloads) == 1
            body = payloads[0]
            assert body["source_corrected_fields"] == ["chief_complaint"] and body["manual_takeover_fields"] == []
            assert [(s["index"], s["text"]) for s in body["fields"]["chief_complaint"]["source_spans"]] == [
                (0, source.split("。")[0]), (2, source.split("。")[2])]
            assert body["expected_revision_id"] and body["expected_content_hash"]
            resolve.press("Enter")
            expect(group).to_contain_text("已选 2 条")
            card.get_by_role("button", name="医生补录").click()
            expect(group).to_have_count(0)
            resolve.click()
            expect(group).to_contain_text("已选 0 条")
            page.locator("#cancelRecordEditButton").click()
            card.get_by_role("button", name="修改", exact=True).click()
            expect(card.locator("textarea")).to_have_value("发热两天")
            resolve.click()
            expect(group).to_contain_text("已选 0 条")
            browser.close()
    finally:
        server.close()


def test_source_choices_preserve_original_sentence_and_legacy_audio_identity():
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(server.base_url + "/static/doctor.html")

            def choices(kind, text, asr):
                return page.evaluate("""([kind,text,asr]) => {
                  appState.currentTask = {input_type:kind,input_text:text,result_json:{asr_source:asr}};
                  appState.currentAsrResult = asr;
                  return sourceCorrectionOptions();
                }""", [kind, text, asr])

            text = '患者：两天；今晨38.2℃。医生：接下来呢？'
            imported = {"engine": "text-import", "segments": [{"text": text, "segment_id": "placeholder", "start": 0}]}
            assert [entry["span"] for entry in choices("text", text, imported)] == [
                {"text": "患者：两天；今晨38.2℃", "index": 0}, {"text": "医生：接下来呢", "index": 1}]
            segments = [{"text": "第一句。第二句。", "segment_id": "original-1", "start": 0, "end": 2.1},
                        {"text": "相同原话。"}, {"text": "相同原话。"}]
            recorded = choices("audio", "", {"segments": segments, "conversation_text": "第一句。第二句。相同原话。相同原话。"})
            assert [(row["span"]["segment_id"], row["span"]["index"]) for row in recorded] == [
                ("original-1", None), (None, 2), (None, 3)]
            assert recorded[0]["span"]["start_time"] == 0 and recorded[0]["span"]["end_time"] == 2.1
            assert all(row["span"]["start_time"] is None and row["span"]["end_time"] is None for row in recorded[1:])
            ambiguous = choices("audio", "", {"segments": segments, "conversation_text": "句序没有可靠对齐。"})
            assert [row["ambiguous"] for row in ambiguous] == [False, True, True]
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
            requests = []
            page.on("request", lambda req: requests.append(req.url)
                    if req.url.endswith("/api/knowledge/retrieve") else None)
            page.route("**/api/knowledge/retrieve", lambda route: route.fulfill(
                json={"results": [{"title": "已关闭抽屉的旧结果"}]}))
            # Wait for the actual UI action, including its choice to discard a closed drawer's response.
            page.evaluate("""() => {
              const lookup = window.retrieveKnowledgeForField;
              window.retrieveKnowledgeForField = (...args) => (window.pendingFieldLookup = lookup(...args));
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
            page.wait_for_function("Boolean(window.releaseKnowledgeResponse) && window.pendingFieldLookup instanceof Promise")
            page.click("#closeDrawerButton")
            page.locator('[data-field="allergy_history"] [data-field-resolution="doctor_entry"]').click()
            editor = page.locator('[data-record-field-input="allergy_history"]')
            editor.fill("没有药物过敏")
            page.click("#openEmbeddedHelpButton")
            page.evaluate("async () => { window.releaseKnowledgeResponse(); await window.pendingFieldLookup; }")
            assert len(requests) == 1
            assert page.evaluate("appState.fieldKnowledgeSearch.chief_complaint.results") == []
            expect(page.locator("#drawer")).to_have_attribute("aria-hidden", "true")
            expect(page.locator("#helpDialog")).to_be_visible()
            page.click("#closeEmbeddedHelpButton")
            expect(editor).to_have_value("没有药物过敏")
            browser.close()
    finally:
        server.close()
