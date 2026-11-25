"""Ordinary doctor navigation after a terminal generation failure, with isolated records."""
import json
import os
import secrets
from pathlib import Path
from uuid import UUID

import pytest
from playwright.sync_api import expect, sync_playwright

from app.db import bind_task_to_encounter, create_encounter, create_task, update_task
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login
from tests.test_doctor_workflow_state_contract_playwright import _server_database
from tests.test_transcript_source_presentation_playwright import _open_from_workbench


def failed_encounter(server, doctor, label):
    source = "说话人一：旧报告留在家中。"
    # A saved ASR fixture with unreviewed roles, never evidence for the writer's text.
    recorded = {"conversation_text": source, "asr_source": {"audio_id": "simulated-audio",
                "segments": [{"segment_id": "s1", "speaker_id": "SPEAKER_00", "text": "旧报告留在家中。"}]}}
    with _server_database(server):
        encounter = create_encounter(doctor_user_id=doctor, deidentified_id=label, check_in_status="in_progress")
        task = create_task("audio", "FAILED", "failed", source)
        bind_task_to_encounter(task, encounter["id"], owner_user_id=doctor)
        update_task(task, status="FAILED", current_stage="failed", result_json=json.dumps(recorded),
                    error_message="LLM_NO_SUPPORTED_FACTS: synthetic failed attempt")
    return encounter["id"], task


def login_doctor(page, username, password):
    page.locator("#loginUsername").fill(username)
    page.locator("#loginPassword").fill(password)
    page.locator("#loginForm button[type=submit]").click()
    expect(page.locator("#authUserLabel")).to_contain_text("doctor")


@pytest.mark.parametrize("width", [1366, 390])
def test_handwritten_r1_draft_recovery_and_lost_ack(width):
    server = RunningServer()
    try:
        with sync_playwright() as pw, pw.chromium.launch() as browser:
            page = browser.new_page(viewport={"width": width, "height": 844})
            _login(page, server.base_url)
            password = secrets.token_urlsafe(24)
            writer = page.request.post(server.base_url + "/api/auth/users", data={
                "username": "mfirst-doc", "password": password, "display_name": "合成执笔人", "role": "doctor",
            }).json()
            owner_id = writer["id"] if "id" in writer else writer["user"]["id"]
            encounter, task = failed_encounter(server, owner_id, "SYN-WRITE-A")
            other, other_task = failed_encounter(server, owner_id, "SYN-WRITE-B")
            open_form = page.get_by_role("button", name="手写病历", exact=True)
            _open_from_workbench(page, encounter)
            expect(open_form).to_have_count(0)  # Admin read access does not allow writing.
            page.locator("#logoutButton").click()
            login_doctor(page, "mfirst-doc", password)
            _open_from_workbench(page, encounter)
            open_form.press("Enter")
            dialog = page.get_by_role("dialog", name="手写病历")
            chief = dialog.get_by_label("主诉", exact=True)
            illness = dialog.get_by_label("现病史", exact=True)
            save = dialog.get_by_role("button", name="保存手写首稿")
            expect(chief).to_be_focused()
            expect(chief).to_have_value("")
            expect(illness).to_have_value("")
            save.press("Enter")
            expect(dialog.get_by_role("status")).to_contain_text("至少填写")
            note = "复核以往资料 <本次> & 单独记录。"
            illness.fill(note)
            page.keyboard.press("Escape")
            expect(open_form).to_be_focused()
            _open_from_workbench(page, other)
            open_form.press("Enter")
            expect(illness).to_have_value("")
            chief.fill("另一就诊草稿")
            page.keyboard.press("Escape")
            _open_from_workbench(page, encounter)
            page.reload()
            open_form.press("Enter")
            expect(illness).to_have_value(note)
            expect(dialog).to_contain_text(f"前次生成任务 #{task}")
            assert dialog.evaluate("d => d.scrollWidth <= d.clientWidth")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            evidence_dir = os.getenv("MRA_MANUAL_FIRST_UI_EVIDENCE")
            if evidence_dir:
                Path(evidence_dir).mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(evidence_dir) / f"普通医生手写-{width}.png"))
            path = f"/api/encounters/{encounter}/manual-first-draft"
            requests = []
            statuses = []

            def lose_first_response(route):
                requests.append(route.request.post_data_json)
                response = route.fetch()
                statuses.append(response.status)
                if len(requests) == 1:
                    route.abort("failed")  # Server committed; browser did not receive its receipt.
                else:
                    route.fulfill(response=response)

            page.route("**" + path, lose_first_response)
            save.press("Enter")
            retry = dialog.get_by_role("button", name="重试保存同一首稿")
            expect(retry).to_be_enabled()
            expect(illness).to_have_value(note)
            retry.press("Enter")
            origin = page.locator("#recordFields .manual-first-origin")
            expect(origin).to_contain_text("首稿来源 · 医生手写")
            expect(origin).to_contain_text("合成执笔人")
            expect(origin).to_contain_text(f"前次生成任务 #{task}")
            if evidence_dir:
                page.screenshot(path=str(Path(evidence_dir) / f"手写首稿来源-{width}.png"))
            assert statuses == [201, 200] and requests[0] == requests[1]
            assert set(requests[0]) == {"failed_task_id", "request_id", "present_illness"}
            UUID(requests[0]["request_id"])
            detail = page.request.get(server.base_url + f"/api/encounters/{encounter}").json()
            assert len(detail["revisions"]) == 1
            assert detail["current_revision"]["source"] == "doctor_manual_first"
            first = detail["task"]["result_json"]
            assert first["fields"]["present_illness"]["value"] == note
            assert not first["fields"]["present_illness"]["source_spans"]
            assert not first.get("approved")
            page.locator('[data-open-detail="history:record"]').press("Enter")
            history = page.locator("#detailDrawerContent")
            expect(history).to_contain_text("医生手写首稿")
            expect(history).to_contain_text("合成执笔人")
            page.keyboard.press("Escape")
            # Successful save clears only this draft. Explicit logout clears this writer's drafts in this tab.
            keys = page.evaluate("Object.keys(sessionStorage)")
            assert f"mra-manual-first:v1:{owner_id}:{encounter}:{task}" not in keys
            assert f"mra-manual-first:v1:{owner_id}:{other}:{other_task}" in keys
            page.evaluate("sessionStorage.setItem('unrelated-key', 'keep')")
            page.locator("#logoutButton").click()
            expect(page.locator("#loginPanel")).to_be_visible()
            keys = page.evaluate("Object.keys(sessionStorage)")
            assert not any(key.startswith(f"mra-manual-first:v1:{owner_id}:") for key in keys)
            assert "unrelated-key" in keys
    finally:
        server.close()


