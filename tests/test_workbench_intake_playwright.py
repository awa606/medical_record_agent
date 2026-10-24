"""Visible intake actions against a real isolated API; mock LLM, no ASR claims."""
import json
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


def test_check_in_retry_preserves_one_registration_and_unknown_identity():
    server = RunningServer()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            intake_events = []

            def record_intake_event(kind, request, status=None):
                parsed = urlsplit(request.url)
                if (parsed.netloc == urlsplit(server.base_url).netloc
                        and parsed.path.startswith("/api/encounters")):
                    intake_events.append({"event": kind, "method": request.method,
                                          "path": parsed.path, "status": status})

            # Keep only request metadata: never credentials, headers or bodies.
            page.on("request", lambda request: record_intake_event("request", request))
            page.on("response", lambda response: record_intake_event(
                "response", response.request, response.status))
            page.on("requestfailed", lambda request: record_intake_event("failed", request))
            _login(page, server.base_url)
            # Failed check-in is explicit fault injection, not a fake success.
            page.route("**/api/encounters/*/check-in", lambda route: route.fulfill(
                status=503, content_type="application/json", body=json.dumps({"detail":"test check-in outage"})), times=1)
            if not page.locator("#localSyntheticPatient").is_visible():
                page.locator("#localRegistrationDisclosure summary").click()
            page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-NEGATION")
            expect(page.locator("#localSyntheticPatient")).to_have_value("SIM-DEMO-0929-NEGATION")
            try:
                # Login also refreshes the list. Observe the actual registration
                # and injected failure, not an unrelated GET racing this action.
                with page.expect_response(lambda response:
                                          urlsplit(response.url).path == "/api/encounters"
                                          and response.request.method == "POST", timeout=30000) as registered:
                    with page.expect_response(lambda response:
                                              urlsplit(response.url).path.startswith("/api/encounters/")
                                              and urlsplit(response.url).path.endswith("/check-in")
                                              and response.request.method == "POST", timeout=30000) as check_in:
                        page.click("#createLocalEncounterButton")
                assert registered.value.ok
                encounter_id = registered.value.json()["id"]
                assert urlsplit(check_in.value.url).path == f"/api/encounters/{encounter_id}/check-in"
                assert check_in.value.status == 503
            except Exception:
                print(json.dumps({"phase": "registration_and_injected_check_in_failure",
                                  "intake_events": intake_events[-20:]}, ensure_ascii=False))
                raise
            row = page.locator("#dashboardEncounterList article").filter(has_text="李示例")
            expect(row).to_contain_text("已登记", timeout=15000)
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
