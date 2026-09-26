"""Real doctor.html reference navigation; synthetic fixtures are not model evidence."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from tests.test_doctor_itemized_approval_playwright import RunningServer, _login, _prepare_review_fixture


def prepare_reference_fixture(page) -> None:
    _prepare_review_fixture(page)
    page.evaluate("""() => {
      const s = window.__MRA_APP_STATE__;
      s.currentEncounter = {id: 'SIM-REF-001', patient_display_name: '模拟患者',
        patient_deidentified_id: 'SIM-REF-001', check_in_status: 'checked_in'};
      const base = s.currentRecordFields.candidate_diagnoses[0];
      s.currentRecordFields.candidate_diagnoses = ['上呼吸道感染', '流行性感冒', '社区获得性肺炎待排'].map((name, i) => ({
        ...base, name, reason: '合成依据：发热与咳嗽，仍需医生结合检查判断。'.repeat(8),
        evidence: [{text: '合成原文：今天发热三十八点二度，没有胸痛。', segment_id: 'sim-segment-1'}],
        suggested_checks: ['合成检查提示：按临床需要评估'], medication_notes: ['合成用药提示：不得自动处方'],
        follow_up_questions: ['合成补问：症状持续多久？'], risk_warnings: ['合成风险：病情变化需医生复核'],
        references: [{title: '合成指南来源（展示测试）', publisher: '测试机构', version: 'fixture-v1',
          url: 'https://example.org/clinical-reference', verification_status: 'unverified'}]
      }));
      s.currentRecordFields.treatment_plan = {value: '合成处理建议：由医生结合病情核对，不构成处方。'.repeat(15)};
      s.knowledgeEvidenceStatus = 'ready';
      s.currentKnowledgeEvidence = {results: [{title: '病例级合成资料', publisher: '测试机构', version: 'fixture-v1',
        section: '合成章节', page: 1, content_sha256: 'f'.repeat(64), chunk_id: 'fixture-chunk', document_id: 'fixture-doc',
        source_url: 'https://example.org/case-reference', excerpt: '病例级摘要，不与某一诊断自动关联'}]};
      s.currentAsrResult = {segments: [{segment_id: 'sim-segment-1', text: '今天发热三十八点二度，没有胸痛。',
        role: 'patient', speaker: 'speaker_1', start: 0, end: 8}], role_quality: {status: 'passed'}};
      setProductView('encounter'); renderAll();
    }""")


@pytest.fixture(scope="module")
def server():
    instance = RunningServer()
    yield instance
    instance.close()


@pytest.fixture
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.environ.get('ALPHA51_BROWSER_CHANNEL') or None)
        tab = browser.new_page(viewport={"width": 1440, "height": 900})
        _login(tab, server.base_url)
        yield tab
        browser.close()


def test_reference_names_open_full_details_without_losing_edits(page):
    prepare_reference_fixture(page)
    panel = page.locator('#assistPanels')
    expect(panel.locator('.clinical-reference-section')).to_have_count(2)
    expect(panel.get_by_role('button')).to_have_count(4)
    expect(panel).not_to_contain_text('合成依据')
    expect(panel).not_to_contain_text('合成处理建议')
    expect(panel).not_to_contain_text('证据匹配')
    page.locator('#editRecordButton').click()
    editor = page.locator('[data-record-field-input="chief_complaint"]')
    editor.fill('未保存的合成修改')
    row = panel.get_by_role('button', name='上呼吸道感染', exact=True)
    row.click()
    drawer = page.locator('#drawer')
    expect(drawer).to_contain_text('合成依据')
    expect(drawer).to_contain_text('合成原文')
    expect(drawer).to_contain_text('合成指南来源')
    expect(drawer).to_contain_text('病例级参考（未关联单项）')
    expect(drawer.get_by_role('link', name='查看来源')).to_have_attribute('href', 'https://example.org/clinical-reference')
    expect(page.locator('#closeDrawerButton')).to_be_focused()
    drawer.locator('summary', has_text='病例级参考（未关联单项）').click()
    expect(drawer).to_contain_text('病例级合成资料')
    expect(drawer.get_by_role('link', name='打开官方来源')).to_have_attribute('href', 'https://example.org/case-reference')
    page.locator('#closeDrawerButton').focus()
    page.keyboard.press('Shift+Tab')
    assert page.evaluate('document.querySelector("#drawer").contains(document.activeElement)')
    page.keyboard.press('Escape')
    expect(drawer).to_have_attribute('aria-hidden', 'true')
    expect(row).to_be_focused()
    expect(editor).to_have_value('未保存的合成修改')
    panel.get_by_role('button', name='查看处理建议', exact=True).click()
    expect(drawer).to_contain_text('合成处理建议')
    expect(drawer).to_contain_text('合成用药提示')
    page.locator('#closeDrawerButton').click()
    expect(panel.get_by_role('button', name='查看处理建议', exact=True)).to_be_focused()
    expect(editor).to_have_value('未保存的合成修改')
    expect(page.locator('#exportButton')).to_be_disabled()


def test_empty_live_and_failure_references_remain_compact_and_escaped(page):
    page.evaluate('setProductView("encounter"); renderAll()')
    panel = page.locator('#assistPanels')
    expect(panel.locator('.clinical-reference-section')).to_have_count(2)
    expect(panel.get_by_role('button')).to_have_count(0)

    page.evaluate("""() => {
      applyLiveClinicalDraft({version: 1, stable_segment_count: 2,
        differentials: [{name: '<img src=x onerror=alert(1)>', summary: '临时诊断说明', missing_evidence: ['缺少检查']}],
        care_plan: [{title: '观察与复评', summary: '临时处理详情', evidence_segment_ids: ['s1']}],
        alerts: [{title: '待复核', summary: '临时危险征象'}], missing_items: [{summary: '补充查体'}]});
      renderAssist();
    }""")
    expect(panel.locator('img')).to_have_count(0)
    expect(panel.get_by_role('button')).to_have_count(2)
    expect(panel).not_to_contain_text('临时诊断说明')
    panel.get_by_role('button', name='<img src=x onerror=alert(1)>', exact=True).click()
    expect(page.locator('#drawer')).to_contain_text('临时诊断说明')
    expect(page.locator('#drawer')).to_contain_text('临时结果')
    page.keyboard.press('Escape')
    panel.get_by_role('button', name='观察与复评', exact=True).click()
    expect(page.locator('#drawer')).to_contain_text('临时处理详情')
    page.keyboard.press('Escape')
    page.evaluate('window.__MRA_APP_STATE__.liveClinicalError="参考生成失败"; window.__MRA_APP_STATE__.liveClinicalDraft=null; renderAssist()')
    expect(panel).to_contain_text('参考生成失败')
    expect(panel.get_by_role('button')).to_have_count(0)


def test_live_reference_close_does_not_stop_recording_and_restores_replaced_trigger(page):
    page.evaluate("""() => {
      setProductView('encounter');
      applyLiveClinicalDraft({version: 1, differentials: [{name: '临时参考', summary: '合成说明'}]});
      window.__MRA_APP_STATE__.browserRecordingStatus = 'recording';
      renderAssist();
    }""")
    page.get_by_role('button', name='临时参考', exact=True).click()
    page.evaluate('renderAssist()')  # A new stable SSE update replaces the trigger DOM.
    page.keyboard.press('Escape')
    expect(page.locator('#drawer')).to_have_attribute('aria-hidden', 'true')
    expect(page.get_by_role('button', name='临时参考', exact=True)).to_be_focused()
    assert page.evaluate('window.__MRA_APP_STATE__.browserRecordingStatus') == 'recording'


@pytest.mark.parametrize('width,height', [(1366,768),(1440,900),(1920,1080),(1093,614),(910,512)])
def test_reference_layout_on_real_page(page, width, height):
    page.set_viewport_size({"width": width, "height": height})
    prepare_reference_fixture(page)
    layout = page.evaluate("""() => {
      const size = selector => parseFloat(getComputedStyle(document.querySelector(selector)).fontSize);
      return {width: document.documentElement.scrollWidth, nav: size('.product-nav-item span'),
        title: size('.brand-copy h1'), heading: size('.alpha51-workspace .panel-header h2'),
        field: size('.field-value'), transcript: size('.transcript-row-text'),
        headers: [...document.querySelectorAll('.alpha51-workspace .column > .panel-header')].map(x => x.getBoundingClientRect().height),
        names: [...document.querySelectorAll('.clinical-reference-link')].map(x => ({
          font: parseFloat(getComputedStyle(x).fontSize), height: x.getBoundingClientRect().height}))};
    }""")
    assert layout['width'] <= width + 1, layout
    assert layout['nav'] == 16 and layout['title'] == 20 and layout['heading'] == 18, layout
    assert layout['field'] == 17 and layout['transcript'] == 16, layout
    visible_headers = [h for h in layout['headers'] if h > 0]
    assert max(visible_headers) - min(visible_headers) <= 1, layout
    if width < 1280:
        page.locator('#showReferenceButton').click()
    names = page.locator('.clinical-reference-link').evaluate_all("els => els.map(x => ({font: parseFloat(getComputedStyle(x).fontSize), height: x.getBoundingClientRect().height}))")
    assert all(x['font'] == 16 and x['height'] >= 44 for x in names), names
    page.get_by_role('button', name='上呼吸道感染', exact=True).click()
    expect(page.locator('#closeDrawerButton')).to_be_in_viewport()
    page.keyboard.press('Escape')
    page.wait_for_function('document.querySelector("#drawer").getBoundingClientRect().left >= innerWidth')
    if os.environ.get('ALPHA51_REFERENCE_SCREENSHOTS'):
        dest = Path(os.environ['ALPHA51_REFERENCE_SCREENSHOTS'])
        dest.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(dest / f'after-{width}.png'), full_page=True)
