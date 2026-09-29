"""Real HTTP/browser workflow regression; fixture LLM, not model-quality evidence."""
import json

from playwright.sync_api import expect, sync_playwright

from tests.auth_helpers import DEFAULT_ADMIN_PASSWORD
from tests.test_doctor_itemized_approval_playwright import RunningServer


def test_independent_cookie_new_patients_repeat_visit_and_source_reopen():
    demo = RunningServer({"MEDICAL_RECORD_AGENT_SESSION_COOKIE_NAME": "mra_showcase_test"})
    test = RunningServer({"MEDICAL_RECORD_AGENT_SESSION_COOKIE_NAME": "mra_usage_test"})
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context()
            context.route("**/static/deployment.json", lambda route: route.fulfill(json={
                "mode": "test" if route.request.url.startswith(test.base_url) else "showcase",
                "label": "使用测试版" if route.request.url.startswith(test.base_url) else "展示版", "version": "test-sha"}))
            page = context.new_page()
            for server in (demo, test):
                page.goto(server.base_url + "/static/doctor.html")
                page.fill("#loginUsername", "admin")
                page.fill("#loginPassword", DEFAULT_ADMIN_PASSWORD)
                page.locator("#loginForm button[type=submit]").click()
                expect(page.locator("#authUserLabel")).to_contain_text("admin")
            cookies = {item["name"] for item in context.cookies()}
            assert {"mra_showcase_test", "mra_usage_test"}.issubset(cookies)
            for _ in range(2):
                page.select_option("#localSyntheticPatient", "__new__")
                page.click("#createLocalEncounterButton")
                expect(page.locator("#workbenchSelectionNotice")).to_contain_text("报到完成")
                expect(page.locator("#createLocalEncounterButton")).to_be_enabled()
            records = context.request.get(test.base_url + "/api/encounters").json()["encounters"]
            assert len(records) == 2
            assert len({record["patient_id"] for record in records}) == 2
            first = records[0]
            page.select_option("#localSyntheticPatient", first["patient_deidentified_id"])
            page.click("#createLocalEncounterButton")
            expect(page.locator("#createLocalEncounterButton")).to_be_enabled()
            rows = context.request.get(test.base_url + "/api/encounters").json()["encounters"]
            assert len(rows) == 3 and len({row["patient_id"] for row in rows}) == 2
            assert context.request.get(demo.base_url + "/api/encounters").json()["encounters"] == []
            latest = max(rows, key=lambda row: row["id"])
            page.locator(f'#dashboardEncounterList [data-encounter-id="{latest["id"]}"][data-encounter-action="start"]').click()
            page.locator('#encounterView [data-input-method="text"]').click()
            source = "患者发热38.2度，伴咳嗽两天，没有胸痛，没有药物过敏史。"
            page.fill("#conversationInput", source)
            page.click("#submitTextButton")
            expect(page.locator("#editRecordButton")).to_be_enabled(timeout=30000)
            page.locator('[data-product-view-target="workbench"]').first.click()
            page.locator(f'#dashboardEncounterList [data-restore-encounter="{latest["id"]}"]').click()
            expect(page.locator("#transcriptHeading")).to_have_text("输入原文")
            expect(page.locator("#transcriptList")).to_contain_text("38.2")
            expect(page.locator(".approval-disclosure summary")).to_contain_text("医生分项审核")
            page.click("#logoutButton")
            assert context.request.get(demo.base_url + "/api/auth/me").status == 200
            assert context.request.get(test.base_url + "/api/auth/me").status == 401
            browser.close()
    finally:
        test.close()
        demo.close()
