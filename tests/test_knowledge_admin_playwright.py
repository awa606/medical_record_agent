from __future__ import annotations

import re
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from tests.test_browser_recording_playwright import RunningServer, _login


def test_readiness_503_uses_chinese_summary_and_keeps_raw_detail_collapsed() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/ready", lambda route: route.fulfill(status=503, json={
                "status": "not_ready", "checks": {
                    "asr_models": {"ok": False, "status": "warming", "error": "FunASR model prewarm has not completed"},
                    "provider": {"ok": True, "status": {"provider": "ollama", "mode": "edge"}},
                }}))
            _login(page, server.base_url)
            page.click('[data-product-view-target="admin"]')
            panel = page.locator("#adminRuntimePanel")
            expect(panel).to_contain_text("语音转写模型预热中")
            expect(panel).to_contain_text("本地模型服务（ollama）")
            expect(panel.locator("pre")).not_to_be_visible()
            panel.locator("summary").click()
            expect(panel.locator("pre")).to_be_visible()
            expect(panel.locator("pre")).to_contain_text("FunASR model prewarm has not completed")
            browser.close()
    finally:
        server.close()


def test_admin_import_test_search_and_enable_use_live_api() -> None:
    server = RunningServer()
    try:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "record-standard.md"
            source.write_text(
                "# 基本要求\n病历书写应当客观、真实、准确、及时、完整、规范。",
                encoding="utf-8",
            )
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                _login(page, server.base_url)
                page.click('[data-product-view-target="admin"]')
                expect(page.locator("#adminHome")).to_be_visible()

                expect(page.locator("#knowledgeImportForm")).not_to_be_visible()
                page.click("#openKnowledgeImportButton")
                page.fill("#knowledgeSourceId", "nhc-record-ui")
                page.fill("#knowledgeTitle", "病历书写规范浏览器测试")
                page.fill("#knowledgePublisher", "国家卫生健康委员会")
                page.fill("#knowledgeVersion", "ui-v1")
                page.select_option("#knowledgeDocumentType", "record-standard")
                page.fill("#knowledgeDiseaseScope", "通用病历书写")
                page.fill("#knowledgeSourceUrl", "https://www.nhc.gov.cn/example")
                page.locator("#knowledgeFileInput").set_input_files(str(source))
                page.click('#knowledgeImportForm button[type="submit"]')

                row = page.locator('[data-knowledge-document*="nhc-record-ui"]')
                expect(row).to_be_visible()
                expect(row).to_contain_text("停用")
                row.locator('[data-knowledge-action="detail"]').click()
                expect(page.locator("#knowledgeDetailDialog")).to_contain_text("使用 / 索引范围")
                page.keyboard.press("Escape")
                expect(row.locator('[data-knowledge-action="detail"]')).to_be_focused()

                row.locator('[data-knowledge-action="edit"]').click()
                expect(page.locator("#knowledgeDetailDialog")).to_contain_text("同来源的所有版本")
                page.fill("#knowledgeEditScope", "通用病历书写，工程演示")
                page.route("**/api/knowledge/admin/documents/*", lambda route: route.fulfill(
                    status=503, content_type="application/json", body='{"detail":"save unavailable"}'
                ) if route.request.method == "PATCH" else route.continue_())
                page.click('#knowledgeMetadataForm button[type="submit"]')
                expect(page.locator("#knowledgeMetadataError")).to_contain_text("save unavailable")
                expect(page.locator("#knowledgeEditScope")).to_have_value("通用病历书写，工程演示")
                page.unroute("**/api/knowledge/admin/documents/*")
                page.click('#knowledgeMetadataForm button[type="submit"]')
                expect(page.locator("#knowledgeDetailDialog")).not_to_be_visible()
                expect(row).to_contain_text("工程演示")
                page.fill("#knowledgeCatalogQuery", "不存在的资料")
                expect(page.locator("#adminKnowledgePanel")).to_contain_text("没有符合筛选")
                page.fill("#knowledgeCatalogQuery", "")
                page.select_option("#knowledgeCatalogStatus", "active")
                expect(page.locator("#adminKnowledgePanel")).to_contain_text("没有符合筛选")
                page.select_option("#knowledgeCatalogStatus", "")

                row.locator('[data-knowledge-action="test"]').click()
                page.fill("#knowledgeTestQuery", "客观真实准确")
                page.locator("#knowledgeTestDocument").select_option(index=1)
                page.click('#knowledgeTestSearchForm button[type="submit"]')
                expect(page.locator("#adminKnowledgeSearchResult")).to_contain_text("测试搜索")
                expect(page.locator("#adminKnowledgeSearchResult")).to_contain_text("病历书写规范浏览器测试")
                expect(page.locator("#adminKnowledgeSearchResult")).to_contain_text("第 1 页")
                expect(page.locator(".knowledge-passage")).to_contain_text("客观、真实、准确")
                expect(page.locator("#adminKnowledgeSearchResult")).to_contain_text("指定版本，仅管理员验证")
                expect(page.locator("#adminKnowledgeSearchResult a")).to_have_attribute("href", "https://www.nhc.gov.cn/example")
                page.select_option("#knowledgeTestDocument", "")
                page.click('#knowledgeTestSearchForm button[type="submit"]')
                expect(page.locator("#adminKnowledgeSearchResult")).to_contain_text("未命中资料")

                page.click("#knowledgeTabCatalog")
                row.locator('[data-knowledge-action="enable"]').click()
                expect(page.locator('[data-knowledge-document*="nhc-record-ui"]')).to_contain_text(
                    re.compile("已启用")
                )
                page.click("#knowledgeTabSearch")
                page.click('#knowledgeTestSearchForm button[type="submit"]')
                expect(page.locator("#adminKnowledgeSearchResult")).to_contain_text("当前医生检索范围")
                expect(page.locator("#adminKnowledgeSearchResult")).to_contain_text("病历书写规范浏览器测试")
                page.locator("#knowledgeTabSearch").focus()
                page.keyboard.press("ArrowRight")
                expect(page.locator("#knowledgeTabHealth")).to_be_focused()
                expect(page.locator("#knowledgeHealthSummary")).to_contain_text("最近一次查询模式")
                page.keyboard.press("Home")
                expect(page.locator("#knowledgeTabCatalog")).to_be_focused()
                result = page.evaluate(
                    """
                    async () => api('/api/knowledge/retrieve', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ query: '客观真实准确' }),
                    })
                    """
                )
                assert result["count"] >= 1
                assert result["results"][0]["publisher"] == "国家卫生健康委员会"
                browser.close()
    finally:
        server.close()


