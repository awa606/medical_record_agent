from __future__ import annotations

from contextlib import closing
import secrets
import sqlite3

import pytest
from playwright.sync_api import expect, sync_playwright

from app.services.knowledge_store import DEFAULT_DISCLAIMER
from tests.approval_helpers import approval_payload_for_fields
from tests.test_doctor_itemized_approval_playwright import (
    RunningServer,
    _login,
    _prepare_review_fixture,
)
from tests.test_transcript_source_presentation_playwright import _open_from_workbench


def test_field_actions_include_their_visible_heading_in_the_accessible_name() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright, playwright.chromium.launch() as browser:
            page = browser.new_page()
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            for width, height in [(1366, 900), (390, 844), (320, 640)]:
                page.set_viewport_size({"width": width, "height": height})
                fields = page.locator("#recordFields .field-card[data-field]:visible")
                assert fields.count() > 1
                for field in fields.all():
                    heading = field.locator(".field-title").inner_text()
                    for button in field.locator(".compact-field-meta button:visible").all():
                        label = button.inner_text()
                        name = f"{label} {heading}"
                        expect(button).to_have_accessible_name(name)
                        expect(page.get_by_role("button", name=name, exact=True)).to_have_count(1)
                expect(page.get_by_role("button", name="查知识资料 主诉", exact=True)).to_have_text("查知识资料")
    finally:
        server.close()


