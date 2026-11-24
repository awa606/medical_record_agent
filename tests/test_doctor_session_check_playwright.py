"""Check the doctor entry before authentication settles, then exercise its real next state."""
from secrets import token_urlsafe
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from app.db import create_encounter
from tests.auth_helpers import DEFAULT_ADMIN_PASSWORD
from tests.test_doctor_itemized_approval_playwright import RunningServer
from tests.test_doctor_workflow_state_contract_playwright import _server_database


@pytest.fixture(scope="module")
def doctor_links():
    server = RunningServer()
    password = token_urlsafe(20)
    try:
        with sync_playwright() as pw:
            admin = pw.request.new_context(base_url=server.base_url)
            assert admin.post("/api/auth/login", data={"username": "admin", "password": DEFAULT_ADMIN_PASSWORD}).ok
            account = admin.post("/api/auth/users", data={
                "username": "session-check", "password": password,
                "display_name": "合成医生", "role": "doctor",
            })
            assert account.status == 201
            owner = account.json()["id"]
            admin.dispose()
        with _server_database(server):
            visits = [
                create_encounter(doctor_user_id=owner, deidentified_id=f"SIM-CHECK-{i}",
                                 display_name=f"合成核对{i}", check_in_status="in_progress")["id"]
                for i in (1, 2)
            ]
        links = [f"{server.base_url}/static/doctor.html?encounter_id={visit}#encounter" for visit in visits]
        yield password, links
    finally:
        server.close()


def assert_locked(page):
    expect(page.locator("#loginPanel")).to_be_visible()
    expect(page.locator("#loginForm")).to_be_hidden()
    expect(page.locator("#loginForm button[type=submit]")).to_be_disabled()
    expect(page.locator(".doctor-app")).to_be_hidden()
    assert page.locator(".doctor-app").evaluate("node => node.hidden")
    assert "脱敏患者" not in page.locator("body").inner_text()


@pytest.mark.parametrize("width", [390, 1366])
def test_valid_session_never_prompts_again_on_second_encounter(doctor_links, width):
    password, links = doctor_links
    with sync_playwright() as pw, pw.chromium.launch() as browser:
        page = browser.new_page(viewport={"width": width, "height": 850})
        page.goto(links[0])
        username = page.locator("#loginUsername")
        expect(username).to_be_visible()
        page.keyboard.press("Tab")
        expect(username).to_be_focused()
        username.fill("session-check")
        page.keyboard.press("Tab")
        page.keyboard.insert_text(password)
        page.keyboard.press("Enter")
        expect(page.locator("#patientName")).to_have_text("脱敏患者 1")

        script, pending, api_requests = [], [], []
        page.route("**/doctor.js?*", lambda route: script.append(route), times=1)
        page.route("**/api/auth/me", lambda route: pending.append(route))
        page.on("request", lambda req: api_requests.append(urlsplit(req.url).path))
        with page.expect_request("**/doctor.js?*"):
            page.goto(links[1], wait_until="commit")
        assert_locked(page)
        expect(page.locator("#sessionCheckMessage")).to_contain_text("正在核对")
        with page.expect_request("**/api/auth/me"):
            script[0].continue_()
        assert_locked(page)
        expect(page.locator("#sessionCheckMessage")).to_contain_text("正在核对")
        expect(page.locator("#retrySessionCheck")).to_be_hidden()
        assert page.get_by_role("button").count() == 0
        page.keyboard.press("Tab")
        assert not page.locator(".doctor-app :focus, #loginForm :focus").count()
        assert not any(path.startswith(("/api/encounters", "/api/patients")) for path in api_requests)
        pending[0].continue_()
        expect(page.locator("#patientName")).to_have_text("脱敏患者 2")
        expect(page.locator("#loginPanel")).to_be_hidden()
        expect(username).to_be_hidden()


@pytest.mark.parametrize("failure", ["unreachable", "timeout", "server_error"])
def test_unconfirmed_session_recovers_by_keyboard(doctor_links, failure):
    _, links = doctor_links
    with sync_playwright() as pw, pw.chromium.launch() as browser:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        if failure == "unreachable":
            page.route("**/api/auth/me", lambda route: route.abort("internetdisconnected"), times=1)
        elif failure == "timeout":
            page.route("**/api/auth/me", lambda route: None, times=1)
        else:
            page.route("**/api/auth/me", lambda route: route.fulfill(status=503), times=1)
        page.goto(links[0], wait_until="domcontentloaded")
        retry = page.get_by_role("button", name="重新核对")
        expect(retry).to_be_visible(timeout=15000)
        expect(page.locator("#sessionCheckMessage")).to_contain_text("检查连接")
        assert_locked(page)
        assert page.get_by_role("button").count() == 1
        page.keyboard.press("Tab")
        expect(retry).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.locator("#loginUsername")).to_be_visible()
        expect(page.locator("#loginForm button[type=submit]")).to_be_enabled()
        assert page.url == links[0]




