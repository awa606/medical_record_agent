"""Visible intake actions against a real isolated API; mock LLM, no ASR claims."""
import json
from playwright.sync_api import sync_playwright, expect
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


def test_check_in_retry_preserves_one_registration_and_unknown_identity():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)
            # Failed check-in is explicit fault injection, not a fake success.
            page.route("**/api/encounters/*/check-in", lambda route: route.fulfill(
                status=503, content_type="application/json", body=json.dumps({"detail":"test check-in outage"})), times=1)
            page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-NEGATION")
            page.click("#createLocalEncounterButton")
            row = page.locator("#dashboardEncounterList article").filter(has_text="李示例")
            expect(row).to_contain_text("已登记")
            expect(page.locator("#workbenchSelectionNotice")).to_contain_text("登记已保存")
            expect(page.locator("#localSyntheticPatient")).to_be_disabled()
            assert page.request.get(server.base_url + "/api/encounters?mine=false").json()["encounters"].__len__() == 1
            row.get_by_role("button", name="报到", exact=True).click()
            expect(row).to_contain_text("已报到")
            expect(page.locator("#localSyntheticPatient")).to_be_enabled()
            expect(page.locator("#createLocalEncounterButton")).to_have_text("登记并报到")
            expect(page.locator("body")).to_have_attribute("data-product-view", "workbench")
            assert len(page.request.get(server.base_url + "/api/encounters?mine=false").json()["encounters"]) == 1
            row.get_by_role("button", name="开始接诊", exact=True).click()
            expect(page.locator("#patientName")).to_have_text("李示例")
            page.locator('[data-product-view-target="workbench"]').first.click()
            page.click("#createLocalEncounterButton")
            expect(page.locator("#dashboardEncounterList article").filter(has_text="李示例")).to_have_count(2)
            response = page.request.post(server.base_url + "/api/encounters", data={
                "patient_deidentified_id":"SIM-UNLISTED", "patient_display_name":"身份绝不显示"})
            assert response.ok
            page.click("#refreshWorklistButton")
            unknown = page.locator("#dashboardEncounterList article").filter(has_text="SIM-UNLISTED")
            expect(unknown).to_contain_text("脱敏患者")
            expect(unknown).not_to_contain_text("身份绝不显示")
            page.fill("#encounterSearchInput", "李示例")
            page.click("#refreshWorklistButton")
            expect(page.locator("#dashboardEncounterList article")).to_have_count(2)
            browser.close()
    finally:
        server.close()


def test_empty_workspace_returns_to_workbench_instead_of_intake_drawer():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)
            page.locator('[data-product-view-target="encounter"]').first.click()
            expect(page.locator("body")).to_have_attribute("data-product-view", "workbench")
            expect(page.locator("#workbenchSelectionNotice")).to_contain_text("开始接诊")
            assert page.locator("#encounterWorklistPanel").count() == 0
            browser.close()
    finally:
        server.close()
