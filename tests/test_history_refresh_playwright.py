"""Visible history clicks against isolated API/SQLite; model is explicitly Mock."""
from secrets import token_urlsafe

from playwright.sync_api import expect, sync_playwright
from app.db import create_encounter, create_user
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login
from tests.test_doctor_workflow_state_contract_playwright import _server_database


def test_saved_text_reloads_same_task_without_new_generation():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)
            if not page.locator("#localSyntheticPatient").is_visible():
                page.locator("#localRegistrationDisclosure summary").click()
            page.click('#createLocalEncounterButton')
            row = page.locator('#dashboardEncounterList article').filter(has_text='张示例')
            row.get_by_role('button', name='开始接诊', exact=True).click()
            page.get_by_role('button', name='文本输入', exact=True).first.click()
            page.locator('#conversationInput').fill('[患者] 发热伴咳嗽两天，没有药物过敏史。')
            page.locator('#submitTextButton').click()
            expect(page.locator('#recordFields')).to_contain_text('主诉', timeout=30000)
            page.wait_for_function('window.__MRA_APP_STATE__.currentTaskId && !window.__MRA_APP_STATE__.busy')
            expect(page.locator('.record-version').first).to_contain_text('#1')
            before = page.evaluate('({task:window.__MRA_APP_STATE__.currentTaskId,revision:window.__MRA_APP_STATE__.currentTask.current_record_revision_id})')
            assert 'encounter_id=' in page.url
            requests = []
            page.on('request', lambda r: requests.append((r.method, r.url)))
            page.reload()
            expect(page.locator('#patientName')).to_have_text('张示例')
            expect(page.locator('#transcriptList')).to_contain_text('没有药物过敏史', timeout=20000)
            expect(page.locator('#recordFields')).to_contain_text('主诉')
            page.wait_for_function('!window.__MRA_APP_STATE__.busy')
            after = page.evaluate('({task:window.__MRA_APP_STATE__.currentTaskId,revision:window.__MRA_APP_STATE__.currentTask.current_record_revision_id})')
            assert after == before
            assert not [(m, u) for m, u in requests if m != 'GET']
            page.locator('[data-product-view-target="workbench"]').first.click()
            row.get_by_role('button', name='返回工作区', exact=True).click()
            expect(page.locator('#transcriptList')).to_contain_text('没有药物过敏史')
            browser.close()
    finally:
        server.close()


def test_doctor_login_resumes_only_a_visible_encounter_link():
    server = RunningServer()
    password = token_urlsafe(20)
    try:
        with _server_database(server):
            encounters = []
            for username in ("link-owner", "link-other"):
                owner = create_user(username=username, password=password, role="doctor", display_name=username)
                visit = create_encounter(doctor_user_id=owner, deidentified_id="SIM-" + username,
                                         display_name="合成就诊", check_in_status="in_progress")
                encounters.append(visit["id"])
        with sync_playwright() as pw, pw.chromium.launch() as browser:
            for encounter_id in (encounters[0], encounters[1], 999999, None):
                with browser.new_context() as context:
                    page = context.new_page()
                    reads = []
                    page.on("request", lambda request: reads.append(request.url))
                    path = f"?encounter_id={encounter_id}#encounter" if encounter_id else ""
                    page.goto(server.base_url + "/static/doctor.html" + path)
                    expect(page.locator("#loginPanel")).to_be_visible()
                    page.fill("#loginUsername", "link-owner")
                    page.fill("#loginPassword", password)
                    page.click("#loginForm button[type=submit]")
                    expect(page.locator("#loginPanel")).to_be_hidden()
                    if encounter_id == encounters[0]:
                        expect(page.locator("#encounterView")).to_be_visible()
                        page.wait_for_function("window.__MRA_APP_STATE__.currentEncounter?.id === " + str(encounter_id))
                    else:
                        expect(page.locator("#workbenchHome")).to_be_visible()
                        if encounter_id:
                            expect(page.locator("#workbenchSelectionNotice")).to_contain_text("不在您的列表")
                            assert "encounter_id=" not in page.url
                            assert not any(url.endswith(f"/api/encounters/{encounter_id}") for url in reads)
                        assert page.evaluate("window.__MRA_APP_STATE__.currentEncounter") is None
    finally:
        server.close()
