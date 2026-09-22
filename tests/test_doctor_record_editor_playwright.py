from __future__ import annotations

from playwright.sync_api import expect, sync_playwright

from tests.test_doctor_itemized_approval_playwright import (
    RunningServer,
    _login,
    _prepare_review_fixture,
)


def _import_knowledge_fixture(page) -> str:
    return page.evaluate(
        """
        async () => {
          const imported = await api('/api/knowledge/admin/import', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              source_id: 'nhc-alpha33-editor',
              title: '发热病历记录规范（匿名测试）',
              publisher: '国家卫生健康委员会（测试元数据）',
              source_url: 'https://www.nhc.gov.cn/example/alpha33-editor',
              published_at: '2026-01-01',
              effective_date: '2026-01-01',
              version: 'alpha33-test-v1',
              usage_scope: '仅用于自动化测试中的医生人工参考。',
              document_type: 'record-standard',
              disease_scope: '发热/呼吸',
              filename: 'alpha33-editor.md',
              content: '# 发热记录\\n发热患者病历应记录体温、咳嗽、胸痛和过敏史。'
            })
          });
          await api(`/api/knowledge/admin/documents/${imported.document_id}/enable`, {method: 'POST'});
          return imported.document_id;
        }
        """
    )


def test_whole_page_edit_save_reload_and_active_knowledge_query() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            _login(page, server.base_url)
            task_id = _prepare_review_fixture(page)
            document_id = _import_knowledge_fixture(page)
            revision_before = int(page.evaluate("window.__MRA_APP_STATE__.currentExportReadiness.revision_id"))

            page.click("#editRecordButton")
            expect(page.locator("#recordFields [data-record-field-input]")).to_have_count(7)
            original_past_history = page.locator('[data-record-field-input="past_history"]').input_value()
            page.locator('[data-record-field-input="past_history"]').fill("本次修改随后取消")
            page.click("#cancelRecordEditButton")
            expect(page.locator("#recordFields [data-record-field-input]")).to_have_count(0)
            page.click("#editRecordButton")
            expect(page.locator('[data-record-field-input="past_history"]')).to_have_value(original_past_history)
            editor = page.locator('[data-record-field-input="chief_complaint"]')
            editor.fill("患者发热39度，医生补充记录")
            expect(page.locator("[data-record-edit-status]")).to_have_text("有未保存修改")
            expect(page.locator("#saveDraftButton")).to_be_enabled()
            expect(page.locator("#confirmFieldsButton")).to_be_disabled()
            expect(page.locator("#exportButton")).to_be_disabled()

            page.click("#saveDraftButton")
            page.wait_for_function("!window.__MRA_APP_STATE__.recordEditMode", timeout=15000)
            page.wait_for_function(
                "(oldRevision) => Number(window.__MRA_APP_STATE__.currentExportReadiness?.revision_id) > oldRevision",
                arg=revision_before,
                timeout=15000,
            )
            persisted = page.evaluate(
                """async (taskId) => {
                  const task = await fetch(`/api/tasks/${taskId}`).then((response) => response.json());
                  return task.result_json.fields.chief_complaint.value;
                }""",
                task_id,
            )
            assert persisted == "患者发热39度，医生补充记录"

            page.click('[data-field="chief_complaint"] [data-knowledge-field="chief_complaint"]')
            page.wait_for_function(
                "window.__MRA_APP_STATE__.fieldKnowledgeSearch.chief_complaint?.status === 'ready'",
                timeout=15000,
            )
            detail = page.locator("#detailDrawerContent")
            expect(detail).to_contain_text("发热病历记录规范")
            expect(detail).to_contain_text("alpha33-test-v1")
            expect(detail).to_contain_text(document_id)
            expect(detail).to_contain_text("内容 SHA256")
            expect(detail.locator('a[href^="https://www.nhc.gov.cn/"]')).to_have_count(1)
            browser.close()
    finally:
        server.close()


def test_stale_revision_keeps_local_edit_until_doctor_loads_latest() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            page.click("#editRecordButton")
            editor = page.locator('[data-record-field-input="chief_complaint"]')
            editor.fill("本地尚未保存的医生修改")

            page.evaluate(
                """async () => {
                  const taskId = window.__MRA_APP_STATE__.currentTaskId;
                  const task = await fetch(`/api/tasks/${taskId}`).then((response) => response.json());
                  const readiness = await fetch(`/api/tasks/${taskId}/export-readiness`).then((response) => response.json());
                  await api(`/api/tasks/${taskId}/review`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                      fields: task.result_json.fields,
                      expected_revision_id: readiness.revision_id,
                      expected_content_hash: readiness.content_hash
                    })
                  });
                }"""
            )
            page.click("#saveDraftButton")
            expect(page.locator(".record-edit-notice.conflict")).to_be_visible(timeout=15000)
            expect(page.locator('[data-record-field-input="chief_complaint"]')).to_have_value("本地尚未保存的医生修改")
            expect(page.locator("[data-record-reload-latest]")).to_be_visible()

            page.click("[data-record-reload-latest]")
            page.wait_for_function("!window.__MRA_APP_STATE__.recordEditMode", timeout=15000)
            expect(page.locator("[data-record-field-input]")).to_have_count(0)
            browser.close()
    finally:
        server.close()