def test_knowledge_catalog_errors_and_safe_dialogs() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            _login(page, server.base_url)
            page.click('[data-product-view-target="admin"]')
            expect(page.locator("#adminKnowledgePanel")).to_contain_text("尚未导入")
            page.route("**/api/knowledge/admin/documents", lambda route: route.fulfill(
                status=503, content_type="application/json", body='{"detail":"catalog offline"}'
            ))
            page.click("#refreshAdminHomeButton")
            expect(page.locator("#adminKnowledgePanel")).to_contain_text("知识服务不可用")
            expect(page.locator("#adminKnowledgePanel")).not_to_contain_text("尚未导入")
            page.unroute("**/api/knowledge/admin/documents")
            page.route("**/api/knowledge/retrieve", lambda route: route.fulfill(
                status=503, content_type="application/json", body='{"detail":"search offline"}'
            ))
            page.click("#knowledgeTabSearch")
            page.fill("#knowledgeTestQuery", "发热")
            page.click('#knowledgeTestSearchForm button[type="submit"]')
            expect(page.locator("#adminKnowledgeSearchResult")).to_contain_text("检索失败")
            expect(page.locator("#adminKnowledgeSearchResult")).not_to_contain_text("未命中资料")
            page.click("#openKnowledgeImportButton")
            page.fill("#knowledgeTitle", "保留未提交输入")
            page.keyboard.press("Escape")
            expect(page.locator("#openKnowledgeImportButton")).to_be_focused()
            page.click("#openKnowledgeImportButton")
            expect(page.locator("#knowledgeTitle")).to_have_value("保留未提交输入")
            for width, height in [(1366, 768), (1440, 900), (1920, 1080)]:
                page.set_viewport_size({"width": width, "height": height})
                box = page.locator("#knowledgeImportDialog").bounding_box()
                assert box and box["x"] >= 0 and box["x"] + box["width"] <= width
                assert box["y"] >= 0 and box["y"] + box["height"] <= height
            browser.close()
    finally:
        server.close()
