"""Clinical layout candidate on real doctor DOM, synthetic data only."""
from pathlib import Path
import os
import pytest
from playwright.sync_api import expect, sync_playwright
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login

@pytest.fixture(scope='module')
def server():
    server = RunningServer()
    yield server
    server.close()

@pytest.fixture
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.environ.get('ALPHA51_BROWSER_CHANNEL') or None)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        _login(page, server.base_url)
        page.locator('#localRegistrationDisclosure summary').click()
        page.select_option('#localSyntheticPatient', 'SIM-DEMO-0929-FEVER')
        page.click('#createLocalEncounterButton')
        page.locator('#dashboardEncounterList [data-encounter-action="start"]').first.click()
        expect(page.get_by_role('button', name='开始录音', exact=True)).to_be_visible()
        page.get_by_role('button', name='文本输入', exact=True).click()
        page.locator('#conversationInput').fill('发热咳嗽两天，体温38.2℃，没有胸痛，也没有药物过敏史。')
        page.locator('#submitTextButton').click()
        page.wait_for_function('window.__MRA_APP_STATE__.currentRecordFields && window.__MRA_APP_STATE__.eventSource === null')
        page.evaluate(Path('tests/fixtures/alpha51_workspace_review.js').read_text(encoding='utf-8'))
        yield page
        browser.close()

def choose_scene(page, scene):
    page.locator('#workspaceReviewTools summary').click()
    page.select_option('#workspaceReviewScene', scene)


@pytest.mark.parametrize('width,height', [(1366,768),(1440,900),(1920,1080),(1093,614),(910,512),(800,600)])
def test_clinical_density_and_auxiliary_panel_preserves_edit(page, width, height):
    page.set_viewport_size({'width': width, 'height': height})
    for scene in ['empty','recording','long','review','role','conflict']:
        choose_scene(page, scene)
        metrics = page.evaluate("""() => {
          const selectors = ['.transcript-column','.field-column','.assist-column'];
          const context=document.querySelector('.chart-context').getBoundingClientRect();
          return {width:document.documentElement.scrollWidth, contextRight:context.right, contextWidth:context.width,
            stepsBottom:document.querySelector('.encounter-command-center').getBoundingClientRect().bottom,
            chiefTop:document.querySelector('[data-field="chief_complaint"] .field-value')?.getBoundingClientRect().top,
            columns:selectors.map(sel => {
            const x=document.querySelector(sel), r=x.getBoundingClientRect();
            return {width:r.width,left:r.left,top:r.top,display:getComputedStyle(x).display};
          }), recordFont:getComputedStyle(document.querySelector('.field-value') || document.querySelector('.field-list')).fontSize};
        }""")
        assert metrics['width'] <= width + 1, (scene,metrics)
        columns = metrics['columns']
        if width >= 900 and scene in {'empty', 'recording', 'role'}:
            # Leave the approved 8px gap below the steps, even when patient identity wraps.
            assert abs(columns[1]['top'] - metrics['stepsBottom'] - 8) <= 1, (scene,metrics)
            assert columns[1]['top'] <= 193, (scene,metrics)
            total = sum(c['width'] for c in columns)
            for col,ratio in zip(columns,[.24,.54,.22]):
                assert abs(col['width']/total-ratio) < .01, metrics
        else:
            assert columns[0]['display'] == columns[2]['display'] == 'none'
            if width >= 900:
                assert 0 < metrics['contextWidth'] < columns[1]['width']
                assert metrics['contextRight'] <= columns[1]['left']
                assert columns[1]['width'] >= width * .60
                assert columns[1]['top'] <= 193
                if width >= 1366 and scene in {'long', 'review'}:
                    assert columns[1]['top'] < metrics['chiefTop'] < height, (scene,metrics)
        if os.environ.get('ALPHA51_CLINICAL_SCREENSHOTS'):
            dest=Path(os.environ['ALPHA51_CLINICAL_SCREENSHOTS']);dest.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(dest/f'{scene}-{width}.png'))
    choose_scene(page,'draft')
    page.click('#editRecordButton')
    editor=page.locator('[data-record-field-input="chief_complaint"]')
    editor.fill('合成未保存修改')
    page.click('#showReferenceButton')
    expect(page.locator('#workspaceAuxDialog')).to_be_visible()
    page.get_by_role('button',name='上呼吸道感染',exact=True).click()
    expect(page.locator('#drawer')).to_contain_text('发热、咳嗽和咽痛')
    expect(page.locator('#closeDrawerButton')).to_be_focused()
    page.keyboard.press('Escape')
    expect(editor).to_have_value('合成未保存修改')
    expect(page.locator('#showReferenceButton')).to_be_focused()
    page.click('#showReferenceButton')
    page.keyboard.press('Escape')
    expect(page.locator('#showReferenceButton')).to_be_focused()
    expect(page.locator('#exportButton')).to_be_disabled()


def test_recording_controls_are_one_inline_group_and_role_gate_remains(page):
    choose_scene(page,'recording')
    for key in ['pauseBrowserRecordingButton','stopBrowserRecordingButton','cancelBrowserRecordingButton']:
        expect(page.locator('#'+key)).to_be_visible()
    for key in ['startBrowserRecordingButton','resumeBrowserRecordingButton','submitBrowserRecordingButton']:
        expect(page.locator('#'+key)).to_be_hidden()
    expect(page.locator('.encounter-action-bar')).to_be_hidden()
    choose_scene(page,'role')
    expect(page.locator('#nextActionPanel')).to_be_visible()
    expect(page.locator('#nextActionPanel')).to_contain_text('确认')
    assert page.evaluate('roleReviewRequired()') is True
    choose_scene(page,'conflict')
    expect(page.locator('.record-edit-notice.conflict')).to_be_visible()
    expect(page.locator('[data-record-reload-latest]')).to_be_visible()
    expect(page.locator('#exportButton')).to_be_disabled()


def test_visit_summary_keeps_conflicts_and_unknown_allergies_out_of_patient_facts(page):
    choose_scene(page, 'draft')
    page.evaluate("""() => {
        const fields = appState.currentRecordFields;
        fields.past_history = {value: '合成待核的历史陈述', status: 'conflicting'};
        fields.allergy_history = {value: '', missing: true, doctor_review_status: 'not_asked_confirmed'};
        renderAll();
    }""")
    summary = page.locator('#chartContextFacts')
    expect(summary).to_contain_text('证据冲突')
    expect(summary).not_to_contain_text('合成待核的历史陈述')
    expect(summary).to_contain_text('本次未询问')
    choose_scene(page, 'empty')
    expect(summary).to_have_text('')