def open_doctor_visit(page, password, link):
    page.goto(link)
    page.locator("#loginUsername").fill("session-check")
    page.locator("#loginPassword").fill(password)
    page.locator("#loginPassword").press("Enter")
    expect(page.locator("#patientName")).to_have_text("脱敏患者 1")


@pytest.mark.parametrize("failure", ["server_error", "unreachable", "timeout"])
def test_unconfirmed_logout_stays_locked_until_server_confirms(doctor_links, failure):
    password, links = doctor_links
    with sync_playwright() as pw, pw.chromium.launch() as browser:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        open_doctor_visit(page, password, links[0])
        me = links[0].split("/static/")[0] + "/api/auth/me"
        assert page.request.get(me).status == 200
        stale, logout_posts = [], []
        logout_mode = "hold"

        def hold_requests(route):
            path = urlsplit(route.request.url).path
            if path == "/api/encounters" and not stale:
                stale.append(route)
            elif path == "/api/auth/logout" and logout_mode == "hold":
                logout_posts.append(route)
            elif path == "/api/auth/logout" and logout_mode == "503":
                route.fulfill(status=503)
            else:
                route.continue_()

        page.route("**/api/**", hold_requests)
        with page.expect_request("**/api/encounters?*"):
            page.evaluate("() => { void refreshEncounterWorklist(); }")

        with page.expect_request("**/api/auth/logout"):
            page.locator("#logoutButton").press("Enter")
        assert_locked(page)
        expect(page.locator("#sessionCheckMessage")).to_contain_text("正在确认退出")
        assert page.evaluate("appState.currentEncounter === null && appState.encounterWorklist.length === 0")
        stale[0].fulfill(status=401, json={"detail": "expired"})
        assert_locked(page)
        if failure == "server_error":
            logout_posts[0].fulfill(status=503)
        elif failure == "unreachable":
            page.context.set_offline(True)
            logout_posts[0].abort("internetdisconnected")

        retry = page.get_by_role("button", name="重试退出")
        expect(retry).to_be_visible(timeout=15000)
        assert_locked(page)
        assert page.request.get(me).status == 200
        assert page.evaluate("sessionStorage.getItem('mra-logout-pending:v1')") == "1"
        expect(page.locator("#sessionCheckMessage")).to_contain_text("尚未确认退出")
        if failure == "unreachable":
            logout_mode = "allow"
            retry.press("Enter")
            expect(retry).to_be_visible()
            assert_locked(page)
            page.context.set_offline(False)
        if failure == "server_error":
            logout_mode = "503"
            retry.press("Enter")
            expect(retry).to_be_visible()
            assert_locked(page)
            patients = []
            page.on("request", lambda req: patients.append(urlsplit(req.url).path))
            page.reload()
            expect(retry).to_be_visible()
            page.goto(links[1])
            expect(retry).to_be_visible()
            assert_locked(page)
            assert not any(path.startswith(("/api/encounters", "/api/patients")) for path in patients)
            assert page.request.get(me).status == 200
        logout_mode = "allow"
        retry.press("Enter")
        expect(page.locator("#loginMessage")).to_have_text("已退出登录。", timeout=15000)
        expect(page.locator("#loginUsername")).to_be_visible()
        assert page.request.get(me).status == 401
        assert page.evaluate("sessionStorage.getItem('mra-logout-pending:v1')") is None


@pytest.mark.parametrize("lost_receipt", [False, True])
def test_logout_with_server_revocation_unlocks_only_the_login_form(doctor_links, lost_receipt):
    password, links = doctor_links
    with sync_playwright() as pw, pw.chromium.launch() as browser:
        page = browser.new_page()
        open_doctor_visit(page, password, links[0])
        if lost_receipt:
            def drop_after_revocation(route):
                assert route.fetch().ok
                route.abort("connectionclosed")
            page.route("**/api/auth/logout", drop_after_revocation)
        page.locator("#logoutButton").press("Enter")
        expect(page.locator("#loginMessage")).to_have_text("已退出登录。", timeout=15000)
        expect(page.locator("#loginUsername")).to_be_visible()
        expect(page.locator(".doctor-app")).to_be_hidden()
        assert page.request.get(links[0].split("/static/")[0] + "/api/auth/me").status == 401



