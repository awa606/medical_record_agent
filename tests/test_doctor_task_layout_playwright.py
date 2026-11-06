"""Actual page controls with explicit synthetic fixtures; no real model/ASR claim."""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from tests.auth_helpers import DEFAULT_ADMIN_PASSWORD
from tests.test_doctor_itemized_approval_playwright import RunningServer, _free_port, _login, _prepare_review_fixture, _wait_for_health


def test_workbench_and_workspace_have_one_empty_state_and_compact_filters():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width":1440,"height":900})
            _login(page, server.base_url)
            expect(page.locator("#localSyntheticPatient")).not_to_be_visible()
            expect(page.locator(".dashboard-status-filters button")).to_have_count(5)
            assert page.locator("#dashboardEncounterList").bounding_box()["y"] < 420
            page.locator("#localRegistrationDisclosure summary").focus()
            page.keyboard.press("Enter")
            page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
            page.click("#createLocalEncounterButton")
            row = page.locator("#dashboardEncounterList article")
            expect(row).to_have_count(1)
            page.locator('[data-dashboard-filter="exceptions"]').click()
            expect(row).to_have_count(0)
            expect(page.locator("#dashboardEncounterList")).to_contain_text("当前筛选下暂无就诊")
            page.locator('[data-dashboard-filter="pendingInput"]').click()
            expect(row).to_have_count(1)
            page.locator('[data-encounter-action="start"]').first.click()
            expect(page.locator("#recordFields .record-empty-state")).to_have_count(1)
            expect(page.locator("#recordFields .field-card")).to_have_count(0)
            expect(page.get_by_role("button",name="开始录音",exact=True)).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            browser.close()
    finally:
        server.close()


def test_historical_empty_display_and_strict_text_roles_do_not_mutate_history():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            rows = page.evaluate("text => transcriptRowsFromText(text)", "医生：患者以前有没有过敏？\n[患者] 没有药物过敏。\n家属：孩子咳嗽，我本人有高血压。\n这份材料提到医生和患者，但没有身份标记。\n旁白 [医生] 仅是引用")
            assert [row['label'] for row in rows] == ['医生','患者','家属','角色未记录','角色未记录']
            assert rows[-1]['text'] == '旁白 [医生] 仅是引用'
            original = page.evaluate("""() => {
                const s=window.__MRA_APP_STATE__;
                for (const [key] of EDITABLE_FIELD_DEFS) s.currentRecordFields[key] = {value:null,hint:'null',missing:true,status:'missing',source_spans:[]};
                s.currentRecordFields.candidate_diagnoses=[];
                s.currentTask.result_json.fields=s.currentRecordFields;
                s.taskStatus='done'; s.currentTask.current_stage='doctor_review';
                s.currentExportReadiness=null; s.approvalRegularFieldsConfirmed=false;
                const raw=JSON.stringify(s.currentRecordFields); renderAll(); return raw;
            }""")
            expect(page.locator('#reviewStatus')).to_have_text('内容不完整')
            expect(page.locator('#recordFields')).not_to_contain_text('null')
            expect(page.locator('#recordFields')).to_contain_text('原因未记录')
            expect(page.locator('#confirmFieldsButton')).to_be_disabled()
            assert page.evaluate('JSON.stringify(window.__MRA_APP_STATE__.currentRecordFields)') == original
            page.evaluate("""() => {
                const s=window.__MRA_APP_STATE__;
                s.taskStatus='exported';s.currentTask.current_stage='exported';
                s.currentExportReadiness={approved:true,can_export:true,revision_id:1,content_hash:'fixture'};
                renderAll();
            }""")
            expect(page.locator('#reviewStatus')).to_have_text('已导出')
            expect(page.locator('.historical-record-notice')).to_contain_text('历史审核记录保留')
            assert page.evaluate('JSON.stringify(window.__MRA_APP_STATE__.currentRecordFields)') == original
            browser.close()
    finally:
        server.close()


def test_review_starts_collapsed_and_batch_does_not_accept_exceptions():
    server=RunningServer()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={"width":1440,"height":900})
            _login(page,server.base_url)
            _prepare_review_fixture(page)
            disclosure=page.locator('.approval-disclosure')
            expect(disclosure).not_to_have_attribute('open','')
            expect(page.locator('[data-field="chief_complaint"]')).to_be_visible()
            before=page.evaluate('JSON.stringify(window.__MRA_APP_STATE__.currentRecordFields)')
            disclosure.locator(':scope > summary').click()
            expect(page.locator('.approval-confirm-scope')).to_contain_text('不处理缺失、候选诊断或证据冲突')
            page.locator('[data-approval-confirm-regular]').click()
            state=page.evaluate("""() => ({regular:appState.approvalRegularFieldsConfirmed, missing:appState.approvalMissingDecisions,
              diagnosis:appState.approvalDiagnosisDecisions, risk:appState.approvalHighRiskConfirmations,
              fields:JSON.stringify(appState.currentRecordFields),pending:pendingApprovalCount(appState.currentRecordFields)})""")
            assert state['regular'] and not state['missing'] and not state['diagnosis'] and not state['risk']
            assert state['fields']==before and state['pending']>0
            expect(disclosure).to_have_attribute('open','')
            page.locator('[data-review-focus="present_illness"]').click()
            expect(page.locator('[data-field="present_illness"]')).to_be_focused()
            browser.close()
    finally:
        server.close()


