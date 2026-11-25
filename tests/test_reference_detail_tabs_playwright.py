"""Reference presentation contracts on the real doctor page, no model evidence."""
import os
import secrets
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.test_doctor_reference_sidebar_playwright import page, server, prepare_reference_fixture
from tests.test_manual_first_draft_playwright import login_doctor


def open_reference(page, name='上呼吸道感染'):
    page.locator('#showReferenceButton').click()
    panel = page.locator('#workspaceAuxDialog')
    expect(panel).to_be_visible()
    panel.get_by_role('button', name=name, exact=True).click()
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
    prepare_reference_fixture(page)
    root = open_reference(page)
    expect(root.get_by_role('tab', name='患者依据')).to_have_attribute('aria-selected', 'true')
    expect(root.locator('#reference-panel-patient')).to_contain_text('00:00.0–00:08.0')
    expect(root.locator('.reference-metadata', has_text='技术说明')).to_have_count(1)
    assert root.inner_text().count('证据匹配度') == 0
    root.get_by_role('tab', name='患者依据').focus()
    page.keyboard.press('ArrowRight')
    expect(root.get_by_role('tab', name='参考资料')).to_be_focused()
    expect(root.locator('#reference-panel-guides')).to_be_visible()
    expect(root).to_contain_text('病例级资料 · 未关联当前项目')
    root.locator('summary', has_text='来源详情').click()
    expect(root).to_contain_text('f' * 64)
    page.keyboard.press('Escape')
    expect(page.locator('#showReferenceButton')).to_be_focused()
    page.click('#editRecordButton')
    editor = page.locator('[data-record-field-input="chief_complaint"]')
    editor.fill('合成未保存内容')
    open_reference(page, '查看处理建议')
    expect(page.locator('#reference-panel-patient')).to_contain_text('合成处理建议')
    page.get_by_role('tab', name='待核对事项').click()
    expect(page.locator('#reference-panel-checks')).to_contain_text('病例级候选提示')
    page.keyboard.press('Escape')
    expect(page.locator('#showReferenceButton')).to_be_focused()
    expect(editor).to_have_value('合成未保存内容')
    expect(page.locator('#exportButton')).to_be_disabled()


def test_patient_evidence_keeps_unverified_quote_without_borrowing_the_segment_time(page):
    prepare_reference_fixture(page)
    page.evaluate("""() => {
      const evidence = window.__MRA_APP_STATE__.currentRecordFields.candidate_diagnoses[0].evidence;
      evidence.push({...evidence[0], text: '合成原文：' + evidence[0].text});
    }""")
    open_reference(page)
    cards = page.locator('#reference-panel-patient .field-evidence-detail')
    expect(cards).to_have_count(2)
    expect(cards.nth(0).locator('p')).to_have_text('今天发热三十八点二度，没有胸痛。')
    expect(cards.nth(0)).to_contain_text('00:00.0–00:08.0')
    expect(cards.nth(0)).to_contain_text('说话人标注')
    expect(cards.nth(1).locator('p')).to_have_text('合成原文：今天发热三十八点二度，没有胸痛。')
    expect(cards.nth(1)).to_contain_text('未记录音频时间')
    expect(cards.nth(1)).not_to_contain_text('00:00.0–00:08.0')
    expect(cards.nth(1)).not_to_contain_text('说话人标注')


@pytest.mark.parametrize('status,message', [('idle','尚未加载'),('ready','本次知识检索无结果'),('failed','知识服务不可用')])
def test_unlinked_no_results_and_failure_are_distinct(page, status, message):
    prepare_reference_fixture(page)
    page.evaluate("""status => {
      const s=window.__MRA_APP_STATE__; s.currentRecordFields.candidate_diagnoses[0].references=[];
      s.currentKnowledgeEvidence={results:[]};s.knowledgeEvidenceStatus=status;
    }""", status)
    open_reference(page)
    page.get_by_role('tab', name='参考资料').click()
    expect(page.locator('#reference-panel-guides')).to_contain_text('当前项目未关联参考资料')
    expect(page.locator('#reference-panel-guides')).to_contain_text(message)


def test_conflicts_remain_visible_on_every_tab_and_sources_escape_html(page):
    prepare_reference_fixture(page)
    page.evaluate("""() => {
      const s=window.__MRA_APP_STATE__;s.recordEditConflict={code:'REVISION_CONFLICT'};
      const r=s.currentRecordFields.candidate_diagnoses[0].references[0];
      r.title='<img src=x onerror=alert(1)>';r.url='javascript:alert(1)';
    }""")
    open_reference(page)
    for label in ['患者依据','参考资料','待核对事项']:
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
    prepare_reference_fixture(page)
    root=open_reference(page)
    for label in ['患者依据','参考资料','待核对事项']:
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
             ('ai_candidate_deleted', '已移除AI候选'), ('not_asked_confirmed', '医生已确认本次未询问'),
             ('missing_accepted', '医生已接受本次缺失'), ('pending', '候选 · 待医生确认')]
    for status, label in cases:
        assert page.evaluate('s => referenceReviewStatus({doctor_review_status:s})', status) == label
    assert page.evaluate('referenceStatusLabel({verification_status:"source_verified",clinical_review_status:"reviewed"})') == '来源已核验，临床映射已复核'
    page.evaluate("window.__MRA_APP_STATE__.currentRecordFields.candidate_diagnoses[0].references[0].evidence_scope='合成适用限制'")
    open_reference(page)
    page.get_by_role('tab', name='参考资料').click()
    expect(page.locator('#reference-panel-guides')).to_contain_text('适用范围：合成适用限制')