def test_clinician_assessment_is_versioned_and_preserves_concurrent_text() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright, playwright.chromium.launch() as browser:
            page = browser.new_page()
            _login(page, server.base_url)
            password = secrets.token_urlsafe(24)
            api = lambda path: server.base_url + "/api" + path
            credentials = {"username": "assessment-doctor", "password": password}
            assert page.request.post(api("/auth/users"), data={**credentials, "role": "doctor", "display_name": "演练记录医生"}).ok
            assert page.request.post(api("/auth/logout")).ok
            assert page.request.post(api("/auth/login"), data=credentials).ok
            encounter = page.request.post(api("/encounters"), data={"patient_deidentified_id": "SYN-ASSESSMENT"}).json()["id"]
            for action in ("check-in", "start"):
                assert page.request.post(api(f"/encounters/{encounter}/{action}"), data={}).ok
            task = page.request.post(api("/records/generate"), data={"encounter_id": encounter, "conversation_text": "患者：最近两天偶尔咳嗽。"}).json()["task_id"]
            page.reload()
            page.wait_for_function("async p => (await fetch(p).then(r => r.json())).status === 'WAITING_DOCTOR_REVIEW'", arg=api(f"/tasks/{task}"))
            _open_from_workbench(page, encounter)
            card = page.get_by_role("article", name="本次医生评估（手录）")
            edit = card.get_by_role("button", name="编辑本次医生评估")
            expect(card).to_contain_text("未填写")
            edit.click()
            card.get_by_label("评估原文").fill("取消时应保留未填写")
            page.locator("#cancelRecordEditButton").click()
            expect(card).to_contain_text("未填写")
            edit.click()
            card.get_by_label("评估原文").fill("由本人记录的判断")
            card.get_by_label("记录状态").select_option("under_consideration")
            with page.expect_response(lambda r: r.url == api(f"/tasks/{task}/review") and r.request.method == "POST") as first:
                page.locator("#saveDraftButton").click()
            assert first.value.ok
            request = first.value.request.post_data_json
            assert request["clinician_assessment"] == {"statement": "由本人记录的判断", "certainty": "under_consideration"}
            assert "clinician_assessment" not in request["fields"]
            expect(card).to_contain_text("待排 · 由本人记录的判断")
            expect(card).to_contain_text("演练记录医生")
            page.locator('[data-open-detail="history:record"]').click()
            page.locator("[data-history-version]").select_option(index=1)
            history = page.locator("[data-history-assessment]")
            expect(history).to_contain_text("未填写")
            expect(history).to_contain_text("待排 · 由本人记录的判断")
            page.locator("#closeDrawerButton").click()

            stored_fields = page.request.get(api(f"/tasks/{task}")).json()["result_json"]["fields"]
            signed_version = page.request.get(api(f"/tasks/{task}/export-readiness")).json()
            approval = approval_payload_for_fields(stored_fields)
            approval.update(revision_id=signed_version["revision_id"], content_hash=signed_version["content_hash"])
            for item in approval["fields"]:
                field = stored_fields[item["key"]]
                item["action"] = "confirm_content" if field["value"] and not field["missing"] else "confirm_not_asked"
            for item in approval["diagnoses"]:
                item["action"] = "delete_ai_candidate"
            signed = page.request.post(api(f"/tasks/{task}/approve"), data=approval)
            assert signed.ok, signed.text()
            _open_from_workbench(page, encounter)
            expect(page.locator("#fieldCountBadge")).to_have_text("已审核")
            expect(card).to_contain_text("待排 · 由本人记录的判断")

            edit.click()
            card.get_by_label("评估原文").fill("这个标签页的未保存原文")
            detail = page.request.get(api(f"/tasks/{task}")).json()
            receipt = page.request.get(api(f"/tasks/{task}/export-readiness")).json()
            assert page.request.post(api(f"/tasks/{task}/review"), data={
                "fields": detail["result_json"]["fields"], "expected_revision_id": receipt["revision_id"],
                "expected_content_hash": receipt["content_hash"],
                "clinician_assessment": {"statement": "另一处已经保存的原文", "certainty": "documented"},
            }).ok
            page.locator("#saveDraftButton").click()
            page.get_by_role("button", name="加载最新版本").click()
            fold = page.locator("details.record-recovery")
            fold.locator("summary").click()
            expect(fold).to_contain_text("这个标签页的未保存原文")
            expect(fold).to_contain_text("另一处已经保存的原文")
            fold.locator("button").click()
            expect(card.get_by_label("评估原文")).to_have_value("另一处已经保存的原文")
            expect(fold).to_contain_text("这个标签页的未保存原文")
            card.get_by_role("button", name="清除本次手录").click()
            with page.expect_response(lambda r: r.url == api(f"/tasks/{task}/review") and r.request.method == "POST") as cleared:
                page.locator("#saveDraftButton").click()
            assert cleared.value.ok and cleared.value.request.post_data_json["clinician_assessment"] is None
            expect(card).to_contain_text("未填写")

            # Simulate a server downgrade between opening the editor and saving. A legacy
            # review accepts unrelated fields while dropping this new top-level property.
            def legacy_review(route):
                body = route.request.post_data_json
                del body["clinician_assessment"]
                response = route.fetch(post_data=body)
                assert response.ok
                task_data = response.json()
                task_data.pop("supports_clinician_assessment")
                route.fulfill(response=response, json=task_data)

            page.route(api(f"/tasks/{task}/review"), legacy_review)
            edit.click()
            card.get_by_label("记录状态").select_option("documented")
            card.get_by_label("评估原文").fill("旧服务未保存这一句")
            page.locator("#saveDraftButton").click()
            expect(page.locator(".record-version")).to_contain_text("医生评估未核实保存")
            expect(card.get_by_label("评估原文")).to_have_value("旧服务未保存这一句")
            expect(page.locator("#saveDraftButton")).to_be_disabled()
            assert not page.request.get(api(f"/tasks/{task}")).json()["result_json"].get("clinician_assessment")
    finally:
        server.close()


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
            chief = page.locator('[data-field="chief_complaint"]')
            original_chief = editor.input_value()
            expect(chief.get_by_role("button", name="查看上版引文 主诉", exact=True)).to_be_visible()
            editor.fill("患者发热39度，医生补充记录")
            expect(chief.get_by_role("button", name="查看字段记录 主诉", exact=True)).to_be_visible()
            expect(editor).to_be_focused()
            editor.fill(original_chief)
            expect(chief.get_by_role("button", name="查看上版引文 主诉", exact=True)).to_be_visible()
            editor.fill("患者发热39度，医生补充记录")
            with page.expect_response(lambda response: response.url.endswith("/api/knowledge/retrieve")) as lookup:
                chief.get_by_role("button", name="查知识资料 主诉", exact=True).press("Enter")
            assert lookup.value.ok
            assert lookup.value.request.post_data_json == {
                "task_id": task_id, "query": "主诉：患者发热39度，医生补充记录", "related_fields": ["chief_complaint"],
            }
            stored = page.request.get(server.base_url + f"/api/tasks/{task_id}").json()["result_json"]["fields"]
            assert stored["chief_complaint"]["value"] == original_chief
            page.click("#closeDrawerButton")
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
            expect(chief.get_by_role("button", name="查看上版引文 主诉", exact=True)).to_be_visible()

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
            expect(detail.get_by_role("region", name="本次检索与来源")).to_contain_text("支持程度尚未核实")
            expect(detail.get_by_text("仅用于自动化测试中的医生人工参考。", exact=True)).to_be_visible()
            expect(detail.get_by_role("link", name="打开登记来源（需联网）")).to_be_visible()
            expect(detail.get_by_text("选择来源核对原文", exact=False)).to_have_count(0)
            first_card = detail.locator(".detail-section").first
            expect(first_card.locator(".detail-kv").first).to_contain_text("章节 / 页码")
            expect(first_card.locator(".detail-kv + .detail-text")).to_be_visible()
            identifiers = first_card.locator("details").filter(has_text="文档编号与校验值")
            expect(identifiers.locator(".hash-value")).to_be_hidden()
            identifiers.locator("summary").press("Enter")
            expect(identifiers.locator(".hash-value")).to_be_visible()
            expect(identifiers).to_contain_text(document_id)
            identifiers.locator("summary").press("Space")
            expect(identifiers.locator(".hash-value")).to_be_hidden()

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
            expect(detail.get_by_text("登记用途", exact=True)).to_have_count(0)
            directory.locator("summary").press("Enter")
            expect(directory.get_by_role("link")).to_have_text(["文书示例 · 2024", "文书示例 · 2025"])
            expect(directory.get_by_role("link").last).to_have_attribute("href", revised["source_url"])
            partial_ids = detail.locator(".detail-section").first.locator("details")
            partial_ids.locator("summary").press("Enter")
            expect(partial_ids).to_contain_text("record-rule / 未登记")
            expect(partial_ids.locator(".hash-value")).to_have_text("未登记")
            page.unroute("**/api/knowledge/retrieve")

            page.click("#closeDrawerButton")
            page.route("**/api/knowledge/retrieve", lambda route: route.fulfill(
                json={"results": [original, {"title": "旧资料"}]}))
            page.locator('[data-knowledge-field="chief_complaint"]').first.press("Enter")
            expect(directory).to_contain_text("2 个片段")
            expect(directory).to_contain_text("部分片段缺少文档标识或版本，无法核定资料总数")
            expect(directory.locator("details")).to_have_count(0)
            legacy_card = detail.locator(".detail-section").last
            expect(legacy_card.get_by_text("此片段未登记文档编号、片段编号和校验值。")).to_be_visible()
            expect(legacy_card.locator("summary")).to_have_count(0)
            page.unroute("**/api/knowledge/retrieve")

            # Older responses can omit the notice, and a source-specific notice
            # can include literal angle brackets. Both must survive an empty result.
            page.click("#closeDrawerButton")
            for response, expected_notice in (
                ({"results": [], "disclaimer": "请核验来源 <测试>。"}, "请核验来源 <测试>。"),
                ({"results": []}, DEFAULT_DISCLAIMER),
            ):
                page.route("**/api/knowledge/retrieve", lambda route: route.fulfill(json=response))
                page.locator('[data-knowledge-field="chief_complaint"]').first.press("Enter")
                expect(detail.get_by_role("note")).to_have_text(expected_notice)
                expect(detail).to_contain_text("没有找到")
                detail.get_by_role("button", name="返回主诉继续核对").press("Enter")
                expect(chief.get_by_role("button", name="查知识资料")).to_be_focused()
                page.unroute("**/api/knowledge/retrieve")
            browser.close()
    finally:
        server.close()


