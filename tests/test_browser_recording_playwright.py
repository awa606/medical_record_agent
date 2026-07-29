from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str) -> None:
    import urllib.request

    last_error = None
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
                health = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(f"{base_url}/ready", timeout=2) as response:
                ready = json.loads(response.read().decode("utf-8"))
            if health.get("status") == "ok" and ready.get("status") == "ready":
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


class RunningServer:
    def __init__(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["MEDICAL_RECORD_AGENT_UPLOAD_DIR"] = str(Path(self.temp_dir.name) / "uploads")
        env["MEDICAL_RECORD_AGENT_DB"] = str(Path(self.temp_dir.name) / "edge.sqlite3")
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_for_health(self.base_url)

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.temp_dir.cleanup()


def _login(page, base_url: str) -> None:
    page.goto(f"{base_url}/static/doctor.html", wait_until="networkidle")
    page.fill("#loginUsername", "admin")
    page.fill("#loginPassword", "admin123456")
    page.click("#loginForm button[type='submit']")
    expect(page.locator("#authUserLabel")).to_contain_text("admin")


def _prepare_ready_encounter(page) -> None:
    page.evaluate(
        """
        async () => {
          const encounter = await api('/api/encounters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              patient_deidentified_id: `REC-${Date.now()}`,
              patient_display_name: 'Recording Test Patient'
            })
          });
          const checkedIn = await api(`/api/encounters/${encounter.id}/check-in`, { method: 'POST' });
          window.__MRA_APP_STATE__.currentEncounter = checkedIn;
          renderAll();
        }
        """
    )
    page.wait_for_function(
        "window.__MRA_APP_STATE__?.currentEncounter?.check_in_status === 'checked_in'"
    )


def _click_first_visible(page, selectors: list[str]) -> str:
    for selector in selectors:
        locator = page.locator(selector)
        if locator.is_visible():
            locator.click()
            return selector
    state = page.evaluate(
        "() => ({ status: window.__MRA_APP_STATE__?.browserRecordingStatus, html: document.body.innerText })"
    )
    raise AssertionError(f"no visible recording control among {selectors}: {state}")


def test_recording_entry_guides_to_encounter_selection_and_panel() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1366, "height": 768})
            page = context.new_page()
            _login(page, server.base_url)

            page.click("#inputMethodButton")
            expect(page.locator("#drawer")).to_have_class(re.compile(r".*\bactive\b.*"))
            expect(page.locator("#inputMethodMenu")).to_be_hidden()
            expect(page.locator(".encounter-selection-notice")).to_contain_text("请先选择已报到或问诊中的患者")
            assert page.evaluate("window.__MRA_APP_STATE__?.pendingInputMethodAfterEncounterSelection") == "record"

            encounter_id = page.evaluate(
                """
                async () => {
                  const encounter = await api('/api/encounters', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      patient_deidentified_id: `REC-GUIDE-${Date.now()}`,
                      patient_display_name: 'Recording Guide Patient'
                    })
                  });
                  await api(`/api/encounters/${encounter.id}/check-in`, { method: 'POST' });
                  await api(`/api/encounters/${encounter.id}/start`, { method: 'POST' });
                  await refreshEncounterWorklist();
                  return encounter.id;
                }
                """
            )
            drawer_record_button = page.locator(
                f'#encounterWorklist [data-restore-encounter="{encounter_id}"][data-after-restore-input="record"]'
            )
            expect(drawer_record_button).to_contain_text("选择并开始录音")
            drawer_metrics = page.evaluate(
                """
                (encounterId) => {
                  const drawer = document.querySelector("#drawer");
                  const list = document.querySelector("#encounterWorklist");
                  const button = Array.from(document.querySelectorAll("#encounterWorklist [data-restore-encounter]"))
                    .find((node) => node.dataset.restoreEncounter === String(encounterId) && node.dataset.afterRestoreInput === "record");
                  const article = button.closest(".encounter-worklist-item");
                  const drawerBox = drawer.getBoundingClientRect();
                  const articleBox = article.getBoundingClientRect();
                  const buttonBox = button.getBoundingClientRect();
                  const hitX = Math.floor((buttonBox.left + buttonBox.right) / 2);
                  const hitY = Math.floor((buttonBox.top + buttonBox.bottom) / 2);
                  const hit = document.elementFromPoint(hitX, hitY);
                  return {
                    bodyOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    drawerOverflow: drawer.scrollWidth - drawer.clientWidth,
                    listOverflow: list.scrollWidth - list.clientWidth,
                    buttonInsideDrawer: buttonBox.left >= drawerBox.left && buttonBox.right <= drawerBox.right,
                    buttonInsideArticle: (
                      buttonBox.left >= articleBox.left
                      && buttonBox.right <= articleBox.right
                      && buttonBox.top >= articleBox.top
                      && buttonBox.bottom <= articleBox.bottom
                    ),
                    buttonHitTarget: hit === button || button.contains(hit),
                  };
                }
                """,
                encounter_id,
            )
            assert drawer_metrics["bodyOverflow"] <= 0
            assert drawer_metrics["drawerOverflow"] <= 1
            assert drawer_metrics["listOverflow"] <= 1
            assert drawer_metrics["buttonInsideDrawer"] is True
            assert drawer_metrics["buttonInsideArticle"] is True
            assert drawer_metrics["buttonHitTarget"] is True
            drawer_record_button.click()
            expect(page.locator("#recordingPanel.active")).to_be_visible()
            expect(page.locator("#drawerTitle")).to_contain_text("浏览器录音生成病历")
            expect(page.locator("#browserRecordingMessage")).to_contain_text("点击“开始录音”")

            page.evaluate(
                """
                () => {
                  window.__MRA_APP_STATE__.browserRecordingStatus = 'recording';
                  window.__MRA_APP_STATE__.browserRecordingMessage = '';
                  renderBrowserRecordingPanel();
                  closeDrawer();
                }
                """
            )
            expect(page.locator("#drawer")).to_have_class(re.compile(r".*\bactive\b.*"))
            expect(page.locator("#browserRecordingMessage")).to_contain_text("录音正在进行")
            assert page.evaluate("window.__MRA_APP_STATE__?.browserRecordingStatus") == "recording"
            browser.close()
    finally:
        server.close()