def test_doctor_conflict_alerts_identify_the_field_without_editing_other_messages(page, server):
    password = secrets.token_urlsafe(24)
    account = page.request.post(server.base_url + '/api/auth/users', data={
        'username': 'reference-test-doctor', 'password': password, 'display_name': '参考资料测试', 'role': 'doctor'})
    assert account.status == 201
    page.locator('#logoutButton').click()
    login_doctor(page, 'reference-test-doctor', password)
    prepare_reference_fixture(page)
    # The review API already returned a physical-exam conflict for this revision.
    physical_conflict = 'physical_exam存在证据冲突，必须先修正。'
    known_conflict = 'past_history存在证据冲突，必须先修正。'
    unchanged = ['unknown_field存在证据冲突，必须先修正。',
                 '原话提到“past_history存在证据冲突，必须先修正。”，请核对。']
    errors = page.evaluate('window.__MRA_APP_STATE__.currentSafetyCheck.errors')
    assert physical_conflict in errors
    page.evaluate('extras => window.__MRA_APP_STATE__.currentSafetyCheck.errors.push(...extras)',
                  [known_conflict, *unchanged])
    for name in ('上呼吸道感染', '查看处理建议'):
        open_reference(page, name)
        summary = page.locator('.reference-summary')
        for expected in ('查体存在证据冲突，必须先修正。', '既往史存在证据冲突，必须先修正。',
                         '安全校验尚未通过，审核及导出限制保持生效。', *unchanged):
            expect(summary.get_by_text(expected, exact=True)).to_be_visible()
        expect(summary.get_by_text(known_conflict, exact=True)).to_have_count(0)
        page.keyboard.press('Escape')
    expect(page.locator('#exportButton')).to_be_disabled()
    assert page.evaluate('window.__MRA_APP_STATE__.currentSafetyCheck.errors') == [
        *errors, known_conflict, *unchanged]


def test_registration_purpose_and_clinical_scope_stay_with_their_own_source(page):
    prepare_reference_fixture(page)
    page.evaluate("""() => {
      const state = window.__MRA_APP_STATE__;
      state.currentRecordFields.candidate_diagnoses[0].references = [{
        title: '合成的已关联资料', document_type: 'record-standard', metadata_origin: 'version_import',
        usage_scope: '用于核对书写项目', evidence_scope: '仅限合成记录第一段',
        disease_scope: '<em>初诊书写</em>', excerpt: '合成摘录'
      }];
      state.currentKnowledgeEvidence.results = [{
        title: '合成的病例资料', document_type: 'clinical-reference', metadata_origin: 'legacy_observed',
        usage_scope: '旧库用途文字', evidence_scope: ' 　'
      }, {title: '未登记示例', usage_scope: '  ', evidence_scope: {}}];
    }""")
    open_reference(page)
    patient = page.locator('#reference-panel-patient')
    expect(patient).not_to_contain_text('用于核对书写项目')
    page.get_by_role('tab', name='参考资料').click()
    panel = page.locator('#reference-panel-guides')
    linked = panel.locator('section').filter(has=page.get_by_role('heading', name='已关联参考资料', exact=True))
    expect(linked).to_contain_text('登记类别：病历规范')
    expect(linked).to_contain_text('适用范围：仅限合成记录第一段')
    expect(linked).to_contain_text('登记用途：用于核对书写项目')
    topic = linked.get_by_text('<em>初诊书写</em>', exact=True)
    expect(topic).to_be_hidden()
    linked.locator('summary').press('Enter')
    expect(topic).to_be_visible()
    expect(linked.locator('em')).to_have_count(0)
    other = panel.locator('section').filter(has=page.get_by_role('heading', name='病例级资料 · 未关联当前项目'))
    expect(other.locator('article h4')).to_have_text(['合成的病例资料', '未登记示例'])
    expect(other.locator('article').first).to_contain_text('旧库共用类别：临床参考（通用分类）')
    expect(other.locator('article').first).to_contain_text('旧库共用用途登记：旧库用途文字')
    expect(other.locator('article').last).to_contain_text('本条资料未提供登记用途。')
    expect(other).not_to_contain_text('适用范围：')
    expect(other).not_to_contain_text('仅限合成记录第一段')


def test_demo_identity_and_runtime_modes_do_not_claim_unverified_hybrid(page):
    prepare_reference_fixture(page)
    page.evaluate("""() => {
      const s=window.__MRA_APP_STATE__;
      s.currentEncounter.patient_deidentified_id='SIM-DEMO-0929-NEGATION';
      s.currentKnowledgeEvidence.retrieval_mode='fts5_v1'; renderAll();
    }""")
    expect(page.locator('#patientName')).to_have_text('李示例')
    expect(page.locator('#patientDemoBadge')).to_be_visible()
    expect(page.locator('#settingsKnowledgeRuntimeStatus')).to_have_text('本次知识检索：关键词全文检索（FTS5）')
    page.evaluate("window.__MRA_APP_STATE__.knowledgeEvidenceStatus='failed';renderAll()")
    expect(page.locator('#settingsKnowledgeRuntimeStatus')).to_have_text('知识检索不可用')
    assert page.evaluate("syntheticDemoLabel({patient_deidentified_id:'NORMAL-001'})") == ''