@pytest.mark.parametrize("width,height", [(320, 640), (650, 500)])
def test_short_touch_viewport_can_open_record_fields_and_edit(width: int, height: int) -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height}, has_touch=True)
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            fields = page.locator("#recordFields")
            for key, title in [("chief_complaint", "主诉"), ("allergy_history", "过敏史")]:
                button = fields.locator(f'[data-knowledge-field="{key}"]')
                button.tap(timeout=5000)
                expect(page.locator("#drawerTitle")).to_have_text(f"查知识资料 · {title}")
                page.locator("#closeDrawerButton").tap()
                expect(button).to_be_focused()
            page.locator("#editRecordButton").tap()
            expect(fields.locator('[data-record-field-input="chief_complaint"]')).to_be_visible()
            page.locator("#cancelRecordEditButton").tap()
            expect(fields.locator("[data-record-field-input]")).to_have_count(0)
            browser.close()
    finally:
        server.close()


def test_scrolled_worklist_filter_accepts_touch_at_320() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 320, "height": 640}, has_touch=True)
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            page.locator("#openWorklistButton").tap()
            expect(page.locator("#encounterSearchInput")).to_be_focused()
            pending = page.locator('[data-dashboard-filter="pendingInput"]')
            pending.evaluate("el => window.scrollBy(0, el.getBoundingClientRect().top - 94)")
            box = pending.bounding_box()
            assert box is not None and 0 <= box["y"] < 120
            page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            expect(pending).to_have_attribute("aria-pressed", "true")
            browser.close()
    finally:
        server.close()


