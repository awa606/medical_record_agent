from __future__ import annotations

import re
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from tests.test_browser_recording_playwright import RunningServer, _login


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

                page.fill("#knowledgeSourceId", "nhc-record-ui")
                page.fill("#knowledgeTitle", "病历书写规范浏览器测试")
                page.fill("#knowledgePublisher", "国家卫生健康委员会")
                page.fill("#knowledgeVersion", "ui-v1")
                page.fill("#knowledgeDocumentType", "record-standard")
                page.fill("#knowledgeDiseaseScope", "通用病历书写")
                page.fill("#knowledgeSourceUrl", "https://www.nhc.gov.cn/example")
                page.locator("#knowledgeFileInput").set_input_files(str(source))
                page.click('#knowledgeImportForm button[type="submit"]')

                row = page.locator('[data-knowledge-document*="nhc-record-ui"]')
                expect(row).to_be_visible()
                expect(row).to_contain_text("停用")

                page.fill("#knowledgeTestQuery", "客观真实准确")
                page.locator("#knowledgeTestDocument").select_option(index=1)
                page.click('#knowledgeTestSearchForm button[type="submit"]')
                expect(page.locator("#adminKnowledgeSearchResult")).to_contain_text("测试搜索")
                expect(page.locator("#adminKnowledgeSearchResult")).to_contain_text("病历书写规范浏览器测试")

                row.locator('[data-knowledge-action="enable"]').click()
                expect(page.locator('[data-knowledge-document*="nhc-record-ui"]')).to_contain_text(
                    re.compile("已启用")
                )
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
