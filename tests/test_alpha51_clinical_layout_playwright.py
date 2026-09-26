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
        page.evaluate("createRecordTask('发热咳嗽两天，体温38.2℃，没有胸痛，也没有药物过敏史。')")
        page.wait_for_function('window.__MRA_APP_STATE__.currentRecordFields && window.__MRA_APP_STATE__.eventSource === null')
        page.evaluate(Path('tests/fixtures/alpha51_workspace_review.js').read_text(encoding='utf-8'))
        yield page
        browser.close()

@pytest.mark.parametrize('width,height', [(1366,768),(1440,900),(1920,1080),(1093,614),(910,512)])
def test_clinical_density_and_auxiliary_panel_preserves_edit(page, width, height):
    page.set_viewport_size({'width': width, 'height': height})
    for scene in ['empty','recording','long','review','role','conflict']:
        page.select_option('#workspaceReviewScene', scene)
        metrics = page.evaluate("""() => {
          const selectors = ['.transcript-column','.field-column','.assist-column'];
          return {width:document.documentElement.scrollWidth, columns:selectors.map(sel => {
            const x=document.querySelector(sel), r=x.getBoundingClientRect();
            return {width:r.width,top:r.top,display:getComputedStyle(x).display};
          }), recordFont:getComputedStyle(document.querySelector('.field-value') || document.querySelector('.field-list')).fontSize};
        }""")
        assert metrics['width'] <= width + 1, (scene,metrics)
        columns = metrics['columns']
        if width >= 1280:
            assert columns[1]['top'] <= 180, (scene,metrics)
            total = sum(c['width'] for c in columns)
            for col,ratio in zip(columns,[.24,.54,.22]):
                assert abs(col['width']/total-ratio) < .01, metrics
        elif width >= 1024:
            assert columns[2]['display'] == 'none'
        else:
            assert columns[0]['display'] == columns[2]['display'] == 'none'
        if os.environ.get('ALPHA51_CLINICAL_SCREENSHOTS'):
            dest=Path(os.environ['ALPHA51_CLINICAL_SCREENSHOTS']);dest.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(dest/f'{scene}-{width}.png'))
    page.select_option('#workspaceReviewScene','draft')
    page.click('#editRecordButton')
    editor=page.locator('[data-record-field-input="chief_complaint"]')
    editor.fill('合成未保存修改')
    if width < 1280:
        page.click('#showReferenceButton')
        expect(page.locator('#workspaceAuxDialog')).to_be_visible()
    page.get_by_role('button',name='上呼吸道感染',exact=True).click()
    expect(page.locator('#drawer')).to_contain_text('发热、咳嗽和咽痛')
    expect(page.locator('#closeDrawerButton')).to_be_focused()
    page.keyboard.press('Escape')
    expect(editor).to_have_value('合成未保存修改')
    if width < 1280:
        expect(page.locator('#showReferenceButton')).to_be_focused()
        page.click('#showReferenceButton')
        page.keyboard.press('Escape')
        expect(page.locator('#showReferenceButton')).to_be_focused()
    expect(page.locator('#exportButton')).to_be_disabled()


def test_recording_controls_are_one_inline_group_and_role_gate_remains(page):
    page.select_option('#workspaceReviewScene','recording')
    for key in ['pauseBrowserRecordingButton','stopBrowserRecordingButton','cancelBrowserRecordingButton']:
        expect(page.locator('#'+key)).to_be_visible()
    for key in ['startBrowserRecordingButton','resumeBrowserRecordingButton','submitBrowserRecordingButton']:
        expect(page.locator('#'+key)).to_be_hidden()
    expect(page.locator('.encounter-action-bar')).to_be_hidden()
    page.select_option('#workspaceReviewScene','role')
    expect(page.locator('#nextActionPanel')).to_be_visible()
    expect(page.locator('#nextActionPanel')).to_contain_text('确认')
    assert page.evaluate('roleReviewRequired()') is True
    page.select_option('#workspaceReviewScene','conflict')
    expect(page.locator('.record-edit-notice.conflict')).to_be_visible()
    expect(page.locator('[data-record-reload-latest]')).to_be_visible()
    expect(page.locator('#exportButton')).to_be_disabled()