def test_browser_recording_failed_chunk_survives_refresh_and_completes() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--use-fake-device-for-media-stream",
                    "--use-fake-ui-for-media-stream",
                ],
            )
            context = browser.new_context()
            context.add_init_script("window.__MRA_BROWSER_RECORDING_CHUNK_SECONDS = 1;")
            page = context.new_page()
            _login(page, server.base_url)
            _prepare_ready_encounter(page)
            encounter_id = page.evaluate("window.__MRA_APP_STATE__.currentEncounter.id")
            page.evaluate("openReservedRecording()")

            state = {"allow_upload": False}

            def route_first_chunk(route) -> None:
                if not state["allow_upload"]:
                    route.fulfill(status=503, content_type="application/json", body='{"detail":"simulated chunk failure"}')
                    return
                route.continue_()

            page.route("**/api/asr/sessions/*/chunks", route_first_chunk)
            page.click("#startBrowserRecordingButton")
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingStatus === 'recording'")
            page.wait_for_function(
                "window.__MRA_APP_STATE__?.browserRecordingPendingChunks > 0",
                timeout=15000,
            )
            first_session = page.evaluate("window.__MRA_APP_STATE__.browserRecordingSessionId")
            first_chunk = page.evaluate(
                "listBrowserRecordingQueueEntries(window.__MRA_APP_STATE__.browserRecordingSessionId)"
                ".then((rows) => rows[0] && ({index: rows[0].chunk_index, sha256: rows[0].sha256}))"
            )

            assert first_session
            assert f"session_id={first_session}" in page.url
            page.evaluate("cleanupBrowserRecordingCapture()")
            state["allow_upload"] = True
            page.goto(f"{server.base_url}/static/doctor.html?session_id={first_session}", wait_until="networkidle")
            page.evaluate("(encounterId) => restoreEncounter(encounterId)", encounter_id)
            page.wait_for_function(
                "(encounterId) => window.__MRA_APP_STATE__?.currentEncounter?.id === encounterId",
                arg=encounter_id,
            )
            page.wait_for_timeout(5000)
            restored_session = page.evaluate("window.__MRA_APP_STATE__?.browserRecordingSessionId")
            assert restored_session == first_session
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingUploadedChunks >= 1", timeout=15000)
            recovered_chunk = page.evaluate(
                "fetch(`/api/asr/sessions/${window.__MRA_APP_STATE__.browserRecordingSessionId}/chunks/status`)"
                ".then((response) => response.json())"
                ".then((status) => status.chunks[0] && ({index: status.chunks[0].chunk_index, sha256: status.chunks[0].sha256}))"
            )
            assert recovered_chunk == first_chunk

            page.evaluate("openReservedRecording()")
            _click_first_visible(page, ["#resumeBrowserRecordingButton", "#startBrowserRecordingButton"])
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingStatus === 'recording'")
            page.wait_for_timeout(1300)
            page.click("#pauseBrowserRecordingButton")
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingStatus === 'paused'")
            page.click("#resumeBrowserRecordingButton")
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingStatus === 'recording'")
            page.wait_for_timeout(1300)
            page.click("#stopBrowserRecordingButton")
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingStatus === 'recorded'", timeout=20000)
            preview_src = page.locator("#browserRecordingPreview").evaluate("node => node.currentSrc || node.src")
            assert "/api/audio/" in preview_src

            page.click("#submitBrowserRecordingButton")
            page.wait_for_function(
                "window.__MRA_APP_STATE__?.currentTaskId || document.querySelectorAll('#transcriptList .transcript-table-row').length > 0",
                timeout=30000,
            )
            browser.close()
    finally:
        server.close()