def test_field_lookup_returns_to_live_button_during_and_after_record_refresh() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            lookup = page.locator('[data-knowledge-field="allergy_history"]')
            with page.expect_response(lambda response: response.url.endswith("/knowledge/retrieve")):
                lookup.click()
            page.wait_for_function("appState.fieldKnowledgeSearch.allergy_history.status === 'ready'")
            # A same-visit refresh replaces the original button while the drawer is open.
            page.evaluate("renderFields()")
            page.keyboard.press("Escape")
            expect(lookup).to_be_focused()
            # A later refresh must leave the doctor's next keyboard action in the same field.
            page.evaluate("renderFields()")
            expect(lookup).to_be_focused()
            page.keyboard.press("Enter")
            expect(page.locator("#drawerTitle")).to_have_text("查知识资料 · 过敏史")
            browser.close()
    finally:
        server.close()


def test_field_search_retry_ignores_a_late_response_for_previous_edit() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            _login(page, server.base_url)
            _prepare_review_fixture(page)
            page.click("#editRecordButton")
            field = page.locator('#recordFields [data-field="chief_complaint"]')
            editor = field.locator('[data-record-field-input="chief_complaint"]')
            lookup = field.get_by_role("button", name="查知识资料")
            drawer = page.locator("#detailDrawerContent")
            held = []
            page.route("**/api/knowledge/retrieve", lambda route: held.append(route))

            def send(action):
                with page.expect_request(lambda req: req.url.endswith("/api/knowledge/retrieve")):
                    action.press("Enter")

            editor.fill("先前录入的主诉")
            send(lookup)
            page.keyboard.press("Escape")
            editor.fill("当前录入的主诉")
            send(lookup)
            held[1].fulfill(status=503, json={"detail": "资料服务暂时不可用"})
            expect(drawer.get_by_role("alert")).to_contain_text("资料服务暂时不可用")
            send(drawer.get_by_role("button", name="重新查询主诉资料"))
            assert [r.request.post_data_json["query"] for r in held] == [
                "主诉：先前录入的主诉", "主诉：当前录入的主诉", "主诉：当前录入的主诉",
            ]
            held[2].fulfill(json={"results": [{"title": "当前查询的资料", "excerpt": "当前字段摘录"}]})
            expect(drawer.get_by_text("当前字段摘录", exact=True)).to_be_visible()
            with page.expect_event("requestfinished", predicate=lambda req: req == held[0].request):
                held[0].fulfill(json={"results": [{"title": "旧查询的资料"}]})
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            expect(drawer.get_by_text("当前字段摘录", exact=True)).to_be_visible()
            assert page.evaluate("window.__MRA_APP_STATE__.fieldKnowledgeSearch.chief_complaint.results[0].title") == "当前查询的资料"
            page.keyboard.press("Escape")
            expect(lookup).to_be_focused()
            expect(editor).to_have_value("当前录入的主诉")
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