@pytest.mark.parametrize("width", [390, 1366])
def test_logout_locks_existing_new_and_restored_same_origin_tabs(doctor_links, width):
    password, links = doctor_links
    with sync_playwright() as pw, pw.chromium.launch() as browser:
        context = browser.new_context(viewport={"width": width, "height": 844})
        first, second = context.new_page(), context.new_page()
        open_doctor_visit(first, password, links[0])
        second.goto(links[1])
        expect(second.locator("#patientName")).to_have_text("脱敏患者 2")
        expect(first.locator("#patientName")).to_have_text("脱敏患者 1")

        stale = []
        def delay_first_session_read(route):
            if not stale:
                stale.append((route, route.fetch()))
            else:
                route.continue_()
        second.route("**/api/auth/me", delay_first_session_read)
        with second.expect_request("**/api/auth/me"):
            second.evaluate("window.dispatchEvent(new Event('focus'))")
        assert_locked(second)

        reject = True
        def logout_result(route):
            if reject:
                route.fulfill(status=503)
            else:
                route.continue_()
        first.route("**/api/auth/logout", logout_result)
        first.locator("#logoutButton").press("Enter")
        retry = first.get_by_role("button", name="重试退出")
        expect(retry).to_be_visible(timeout=15000)
        expect(second.get_by_role("button", name="重试退出")).to_be_visible()
        route, valid_before_logout = stale[0]
        assert valid_before_logout.status == 200
        route.fulfill(response=valid_before_logout)
        assert_locked(second)
        assert second.evaluate("appState.currentEncounter === null")

        third = context.new_page()
        reads = []
        third.on("request", lambda req: reads.append(urlsplit(req.url).path))
        third.goto(links[1])
        expect(third.get_by_role("button", name="重试退出")).to_be_visible()
        third.goto(links[1].split("/static/")[0] + "/ready")
        third.go_back()
        expect(third.get_by_role("button", name="重试退出")).to_be_visible()
        assert_locked(third)
        assert not any(path.startswith(("/api/encounters", "/api/patients")) for path in reads)
        reject = False
        retry.press("Enter")
        for page in (first, second, third):
            expect(page.locator("#loginUsername")).to_be_visible()
            expect(page.locator(".doctor-app")).to_be_hidden()
        assert first.request.get(links[0].split("/static/")[0] + "/api/auth/me").status == 401
        third.reload()
        expect(third.locator("#loginUsername")).to_be_visible()


def test_foreground_rechecks_revocation_without_a_browser_logout_event(doctor_links):
    password, links = doctor_links
    with sync_playwright() as pw, pw.chromium.launch() as browser:
        page = browser.new_page()
        open_doctor_visit(page, password, links[0])
        assert page.request.post(links[0].split("/static/")[0] + "/api/auth/logout").ok
        with page.expect_request("**/api/auth/me"):
            page.evaluate("window.dispatchEvent(new Event('focus'))")
        expect(page.locator("#loginUsername")).to_be_visible()
        expect(page.locator(".doctor-app")).to_be_hidden()



def test_mobile_open_dialog_restores_focus_or_releases_keyboard_for_retry(doctor_links):
    password, links = doctor_links
    with sync_playwright() as pw, pw.chromium.launch() as browser:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        open_doctor_visit(page, password, links[0])
        page.locator("#showTranscriptButton").click()
        dialog = page.locator("#workspaceAuxDialog")
        expect(dialog).to_be_visible()
        with page.expect_response("**/api/auth/me"):
            page.evaluate("window.dispatchEvent(new Event('focus'))")
        expect(dialog).to_be_visible()
        expect(page.locator("#closeWorkspaceAuxButton")).to_be_focused()
        page.route("**/api/auth/me", lambda route: route.fulfill(status=503), times=1)
        with page.expect_request("**/api/auth/me"):
            page.evaluate("window.dispatchEvent(new Event('focus'))")
        retry = page.get_by_role("button", name="重新核对")
        expect(retry).to_be_visible()
        assert_locked(page)
        assert not dialog.evaluate("node => node.open")
        page.keyboard.press("Tab")
        expect(retry).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.locator("#patientName")).to_have_text("脱敏患者 1")
        expect(page.locator(".doctor-app")).to_be_visible()
        page.locator("#showTranscriptButton").click()
        expect(dialog).to_be_visible()