@pytest.mark.parametrize("after_commit", ["refresh", "logout", "expired", "expired-same", "legacy", "timeout"])
def test_first_draft_late_receipt_does_not_expose_or_resurrect_draft(after_commit):
    server = RunningServer()
    try:
        with sync_playwright() as pw, pw.chromium.launch() as browser:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            _login(page, server.base_url)
            password = secrets.token_urlsafe(24)
            doctor_ids = {}
            for username in ("first-writer", "next-writer"):
                created = page.request.post(server.base_url + "/api/auth/users", data={
                    "username": username, "password": password, "role": "doctor", "display_name": username,
                })
                assert created.ok
                created_user = created.json()
                doctor_ids[username] = created_user.get("id") or created_user["user"]["id"]
            page.locator("#logoutButton").click()
            login_doctor(page, "first-writer", password)
            doctor = page.request.get(server.base_url + "/api/auth/me").json()["id"]
            encounter, task = failed_encounter(server, doctor, "SYN-LATE-RECEIPT")
            _open_from_workbench(page, encounter)
            page.get_by_role("button", name="手写病历", exact=True).press("Enter")
            dialog = page.get_by_role("dialog", name="手写病历")
            dialog.get_by_label("主诉", exact=True).fill("本次由医生记录来意。")
            if after_commit == "legacy":
                next_owner = doctor_ids["next-writer"]
                other, other_task = failed_encounter(server, next_owner, "SYN-LEGACY-TAB")
                other_key = f"mra-manual-first:v1:{next_owner}:{other}:{other_task}"
                page.evaluate("""k => {
                    sessionStorage.removeItem("mra-manual-first:tab-account:v1");
                    sessionStorage.setItem(k, JSON.stringify({chief:"乙的历史暂存", illness:"", requestId:"", attempted:false}));
                    sessionStorage.setItem("unrelated-legacy-key","keep");
                }""", other_key)
                login_tab = context.new_page()
                login_tab.goto(server.base_url + "/static/doctor.html")
                login_tab.locator("#logoutButton").click()
                login_doctor(login_tab, "next-writer", password)
                login_tab.close()
                page.reload()
                expect(page.locator("#authUserLabel")).to_contain_text("next-writer")
                _open_from_workbench(page, other)
                page.get_by_role("button", name="手写病历", exact=True).press("Enter")
                expect(dialog.get_by_label("主诉", exact=True)).to_have_value("乙的历史暂存")
                key = f"mra-manual-first:v1:{doctor}:{encounter}:{task}"
                assert page.evaluate("k => sessionStorage.getItem(k)", key) is None
                assert page.evaluate("sessionStorage.getItem('unrelated-legacy-key')") == "keep"
                return
            if after_commit in ("expired", "expired-same"):
                # Passive server revocation leaves this doctor to discover expiry on save.
                # Explicit logout in another tab now locks this editor immediately.
                assert page.request.post(server.base_url + "/api/auth/logout").ok
                dialog.get_by_role("button", name="保存手写首稿").press("Enter")
                expect(page.locator("#loginPanel")).to_be_visible()
                if after_commit == "expired-same":
                    # A same-account login resumes this authorized encounter link.
                    with page.expect_response(lambda response: response.url.endswith(f"/api/encounters/{encounter}")
                                              and response.status == 200):
                        login_doctor(page, "first-writer", password)
                    expect(page.locator("#patientProfile")).to_contain_text(f"E-{encounter}")
                    page.wait_for_function(
                        "id => appState.currentTaskId === id && !appState.busy", arg=task
                    )
                    page.get_by_role("button", name="手写病历", exact=True).press("Enter")
                    expect(dialog.get_by_label("主诉", exact=True)).to_have_value("本次由医生记录来意。")
                    return
                login_doctor(page, "next-writer", password)
                expect(page.locator("body")).to_have_attribute("data-product-view", "workbench")
                expect(page.locator("#patientName")).to_have_text("未选择患者")
                expect(page.locator("#manualFirstChief")).to_have_value("")
                key = f"mra-manual-first:v1:{doctor}:{encounter}:{task}"
                assert page.evaluate("k => sessionStorage.getItem(k)", key) is None
                assert not page.evaluate("k => manualFirstDrafts.has(k) || manualFirstWrites.has(k)", key)
                return
            held = []
            if after_commit == "timeout":
                request_ids = []

                def hold_first_request(route):
                    request_ids.append(route.request.post_data_json["request_id"])
                    if len(request_ids) == 2:
                        route.continue_()

                page.route("**/manual-first-draft", hold_first_request)
                dialog.get_by_role("button", name="保存手写首稿").press("Enter")
                retry = dialog.get_by_role("button", name="重试保存同一首稿")
                expect(retry).to_be_enabled(timeout=22000)
                retry.press("Enter")
                expect(page.locator("#recordFields .manual-first-origin")).to_be_visible()
                assert len(request_ids) == 2 and request_ids[0] == request_ids[1]
                detail = page.request.get(server.base_url + f"/api/encounters/{encounter}").json()
                assert len(detail["revisions"]) == 1
                return

            def delay_receipt(route):
                result = route.fetch()
                assert result.status == 201
                held.append((route, result))
                if after_commit == "refresh":
                    route.abort("failed")

            page.route("**/manual-first-draft", delay_receipt)
            dialog.get_by_role("button", name="保存手写首稿").press("Enter")
            key = f"mra-manual-first:v1:{doctor}:{encounter}:{task}"
            page.wait_for_function("k => JSON.parse(sessionStorage.getItem(k))?.attempted", arg=key)
            if after_commit == "refresh":
                expect(dialog.get_by_role("button", name="重试保存同一首稿")).to_be_enabled()
                page.reload()
                expect(page.locator("#recordFields .manual-first-origin")).to_be_visible()
                assert page.evaluate("k => sessionStorage.getItem(k)", key) is None
            else:
                dialog.get_by_role("button", name="返回本次就诊").press("Enter")
                page.locator("#logoutButton").click()
                expect(page.locator("#loginPanel")).to_be_visible()
                login_doctor(page, "next-writer", password)
                route, response = held[0]
                with page.expect_response(lambda res: res.url.endswith("/manual-first-draft")):
                    route.fulfill(response=response)
                page.wait_for_function("manualFirstWrites.size === 0")
                assert page.evaluate("k => sessionStorage.getItem(k)", key) is None
                expect(dialog).not_to_be_visible()
                expect(page.locator("#recordFields")).not_to_contain_text("本次由医生记录来意")
            assert len(held) == 1
    finally:
        server.close()
