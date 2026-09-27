"""Reference presentation contracts on the real doctor page, no model evidence."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.test_doctor_reference_sidebar_playwright import page, server, prepare_reference_fixture


def open_reference(page):
    prepare_reference_fixture(page)
    if page.viewport_size['width'] < 1280:
        page.click('#showReferenceButton')
    page.get_by_role('button', name='上呼吸道感染', exact=True).click()
    return page.locator('.reference-detail')


def test_production_page_has_no_review_injection_and_fixture_tools_are_explicit(page):
    expect(page.locator('#workspaceReviewTools')).to_have_count(0)
    assert page.locator('script[src*="__workspace_review"]').count() == 0
    assert page.evaluate('typeof window.setWorkspaceReviewScene') == 'undefined'
    prepare_reference_fixture(page)
    page.evaluate(Path('tests/fixtures/alpha51_workspace_review.js').read_text(encoding='utf8'))
    expect(page.locator('.review-data-badge')).to_have_text('演示数据')
    expect(page.locator('#workspaceReviewScene')).to_be_hidden()
    page.locator('#workspaceReviewTools summary').click()
    expect(page.locator('.review-tools-popover')).to_contain_text('未执行真实模型')
    page.select_option('#workspaceReviewScene', 'role')
    expect(page.locator('#workspaceReviewScene')).to_be_hidden()
    assert page.evaluate('roleReviewRequired()') is True


def test_detail_tabs_keyboard_traceability_score_and_edit_preservation(page):
    root = open_reference(page)
    expect(root.get_by_role('tab', name='患者依据')).to_have_attribute('aria-selected', 'true')
    expect(root.locator('#reference-panel-patient')).to_contain_text('00:00.0–00:08.0')
    expect(root.locator('.reference-metadata', has_text='技术说明')).to_have_count(1)
    assert root.inner_text().count('证据匹配度') == 0
    root.get_by_role('tab', name='患者依据').focus()
    page.keyboard.press('ArrowRight')
    expect(root.get_by_role('tab', name='指南资料')).to_be_focused()
    expect(root.locator('#reference-panel-guides')).to_be_visible()
    expect(root).to_contain_text('病例级资料 · 未关联当前项目')
    root.locator('summary', has_text='来源详情').click()
    expect(root).to_contain_text('f' * 64)
    page.keyboard.press('Escape')
    expect(page.get_by_role('button', name='上呼吸道感染', exact=True)).to_be_focused()
    page.click('#editRecordButton')
    editor = page.locator('[data-record-field-input="chief_complaint"]')
    editor.fill('合成未保存内容')
    page.get_by_role('button', name='查看处理建议', exact=True).click()
    expect(page.locator('#reference-panel-patient')).to_contain_text('合成处理建议')
    page.get_by_role('tab', name='待核对事项').click()
    expect(page.locator('#reference-panel-checks')).to_contain_text('病例级候选提示')
    page.keyboard.press('Escape')
    expect(editor).to_have_value('合成未保存内容')
    expect(page.locator('#exportButton')).to_be_disabled()


@pytest.mark.parametrize('status,message', [('idle','尚未加载'),('ready','本次知识检索无结果'),('failed','知识服务不可用')])
def test_unlinked_no_results_and_failure_are_distinct(page, status, message):
    prepare_reference_fixture(page)
    page.evaluate("""status => {
      const s=window.__MRA_APP_STATE__; s.currentRecordFields.candidate_diagnoses[0].references=[];
      s.currentKnowledgeEvidence={results:[]};s.knowledgeEvidenceStatus=status;
    }""", status)
    page.get_by_role('button', name='上呼吸道感染', exact=True).click()
    page.get_by_role('tab', name='指南资料').click()
    expect(page.locator('#reference-panel-guides')).to_contain_text('当前项目未关联指南')
    expect(page.locator('#reference-panel-guides')).to_contain_text(message)


def test_conflicts_remain_visible_on_every_tab_and_sources_escape_html(page):
    prepare_reference_fixture(page)
    page.evaluate("""() => {
      const s=window.__MRA_APP_STATE__;s.recordEditConflict={code:'REVISION_CONFLICT'};
      const r=s.currentRecordFields.candidate_diagnoses[0].references[0];
      r.title='<img src=x onerror=alert(1)>';r.url='javascript:alert(1)';
    }""")
    page.get_by_role('button', name='上呼吸道感染', exact=True).click()
    for label in ['患者依据','指南资料','待核对事项']:
        page.get_by_role('tab',name=label).click()
        expect(page.locator('.reference-summary')).to_contain_text('病历版本冲突')
    expect(page.locator('.reference-detail img')).to_have_count(0)
    expect(page.locator('.reference-detail a[href^="javascript:"]')).to_have_count(0)
    expect(page.locator('.reference-detail')).not_to_contain_text('质量可用')
    page.get_by_role('tab', name='待核对事项').focus()
    page.keyboard.press('Home')
    expect(page.get_by_role('tab',name='患者依据')).to_be_focused()
    page.keyboard.press('End')
    expect(page.get_by_role('tab',name='待核对事项')).to_be_focused()
    page.locator('summary',has_text='技术说明').click()
    assert page.locator('.reference-detail').inner_text().count('证据匹配度') == 1


@pytest.mark.parametrize('width,height', [(1366,768),(1440,900),(1920,1080),(910,512),(390,844)])
def test_reference_drawer_readability_and_single_scroll(page, width, height):
    page.set_viewport_size({'width':width,'height':height})
    root=open_reference(page)
    for label in ['患者依据','指南资料','待核对事项']:
        root.get_by_role('tab',name=label).click()
        metrics=root.evaluate("""el => {
          const body=el.querySelector('.reference-body'), r=el.getBoundingClientRect();
          return {width:r.width, right:r.right, overflow:body.scrollWidth>body.clientWidth+1,
            font:getComputedStyle(el).fontSize, scroll:getComputedStyle(body).overflowY};
        }""")
        assert metrics['width'] <= min(680,width) and metrics['right'] <= width+1, metrics
        assert metrics['font']=='16px' and metrics['scroll']=='auto' and not metrics['overflow'],metrics
        expect(page.locator('#closeDrawerButton')).to_be_in_viewport()
        if os.environ.get('ALPHA51_DETAIL_SCREENSHOTS'):
            dest=Path(os.environ['ALPHA51_DETAIL_SCREENSHOTS']);dest.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(dest/f'{width}-{label}.png'))


def test_reference_status_uses_existing_schema_enums(page):
    prepare_reference_fixture(page)
    cases = [('candidate_confirmed', '医生已确认'), ('content_confirmed', '医生已确认'),
             ('ai_candidate_deleted', '医生已排除'), ('not_asked_confirmed', '医生已确认本次未询问'),
             ('missing_accepted', '医生已接受本次缺失'), ('pending', '候选 · 待医生确认')]
    for status, label in cases:
        assert page.evaluate('s => referenceReviewStatus({doctor_review_status:s})', status) == label
    assert page.evaluate('referenceStatusLabel({verification_status:"source_verified",clinical_review_status:"reviewed"})') == '来源已核验，临床映射已复核'
    page.evaluate("window.__MRA_APP_STATE__.currentRecordFields.candidate_diagnoses[0].references[0].evidence_scope='合成适用限制'")
    page.get_by_role('button', name='上呼吸道感染', exact=True).click()
    page.get_by_role('tab', name='指南资料').click()
    expect(page.locator('#reference-panel-guides')).to_contain_text('适用范围：合成适用限制')