def test_valid_historical_value_with_null_hint_is_not_reported_as_empty():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            original = page.evaluate("""() => {
                const s = window.__MRA_APP_STATE__;
                for (const [key] of EDITABLE_FIELD_DEFS) s.currentRecordFields[key] = {
                    value:'已保存的字段内容', hint:null, missing:false, status:'present', source_spans:[]
                };
                s.currentRecordFields.chief_complaint.value = '发热两天';
                s.currentRecordFields.chief_complaint.hint = 'null';
                s.currentRecordFields.candidate_diagnoses = [];
                s.currentTask.result_json.fields = s.currentRecordFields;
                const raw = JSON.stringify(s.currentRecordFields); renderAll(); return raw;
            }""")
            expect(page.locator('[data-field="chief_complaint"] .field-value')).to_have_text('发热两天')
            expect(page.locator('.historical-record-notice')).to_have_count(0)
            expect(page.locator('#recordFields')).not_to_contain_text('原因未记录')
            assert page.evaluate('JSON.stringify(window.__MRA_APP_STATE__.currentRecordFields)') == original
            whitespace_raw = page.evaluate("""() => {
                appState.currentRecordFields.chief_complaint.value = ' \\n  ';
                appState.currentRecordFields.chief_complaint.hint = '   ';
                const raw=JSON.stringify(appState.currentRecordFields); renderAll(); return raw;
            }""")
            expect(page.locator('[data-field="chief_complaint"] .field-value')).to_have_text('历史字段无可用内容，原因未记录')
            assert page.evaluate('JSON.stringify(window.__MRA_APP_STATE__.currentRecordFields)') == whitespace_raw
            assert page.evaluate("readableStoredText('  发热两天  ')") == '  发热两天  '
            browser.close()
    finally:
        server.close()


def test_visual_review_fixture_clears_previous_task_for_empty_and_recording_scenes():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width":1440,"height":900})
            _login(page, server.base_url)
            page.locator('#localRegistrationDisclosure summary').click()
            page.select_option('#localSyntheticPatient', 'SIM-DEMO-0929-FEVER')
            page.click('#createLocalEncounterButton')
            page.locator('[data-encounter-action="start"]').first.click()
            expect(page.get_by_role('button', name='开始录音', exact=True)).to_be_visible()
            encounter_id = page.evaluate('selectedEncounterId()')
            _prepare_review_fixture(page)
            page.add_script_tag(path=str(Path(__file__).parent / 'fixtures' / 'alpha51_workspace_review.js'))
            page.locator('#workspaceReviewTools summary').click()
            page.select_option('#workspaceReviewScene', 'empty')
            expect(page.get_by_role('button', name='开始录音', exact=True)).to_be_visible()
            assert page.evaluate('selectedEncounterId()') == encounter_id
            assert page.evaluate('encounterReadyForInput() && !hasActiveSession()')
            page.locator('#workspaceReviewTools summary').click()
            page.select_option('#workspaceReviewScene', 'recording')
            expect(page.locator('#pauseBrowserRecordingButton')).to_be_visible()
            expect(page.locator('#stopBrowserRecordingButton')).to_be_visible()
            expect(page.locator('#cancelBrowserRecordingButton')).to_be_visible()
            expect(page.locator('#browserRecordingMessage')).to_contain_text('未使用麦克风')
            expect(page.locator('#transcriptList')).to_contain_text('正在录音，等待转写内容')
            page.locator('#pauseBrowserRecordingButton').click()
            expect(page.locator('#transcriptList')).to_contain_text('录音已暂停，暂无转写内容')
            expect(page.locator('#transcriptList')).not_to_contain_text('可开始录音')
            assert page.evaluate('selectedEncounterId()') == encounter_id
            page.locator('#workspaceReviewTools summary').click()
            page.select_option('#workspaceReviewScene', 'draft')
            expect(page.locator('[data-field="chief_complaint"] .field-value')).to_have_text('发热伴咳嗽、咽痛2天')
            expect(page.locator('[data-field="preliminary_diagnosis"] .field-status-text')).to_have_text('待确认')
            page.locator('#workspaceReviewTools summary').click()
            page.select_option('#workspaceReviewScene', 'approved')
            expect(page.locator('[data-field="preliminary_diagnosis"] .field-title')).to_have_text('候选诊断（医生已审核）')
            expect(page.locator('[data-field="preliminary_diagnosis"] .field-status-text')).to_have_text('已处理')
            page.evaluate("appState.currentRecordFields.candidate_diagnoses[0].doctor_review_status='pending';renderAll()")
            expect(page.locator('[data-field="preliminary_diagnosis"] .field-status-text')).to_have_text('待确认')
            page.evaluate("""() => {
                appState.currentRecordFields.candidate_diagnoses[0].doctor_review_status='candidate_confirmed';
                appState.currentExportReadiness={approved:false,can_export:false};
                appState.currentTask.current_stage='doctor_review';appState.taskStatus='doctor_review';
                appState.currentEncounter.status='draft';renderAll();
            }""")
            expect(page.locator('[data-field="preliminary_diagnosis"] .field-title')).to_have_text('候选诊断（待医生确认）')
            expect(page.locator('[data-field="preliminary_diagnosis"] .field-status-text')).to_have_text('待确认')
            browser.close()
    finally:
        server.close()