def test_browser_recording_cancel_cleans_local_queue_and_server_state() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--use-fake-device-for-media-stream",
                    "--use-fake-ui-for-media-stream",
                ],
            )
            context = browser.new_context()
            context.add_init_script("window.__MRA_BROWSER_RECORDING_CHUNK_SECONDS = 1;")
            page = context.new_page()
            _login(page, server.base_url)
            _prepare_ready_encounter(page)
            page.evaluate("openReservedRecording()")
            page.route("**/api/asr/sessions/*/chunks", lambda route: route.abort())
            page.click("#startBrowserRecordingButton")
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingStatus === 'recording'")
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingPendingChunks > 0", timeout=15000)
            session_id = page.evaluate("window.__MRA_APP_STATE__.browserRecordingSessionId")
            page.click("#cancelBrowserRecordingButton")
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingStatus === 'idle'")
            local_count = page.evaluate(
                "(sessionId) => listBrowserRecordingQueueEntries(sessionId).then((rows) => rows.length)",
                session_id,
            )
            assert local_count == 0
            session_status = page.evaluate(
                "(path) => fetch(path).then((response) => response.json()).then((session) => session.status)",
                f"/api/asr/sessions/{session_id}",
            )
            assert session_status == "cancelled"
            browser.close()
    finally:
        server.close()


def test_browser_recording_offline_cancel_retries_cleanup_after_reconnect() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--use-fake-device-for-media-stream",
                    "--use-fake-ui-for-media-stream",
                ],
            )
            context = browser.new_context()
            context.add_init_script("window.__MRA_BROWSER_RECORDING_CHUNK_SECONDS = 1;")
            page = context.new_page()
            _login(page, server.base_url)
            _prepare_ready_encounter(page)
            page.evaluate("openReservedRecording()")
            page.click("#startBrowserRecordingButton")
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingStatus === 'recording'")
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingUploadedChunks >= 1", timeout=15000)
            session_id = page.evaluate("window.__MRA_APP_STATE__.browserRecordingSessionId")

            context.set_offline(True)
            page.click("#cancelBrowserRecordingButton")
            page.wait_for_function("window.__MRA_APP_STATE__?.browserRecordingStatus === 'idle'")
            cleanup_count = page.evaluate("listBrowserRecordingCleanups().then((rows) => rows.length)")
            assert cleanup_count == 1

            context.set_offline(False)
            page.wait_for_function(
                "(sessionId) => fetch(`/api/asr/sessions/${sessionId}/chunks/status`, { cache: 'no-store' })"
                ".then((response) => response.json())"
                ".then((status) => status.status === 'cancelled')",
                arg=session_id,
                timeout=15000,
            )
            page.wait_for_function("listBrowserRecordingCleanups().then((rows) => rows.length === 0)", timeout=15000)
            local_count = page.evaluate(
                "(sessionId) => listBrowserRecordingQueueEntries(sessionId).then((rows) => rows.length)",
                session_id,
            )
            assert local_count == 0
            session_status = page.evaluate(
                "(path) => fetch(path, { cache: 'no-store' }).then((response) => response.json()).then((session) => session.status)",
                f"/api/asr/sessions/{session_id}",
            )
            assert session_status == "cancelled"
            chunk_status = page.evaluate(
                "(path) => fetch(path, { cache: 'no-store' }).then((response) => response.json())",
                f"/api/asr/sessions/{session_id}/chunks/status",
            )
            assert chunk_status["status"] == "cancelled"
            assert chunk_status["chunk_count"] == 0
            browser.close()
    finally:
        server.close()
