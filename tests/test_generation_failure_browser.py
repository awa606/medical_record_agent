import json
from playwright.sync_api import expect, sync_playwright

from app.db import bind_task_to_encounter, create_task, update_task
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login
from tests.test_doctor_workflow_state_contract_playwright import _server_database


def test_failed_generation_preserves_input_and_exposes_explicit_recovery():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            _login(page, server.base_url)
            if not page.locator("#localSyntheticPatient").is_visible():
                page.locator("#localRegistrationDisclosure summary").click()
            page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
            page.click("#createLocalEncounterButton")
            page.locator('#dashboardEncounterList [data-encounter-action="start"]').click()
            page.wait_for_function("window.__MRA_APP_STATE__.currentEncounter?.id")
            encounter, owner = page.evaluate("[window.__MRA_APP_STATE__.currentEncounter.id,window.__MRA_APP_STATE__.authUser.id]")
            source = "患者：发热两天，没有药物过敏。"
            with _server_database(server):
                task = create_task(input_type="text", status="FAILED", current_stage="failed", input_text=source)
                bind_task_to_encounter(task, encounter, owner_user_id=owner)
                update_task(task, error_message="LLM_OUTPUT_CONTRADICTION: 模型输出矛盾，未采纳。",
                            result_json=json.dumps({"conversation_text": source, "fields": None}))
            page.reload()
            # Refresh now restores the selected encounter directly.
            expect(page.locator("#patientName")).to_have_text("张示例")
            expect(page.locator("#nextActionPanel")).to_contain_text("病历生成中断")
            expect(page.locator("#nextActionPanel")).to_contain_text("模型输出矛盾")
            expect(page.get_by_role("button", name="重新生成病历", exact=True)).to_be_enabled()
            page.get_by_role("button", name="修改输入", exact=True).click()
            expect(page.locator("#conversationInput")).to_have_value(source)
            browser.close()
    finally:
        server.close()