def test_workspace_review_reload_waits_for_existing_encounter_restore():
    root = Path(__file__).resolve().parents[1]
    artifacts = root / '.artifacts'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='review-reload-', dir=artifacts) as directory:
        runtime = Path(directory).resolve()
        assert runtime.is_relative_to(artifacts.resolve())
        port = _free_port()
        base_url = f'http://127.0.0.1:{port}'
        process = subprocess.Popen(
            [sys.executable, 'scripts/alpha51_workspace_review.py', '--port', str(port),
             '--runtime', str(runtime.relative_to(root.resolve()))],
            cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_health(base_url)
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width':1440,'height':900})
                generated_for = []
                failures = []
                page.on('request', lambda request: generated_for.append(request.post_data_json['encounter_id'])
                        if request.method == 'POST' and request.url.endswith('/api/records/generate') else None)
                page.on('console', lambda message: failures.append(message.text)
                        if message.type == 'error' and 'Visual review fixture:' in message.text else None)
                page.goto(f'{base_url}/workspace-review')
                page.fill('#loginUsername', 'admin')
                page.fill('#loginPassword', DEFAULT_ADMIN_PASSWORD)
                page.click('#loginForm button[type="submit"]')
                expect(page.locator('#workspaceReviewScene')).to_be_attached(timeout=30000)
                old_id = page.evaluate('selectedEncounterId()')
                assert f'encounter_id={old_id}' in page.url

                def delay_original_restore(route):
                    time.sleep(0.8)
                    route.continue_()

                page.route(f'**/api/encounters/{old_id}', delay_original_restore)
                page.reload()
                expect(page.locator('#workspaceReviewScene')).to_be_attached(timeout=30000)
                new_id = page.evaluate('selectedEncounterId()')
                assert new_id != old_id
                assert [str(value) for value in generated_for] == [str(old_id), str(new_id)]
                assert not failures
                page.locator('#workspaceReviewTools summary').click()
                page.select_option('#workspaceReviewScene', 'empty')
                expect(page.get_by_role('button', name='开始录音', exact=True)).to_be_visible()
                browser.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_historical_missing_display_respects_recorded_doctor_decision():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            original = page.evaluate("""() => {
                const s = window.__MRA_APP_STATE__;
                for (const [key] of EDITABLE_FIELD_DEFS) s.currentRecordFields[key] = {
                    value:'已保存的字段内容', hint:null, missing:false, status:'present', source_spans:[]
                };
                for (const [key, review] of [['past_history','not_asked_confirmed'], ['physical_exam','missing_accepted'], ['allergy_history','pending']]) {
                    s.currentRecordFields[key] = {value:null, hint:key === 'past_history' ? null : 'null', missing:true, status:'missing', source_spans:[], doctor_review_status:review};
                }
                s.currentRecordFields.candidate_diagnoses = [];
                s.currentTask.result_json.fields = s.currentRecordFields;
                const raw = JSON.stringify(s.currentRecordFields); renderAll(); return raw;
            }""")
            expect(page.locator('[data-field="past_history"] .field-value')).to_have_text('医生确认本次未询问')
            expect(page.locator('[data-field="physical_exam"] .field-value')).to_have_text('医生接受本次信息缺失')
            expect(page.locator('[data-field="allergy_history"] .field-value')).to_have_text('历史字段无可用内容，原因未记录')
            expect(page.locator('.historical-record-notice')).to_have_count(1)
            assert page.evaluate('JSON.stringify(window.__MRA_APP_STATE__.currentRecordFields)') == original
            page.evaluate("""() => {
                appState.currentRecordFields.allergy_history = {value:'否认药物过敏', hint:null, missing:false, status:'present', source_spans:[]};
                renderAll();
            }""")
            expect(page.locator('.historical-record-notice')).to_have_count(0)
            browser.close()
    finally:
        server.close()
