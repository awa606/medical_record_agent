from __future__ import annotations

from contextlib import closing
import sqlite3

import pytest
from playwright.sync_api import expect, sync_playwright

from app.services.knowledge_store import DEFAULT_DISCLAIMER
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
            original_source_spans = page.evaluate(
                "async id => (await api(`/api/tasks/${id}`)).result_json.fields.chief_complaint.source_spans",
                task_id,
            )
            assert original_source_spans
            database_uri = f"file:{(server.root / 'edge.sqlite3').as_posix()}?mode=ro"
            with closing(sqlite3.connect(database_uri, uri=True)) as connection:
                original_revision = connection.execute(
                    "SELECT * FROM record_revision WHERE id = ?", (revision_before,)
                ).fetchone()
            assert original_revision is not None

            page.click("#editRecordButton")
            expect(page.locator("#recordFields [data-record-field-input]")).to_have_count(21)
            original_past_history = page.locator('[data-record-field-input="past_history"]').input_value()
            page.locator('[data-record-field-input="past_history"]').fill("本次修改随后取消")
            page.click("#cancelRecordEditButton")
            expect(page.locator("#recordFields [data-record-field-input]")).to_have_count(0)
            page.click("#editRecordButton")
            expect(page.locator('[data-record-field-input="past_history"]')).to_have_value(original_past_history)
            editor = page.locator('[data-record-field-input="chief_complaint"]')
            editor.fill("患者发热39度，医生补充记录")
            edited_field = page.evaluate("window.__MRA_APP_STATE__.currentRecordFields.chief_complaint")
            assert edited_field["status"] == "partial"
            assert edited_field["source_spans"] == []
            assert edited_field["confidence"] is None
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
                  return task.result_json.fields.chief_complaint;
                }""",
                task_id,
            )
            assert persisted["value"] == "患者发热39度，医生补充记录"
            assert persisted["status"] == "partial"
            # The editor clears client evidence, but normal saves retain the
            # immediately previous server quotes for comparison only. Manual
            # provenance must not become automatic evidence or confirmation.
            assert persisted["source_spans"] == original_source_spans
            assert persisted["doctor_review_note"].startswith("manual_doctor_edit_v1:")
            assert persisted["confirmed_by_doctor"] is False
            assert persisted["doctor_review_status"] == "pending"
            assert persisted["confidence"] is None
            with closing(sqlite3.connect(database_uri, uri=True)) as connection:
                assert connection.execute(
                    "SELECT * FROM record_revision WHERE id = ?", (revision_before,)
                ).fetchone() == original_revision
            expect(page.locator('[data-field="chief_complaint"] .doctor-edit-origin')).to_have_text("医生已修改")

            page.click('[data-field="chief_complaint"] [data-knowledge-field="chief_complaint"]')
            page.wait_for_function(
                "window.__MRA_APP_STATE__.fieldKnowledgeSearch.chief_complaint?.status === 'ready'",
                timeout=15000,
            )
            detail = page.locator("#detailDrawerContent")
            expect(detail).to_contain_text("发热病历记录规范")
            expect(detail).to_contain_text("alpha33-test-v1")
            expect(detail).to_contain_text(document_id)
            expect(detail).to_contain_text("内容校验值（SHA256）")
            expect(detail.locator('a[href^="https://www.nhc.gov.cn/"]')).to_have_count(1)
            expect(detail.get_by_role("note")).to_have_text(DEFAULT_DISCLAIMER)
            expect(detail.get_by_role("region", name="本次检索与来源")).to_contain_text("1 份资料")
            expect(detail.get_by_text("选择来源核对原文", exact=False)).to_have_count(0)

            # Two passages in one version share an original; a new version is a second source.
            original = {"document_id": "record-rule", "version": "2024", "title": "文书示例",
                        "source_url": "https://example.org/2024"}
            revised = {**original, "version": "2025", "source_url": "https://example.org/2025"}
            page.click("#closeDrawerButton")
            page.route("**/api/knowledge/retrieve", lambda route: route.fulfill(
                json={"results": [original, {**original, "section": "第二章"}, revised]}))
            page.locator('[data-knowledge-field="chief_complaint"]').first.press("Enter")
            directory = detail.get_by_role("region", name="本次检索与来源")
            expect(directory).to_contain_text("3 个片段，来自 2 份资料")
            directory.locator("summary").press("Enter")
            expect(directory.get_by_role("link")).to_have_text(["文书示例 · 2024", "文书示例 · 2025"])
            expect(directory.get_by_role("link").last).to_have_attribute("href", revised["source_url"])
            page.unroute("**/api/knowledge/retrieve")

            page.click("#closeDrawerButton")
            page.route("**/api/knowledge/retrieve", lambda route: route.fulfill(
                json={"results": [original, {"title": "旧资料"}]}))
            page.locator('[data-knowledge-field="chief_complaint"]').first.press("Enter")
            expect(directory).to_contain_text("2 个片段")
            expect(directory).to_contain_text("部分片段缺少文档标识或版本，无法核定资料总数")
            expect(directory.locator("details")).to_have_count(0)
            page.unroute("**/api/knowledge/retrieve")

            # Older responses can omit the notice, and a source-specific notice
            # can include literal angle brackets. Both must survive an empty result.
            for response, expected_notice in (
                ({"results": [], "disclaimer": "请核验来源 <测试>。"}, "请核验来源 <测试>。"),
                ({"results": []}, DEFAULT_DISCLAIMER),
            ):
                page.click("#closeDrawerButton")
                page.route("**/api/knowledge/retrieve", lambda route: route.fulfill(json=response))
                page.locator('[data-knowledge-field="chief_complaint"]').first.press("Enter")
                expect(detail.get_by_role("note")).to_have_text(expected_notice)
                expect(detail).to_contain_text("没有找到")
                page.unroute("**/api/knowledge/retrieve")
            browser.close()
    finally:
        server.close()


@pytest.mark.parametrize("receipt", ["original", "unavailable", "newer"])
def test_stale_revision_keeps_local_edit_until_doctor_loads_latest(receipt: str) -> None:
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

            saved_chief = "另一窗口已保存 <span>核对</span>" if receipt == "newer" else None
            page.evaluate(
                """async (savedChief) => {
                  const taskId = window.__MRA_APP_STATE__.currentTaskId;
                  const task = await fetch(`/api/tasks/${taskId}`).then((response) => response.json());
                  const readiness = await fetch(`/api/tasks/${taskId}/export-readiness`).then((response) => response.json());
                  if (savedChief) task.result_json.fields.chief_complaint.value = savedChief;
                  await api(`/api/tasks/${taskId}/review`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                      fields: task.result_json.fields,
                      expected_revision_id: readiness.revision_id,
                      expected_content_hash: readiness.content_hash
                    })
                  });
                }""",
                saved_chief,
            )
            if receipt == "unavailable":
                page.route("**/export-readiness", lambda route: route.fulfill(status=503))
                assert page.evaluate("refreshExportReadiness()") is None
                page.unroute("**/export-readiness")
            elif receipt == "newer":
                page.evaluate("refreshExportReadiness()")
            page.click("#saveDraftButton")
            expect(page.locator(".record-edit-notice.conflict")).to_be_visible(timeout=15000)
            expect(page.locator('[data-record-field-input="chief_complaint"]')).to_have_value("本地尚未保存的医生修改")
            expect(page.locator("[data-record-reload-latest]")).to_be_visible()

            # Fail after the task response has arrived: the whole edit snapshot
            # must survive, including the old revision used for conflict checks.
            page.route("**/export-readiness", lambda route: route.abort())
            page.click("[data-record-reload-latest]")
            expect(page.locator(".record-version")).to_contain_text("加载失败", timeout=15000)
            expect(page.locator('[data-record-field-input="chief_complaint"]')).to_have_value("本地尚未保存的医生修改")
            expect(page.locator(".record-edit-notice.conflict")).to_be_visible()
            page.unroute("**/export-readiness")
            page.click("[data-record-reload-latest]")
            page.wait_for_function("!window.__MRA_APP_STATE__.recordEditMode", timeout=15000)
            expect(page.locator("[data-record-field-input]")).to_have_count(0)
            page.locator(".record-recovery summary").click()
            recovery = page.locator(".record-recovery")
            expect(recovery).to_contain_text("本地尚未保存的医生修改")
            if saved_chief:
                expect(recovery.locator("dt")).to_have_text(["最新已存", "本地未保存"])
                expect(recovery.locator("dd")).to_have_text([saved_chief, "本地尚未保存的医生修改"])
                expect(recovery.locator("dd span")).to_have_count(0)
            else:
                expect(recovery.locator("dt")).to_have_count(0)
            page.click("[data-record-reapply]")
            expect(page.locator('[data-record-field-input="chief_complaint"]')).to_have_value("本地尚未保存的医生修改")
            expect(page.locator("#confirmFieldsButton")).to_be_disabled()
            page.click("#saveDraftButton")
            page.wait_for_function("!window.__MRA_APP_STATE__.recordEditMode", timeout=15000)
            expect(page.locator(".record-version")).to_contain_text("修改已保存")
            expect(page.locator(".record-recovery")).to_have_count(0)
            browser.close()
    finally:
        server.close()


def test_field_edit_focus_save_failure_and_completed_review_disclosure() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            page.click('[data-record-edit-field="past_history"]')
            editor = page.locator('[data-record-field-input="past_history"]')
            expect(editor).to_be_focused()
            editor.fill("医生待保存修改 <script>不可执行</script>")
            # Focusing another field must not reset the first edited value.
            page.evaluate("beginRecordEdit('allergy_history')")
            expect(editor).to_have_value("医生待保存修改 <script>不可执行</script>")
            page.route("**/review", lambda route: route.fulfill(status=503, json={"detail": "暂时不可用"}))
            page.click("#saveDraftButton")
            expect(page.locator(".record-version")).to_contain_text("保存失败", timeout=15000)
            expect(editor).to_have_value("医生待保存修改 <script>不可执行</script>")
            expect(page.locator("#recordFields script")).to_have_count(0)
            page.unroute("**/review")
            page.click("#cancelRecordEditButton")
            if not page.locator(".approval-disclosure").get_attribute("open") == "":
                page.locator(".approval-disclosure > summary").click()
            page.click("[data-approval-confirm-regular]")
            expect(page.locator(".review-completed")).not_to_have_attribute("open", "")
            expect(page.locator("[data-approval-confirm-regular]")).not_to_be_visible()
            page.locator(".review-completed summary").click()
            expect(page.locator("[data-approval-confirm-regular]")).to_be_visible()
            browser.close()
    finally:
        server.close()


@pytest.mark.parametrize("local_value", ["读取失败后的本地追加内容", ""], ids=["append", "clear"])
def test_committed_save_with_failed_refresh_requires_verification_not_resubmit(local_value) -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            _login(page, server.base_url)
            task_id = _prepare_review_fixture(page)
            page.click('[data-record-edit-field="past_history"]')
            editor = page.locator('[data-record-field-input="past_history"]')
            editor.fill("医生确认既往史本次未详细采集")
            posted_reviews = []
            page.on("request", lambda request: posted_reviews.append(request.url)
                    if request.method == "POST" and request.url.endswith("/review") else None)
            page.route("**/export-readiness", lambda route: route.abort())
            page.click("#saveDraftButton")
            expect(page.locator(".record-version")).to_contain_text("服务器已接受保存", timeout=15000)
            expect(page.locator("#saveDraftButton")).to_be_disabled()
            expect(editor).to_be_editable()
            editor.fill(local_value)
            # A passive same-task refresh can complete after the doctor resumes typing.
            await_read = "async () => {await refreshTask(appState.currentTaskId); return appState.currentRecordFields.past_history.value}"
            assert (page.evaluate(await_read) or "") == local_value
            expect(editor).to_have_value(local_value)
            expect(page.locator("#saveDraftButton")).to_be_disabled()
            expect(page.locator("#cancelRecordEditButton")).to_be_disabled()
            page.unroute("**/export-readiness")
            page.click("[data-record-reload-latest]")
            page.wait_for_function("!appState.recordEditMode", timeout=15000)
            persisted = page.evaluate("async id => (await api(`/api/tasks/${id}`)).result_json.fields.past_history.value", task_id)
            assert persisted == "医生确认既往史本次未详细采集"
            page.locator(".record-recovery summary").click()
            expect(page.locator(".record-recovery")).to_contain_text(local_value or "（留空）")
            page.locator("[data-record-reapply]").click()
            expect(editor).to_be_editable()
            expect(editor).to_have_value(local_value)
            assert len(posted_reviews) == 1
            browser.close()
    finally:
        server.close()
