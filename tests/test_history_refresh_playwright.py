"""Visible history clicks against isolated API/SQLite; model is explicitly Mock."""
from playwright.sync_api import expect, sync_playwright
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


def test_saved_text_reloads_same_task_without_new_generation():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)
            page.click('#createLocalEncounterButton')
            row = page.locator('#dashboardEncounterList article').filter(has_text='张示例')
            row.get_by_role('button', name='开始接诊', exact=True).click()
            page.get_by_role('button', name='文本输入', exact=True).first.click()
            page.locator('#conversationInput').fill('[患者] 发热伴咳嗽两天，没有药物过敏史。')
            page.locator('#submitTextButton').click()
            expect(page.locator('#recordFields')).to_contain_text('主诉', timeout=30000)
            page.wait_for_function('window.__MRA_APP_STATE__.currentTaskId && !window.__MRA_APP_STATE__.busy')
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
