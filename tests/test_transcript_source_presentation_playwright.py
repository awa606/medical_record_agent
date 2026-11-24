"""Persisted text/audio source presentation; isolated API and synthetic media.

The WAV is silence used only to test duration/seeking. ASR segments are explicit
stored fixtures, not recognition output, and no model request is made here.
"""
from __future__ import annotations

import io
import json
import secrets
import wave
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from app.db import bind_task_to_encounter, create_encounter, create_task, update_task
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login
from tests.test_doctor_workflow_state_contract_playwright import _server_database


TEXT = "医生：这两天有什么不舒服？\n患者：文本病例咳嗽两天，没有药物过敏史。"
AUDIO_TEXT = "患者：音频病例发热两天。\n患者：没有胸痛。\n患者：另有未记录时间的说明。"


def _silent_wav(seconds: int = 65) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * seconds)
    return output.getvalue()


def _saved_encounter(server, owner_id, patient_id, input_type, text, asr_source=None, fields=None):
    result = {"conversation_text": text, "fields": fields or {}, "draft": ""}
    if asr_source is not None:
        result["asr_source"] = asr_source
    with _server_database(server):
        encounter = create_encounter(
            doctor_user_id=owner_id,
            deidentified_id=patient_id,
            display_name="合成来源测试",
            check_in_status="in_progress",
        )
        task_id = create_task(
            input_type=input_type,
            input_text=text,
            status="WAITING_DOCTOR_REVIEW",
            current_stage="waiting_doctor_review",
        )
        bind_task_to_encounter(task_id, encounter["id"], owner_user_id=owner_id)
        update_task(task_id, result_json=json.dumps(result, ensure_ascii=False))
    return encounter["id"]


def test_historical_field_evidence_uses_clinical_sentence_and_discards_unverified_times():
    server = RunningServer()
    try:
        with sync_playwright() as pw, pw.chromium.launch() as browser:
            page = browser.new_page()
            _login(page, server.base_url)
            password = secrets.token_urlsafe(24)
            users = server.base_url + "/api/auth/users"
            assert page.request.post(users, data={
                "username": "history-reader", "password": password, "role": "doctor",
                "display_name": "模拟医生",
            }).ok
            assert page.request.post(server.base_url + "/api/auth/logout").ok
            login = page.request.post(server.base_url + "/api/auth/login", data={
                "username": "history-reader", "password": password,
            }).json()["user"]
            assert login["role"] == "doctor"
            page.reload()
            uploaded = page.request.post(server.base_url + "/api/audio/upload", multipart={
                "file": {"name": "timing.wav", "mimeType": "audio/wav", "buffer": _silent_wav(15)},
            })
            assert uploaded.ok
            repeated = "喝水后我头晕"
            segments = [
                {"segment_id": "d", "role": "医生", "text": "先听我说。" + repeated, "start": 1, "end": 4},
                {"segment_id": "p", "role": "患者", "text": repeated, "start": 9, "end": 11,
                 "role_source": "manual", "reviewed_by_doctor": True},
                {"segment_id": "n", "role": "患者", "text": "睡得不错"},
            ]
            transcript = "\n".join(f"[{row['role']}] {row['text']}" for row in segments)
            unknown = "未记录音频时间"
            cases = [
                ({"text": repeated, "index": 1}, "00:01.0–00:04.0", "医生"),
                ({"text": repeated, "index": 2}, "00:09.0–00:11.0", "患者"),
                ({"text": repeated}, unknown, None),
                ({"text": repeated, "index": "1"}, unknown, None),
                ({"text": repeated, "index": 1, "segment_id": "p"}, unknown, None),
                ({"text": "先听我说", "segment_id": "d", "start_time": 9}, unknown, None),
                ({"text": "[患者] " + repeated, "segment_id": "p", "start_time": 9.5}, "00:09.5–00:11.0", "患者"),
                ({"text": "睡得不错", "start_time": 0}, unknown, "患者"),
                ({"text": "先听我说。" + repeated, "segment_id": "d"}, "00:01.0–00:04.0", "医生"),
            ]
            source = {"audio_id": uploaded.json()["audio_id"], "engine": "mock",
                      "conversation_text": transcript, "text": transcript, "segments": segments}
            fields = {"present_illness": {"value": repeated, "status": "complete", "missing": False,
                                          "source_spans": [span for span, _, _ in cases]}}
            encounter = _saved_encounter(server, login["id"], "SIM-HISTORY", "text", transcript, source, fields)
            _open_from_workbench(page, encounter)
            page.locator('[data-open-detail="field:present_illness"]').first.click()
            cards = page.locator("#detailDrawerContent .field-evidence-detail")
            expect(cards).to_have_count(len(cases))
            for i, (span, timing, role) in enumerate(cases):
                body = cards.nth(i).inner_text()
                assert span["text"] in body and timing in body, (span, body)
                assert ("说话人标注" in body) == bool(role), (span, body)
                if role:
                    assert "说话人标注　" + role in body
                expect(cards.nth(i).locator("summary")).to_have_count(int(i in {0, 1, 6, 8}))
            for i in (0, 1, 8):
                summary = cards.nth(i).locator("summary")
                summary.focus()
                page.keyboard.press("Enter")
                lines = cards.nth(i).locator(".field-source-context li")
                assert lines.count() == (2 if i == 8 else 3)
                current = lines.filter(has_text="引用所在句")
                expect(current).to_contain_text("患者" if i == 1 else "医生（角色待核）")
                expect(current).to_contain_text(cases[i][0]["text"])
                following = lines.filter(has_text="后一句")
                expect(following).to_contain_text("睡得不错" if i == 1 else repeated)
                expect(following).to_contain_text("患者（角色待核）" if i == 1 else "患者")
                page.keyboard.press("Space")
                expect(lines.first).to_be_hidden()
            page.set_viewport_size({"width": 390, "height": 520})
            panel = page.locator("#detailPanel")
            page.locator("#closeDrawerButton").focus()
            expect(page.locator("#closeDrawerButton")).to_be_focused()
            assert panel.evaluate("el => el.scrollHeight > el.clientHeight")
            page.keyboard.press("Tab")
            expect(panel).to_be_focused()
            page.keyboard.press("Shift+Tab")
            expect(page.locator("#closeDrawerButton")).to_be_focused()
            page.keyboard.press("End")
            expect(panel).to_be_focused()
            page.wait_for_function("""() => {
                const el = document.querySelector('#detailPanel');
                return el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
            }""")
            page.keyboard.press("Home")
            page.wait_for_function("() => document.querySelector('#detailPanel').scrollTop === 0")
            page.keyboard.press("Escape")
            expect(page.locator('[data-open-detail="field:present_illness"]').first).to_be_focused()
            page.set_viewport_size({"width": 390, "height": 844})

            # Same doctor, new saved task: source identity, role and sentence index must agree.
            text = "医生：刚才如何？\n患者：稍稍头晕，又缓过来了！\n家属：我当时也在场。\n没有录入说话人。"
            text_spans = [{"text": "头晕", "index": 1}, {"text": "头晕"}, {"text": "头晕", "index": 0},
                          {"text": "患者：没有录入说话人", "index": 3}]
            def check_saved(patient, kind, original, asr, spans, status="complete"):
                saved_fields = {"present_illness": {**fields["present_illness"], "source_spans": spans, "status": status}}
                target = _saved_encounter(server, login["id"], patient, kind, original, asr, saved_fields)
                _open_from_workbench(page, target)
                page.locator('[data-open-detail="field:present_illness"]').first.click()
                expect(cards).to_have_count(len(spans))
                return cards.locator("summary")

            summaries = check_saved("SIM-CONTEXT-TEXT", "text", text, None, text_spans)
            expect(summaries).to_have_count(1)
            summaries.click()
            lines = cards.first.locator("li")
            expect(lines).to_have_text(["前一句医生刚才如何？", "引用所在句患者稍稍头晕，又缓过来了！", "后一句家属我当时也在场。"])
            assert page.locator("#detailPanel").evaluate("el => el.scrollWidth <= el.clientWidth + 1")
            page.keyboard.press("Escape")
            # Only the indexed sentence is selected; a repeated word within it is not highlighted.
            one = "她头晕，我本人早上也头晕。"
            one_spans = [{"text": "头晕", "index": 0}, {"text": one, "index": 0},
                         {"text": "头晕", "index": 1}, {"text": "医生：头晕", "index": 0}]
            summaries = check_saved("SIM-ONE-TEXT", "text", "患者：" + one, None, one_spans, "conflicting")
            expect(summaries).to_have_text(["看完整原句"])
            page.locator("#closeDrawerButton").focus()
            for _ in range(12):
                page.keyboard.press("Tab")
                if summaries.evaluate("el => el === document.activeElement"):
                    break
            expect(summaries).to_be_focused()
            page.keyboard.press("Enter")
            expect(cards.first.locator("li div")).to_have_text(one)
            expect(cards.first.locator("li mark")).to_have_count(0)
            page.keyboard.press("Space")
            expect(cards.first.locator("li")).to_be_hidden()
            page.keyboard.press("Escape")

            audio_one = {**source, "text": "患者：" + one, "conversation_text": "患者：" + one,
                         "segments": [{"segment_id": "one", "text": one, "role": "患者", "start": 1, "end": 4}]}
            spans = [{"text": "头晕", "index": 0, "segment_id": "one"},
                     {"text": "头晕", "index": 0, "segment_id": "old"}]
            summaries = check_saved("SIM-ONE-AUDIO", "audio", "患者：" + one, audio_one, spans)
            expect(summaries).to_have_text(["看完整原句"])
            summaries.click()
            expect(cards.first.locator("li")).to_have_text("引用所在句患者（角色待核）" + one)
            page.keyboard.press("Escape")
            for patient, kind, original, bad_source in [
                ("SIM-CONTEXT-NONE", "text", "", None),
                ("SIM-CONTEXT-TYPE", "unknown", text, None),
                ("SIM-CONTEXT-MISSING", "audio", text, None),
                ("SIM-CONTEXT-SCALAR", "audio", text, {**source, "segments": "旧记录"}),
                ("SIM-CONTEXT-NULL", "audio", text, {**source, "segments": [segments[0], None]}),
            ]:
                summaries = check_saved(patient, kind, original, bad_source, text_spans[:1])
                expect(summaries).to_have_count(0)
                expect(cards.first).to_contain_text("头晕")
                expect(cards.first).not_to_contain_text("家属")
                page.keyboard.press("Escape")
    finally:
        server.close()


def _open_from_workbench(page, encounter_id):
    page.locator('[data-product-view-target="workbench"]').first.click()
    with page.expect_response(lambda response:
                              urlsplit(response.url).path == "/api/encounters"
                              and response.request.method == "GET"):
        page.locator("#refreshWorklistButton").click()
    page.locator(
        f'#dashboardEncounterList [data-restore-encounter="{encounter_id}"]'
    ).click()
    expect(page.locator("body")).to_have_attribute("data-product-view", "encounter")
    expect(page.locator("#patientProfile")).to_contain_text(f"E-{encounter_id}")


def _assert_text_source(page):
    expect(page.locator("#transcriptHeading")).to_have_text("输入原文")
    expect(page.locator("#transcriptSourceNotice")).to_be_visible()
    expect(page.locator("#transcriptSourceNotice")).to_have_text(
        "文本输入 · 无录音时间"
    )
    expect(page.locator("#transcriptList")).to_contain_text("文本病例咳嗽两天")
    expect(page.locator("#transcriptList")).to_contain_text("这两天有什么不舒服")
    expect(page.locator("#transcriptList")).not_to_contain_text("音频病例")
    expect(page.locator("#transcriptList")).not_to_contain_text("--:--")
    expect(page.locator("#transcriptList .transcript-row-time")).to_have_count(0)
    expect(page.locator("#transcriptList [data-segment-start]")).to_have_count(0)
    expect(page.locator("#consultationAudioPlayer")).not_to_be_visible()
    assert page.locator("#consultationAudio").get_attribute("src") is None


def _assert_text_detail(page):
    page.locator("#transcriptList .transcript-row-link").first.click()
    detail = page.locator("#detailDrawerContent")
    expect(detail).to_contain_text("文本输入（未关联录音）")
    expect(detail).not_to_contain_text("--:--")
    expect(detail.locator(".transcript-row-time")).to_have_count(0)
    page.locator("#closeDrawerButton").click()
    expect(page.locator("#drawer")).to_have_attribute("aria-hidden", "true")
    assert page.locator("#drawer").evaluate("node => node.inert")


def _assert_player_controls_fit(page):
    # These are CSS pixels at a 1280px viewport, not physical browser zoom.
    ids = ["audioPlayPauseButton", "audioTimeLabel", "audioSeekRange",
           "audioMuteButton", "audioVolumeRange", "audioPlaybackRate"]
    shell = page.locator("#consultationAudioPlayer").bounding_box()
    assert shell
    bounds = []
    for name in ids:
        node = page.locator(f"#{name}")
        expect(node).to_be_visible()
        box = node.bounding_box()
        assert box and box["width"] > 0 and box["height"] > 0, (name, box)
        assert box["x"] >= shell["x"] - 1, (name, box, shell)
        assert box["y"] >= shell["y"] - 1, (name, box, shell)
        assert box["x"] + box["width"] <= shell["x"] + shell["width"] + 1, (name, box, shell)
        assert box["y"] + box["height"] <= shell["y"] + shell["height"] + 1, (name, box, shell)
        assert box["x"] + box["width"] <= 1280, (name, box)
        assert box["y"] + box["height"] <= 720, (name, box)
        bounds.append((name, box))
    for index, (name, box) in enumerate(bounds):
        for other_name, other in bounds[index + 1:]:
            overlap_x = min(box["x"] + box["width"], other["x"] + other["width"]) - max(box["x"], other["x"])
            overlap_y = min(box["y"] + box["height"], other["y"] + other["height"]) - max(box["y"], other["y"])
            assert overlap_x <= 1 or overlap_y <= 1, (name, other_name, box, other)
    assert page.locator("#audioTimeLabel").evaluate(
        "node => node.scrollWidth <= node.clientWidth + 1"
    )


def _assert_first_segment_body_fits_initial_list(page):
    listing = page.locator("#transcriptList")
    assert listing.evaluate("node => node.scrollTop") <= 1
    list_box = listing.bounding_box()
    body_box = listing.locator(".transcript-row-text").first.bounding_box()
    assert list_box and body_box
    assert body_box["y"] >= list_box["y"] - 1, (body_box, list_box)
    assert body_box["y"] + body_box["height"] <= list_box["y"] + list_box["height"] + 1, (body_box, list_box)


@pytest.mark.parametrize("legacy_text_import", [False, True], ids=["plain-text", "text-import"])
def test_persisted_text_and_audio_have_distinct_time_and_restore_without_stale_source(
    legacy_text_import,
):
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                _login(page, server.base_url)
                owner_id = page.request.get(server.base_url + "/api/auth/me").json()["id"]
                uploaded = page.request.post(
                    server.base_url + "/api/audio/upload?recognition_mode=fast",
                    multipart={"file": {
                        "name": "synthetic-source-timing.wav",
                        "mimeType": "audio/wav", "buffer": _silent_wav(),
                    }},
                )
                assert uploaded.ok
                audio_id = uploaded.json()["audio_id"]
                text_source = {
                    "audio_id": "text-import", "text": TEXT,
                    "conversation_text": TEXT,
                    # Legacy imports may carry segment-shaped placeholders;
                    # these are not evidence of recorded audio or real timing.
                    "segments": [
                        {"segment_id": "legacy-text-0", "start": 0, "end": 1,
                         "role": "医生", "text": "这两天有什么不舒服？"},
                        {"segment_id": "legacy-text-1", "start": 60, "end": 61,
                         "role": "患者", "text": "文本病例咳嗽两天，没有药物过敏史。"},
                    ],
                } if legacy_text_import else None
                text_id = _saved_encounter(
                    server, owner_id, "SIM-SOURCE-TEXT", "text", TEXT, text_source
                )
                audio_id_encounter = _saved_encounter(
                    # A completed audio-to-record task also uses text input;
                    # its persisted ASR source, not input_type, identifies audio.
                    server, owner_id, "SIM-SOURCE-AUDIO", "text", AUDIO_TEXT,
                    {"audio_id": audio_id, "engine": "mock", "duration": 65,
                     "text": AUDIO_TEXT, "conversation_text": AUDIO_TEXT,
                     "segments": [
                         {"segment_id": "audio-zero", "start": 0, "end": 3,
                          "text": "音频病例发热两天。", "role": "患者",
                          "speaker_id": "speaker-0", "reviewed_by_doctor": True},
                         {"segment_id": "audio-sixty", "start": 60, "end": 64,
                          "text": "没有胸痛。", "role": "患者",
                          "speaker_id": "speaker-0", "reviewed_by_doctor": True},
                         {"segment_id": "audio-untimed",
                          "text": "另有未记录时间的说明。", "role": "患者",
                          "speaker_id": "speaker-0", "reviewed_by_doctor": True},
                     ]},
                )
                # From this point the user only opens, reads and seeks sources.
                # Restoring or switching must not silently generate/transcribe.
                mutating_requests = []
                page.on("request", lambda request: mutating_requests.append(
                    (request.method, urlsplit(request.url).path)
                ) if request.method not in {"GET", "HEAD", "OPTIONS"} else None)

                _open_from_workbench(page, text_id)
                _assert_text_source(page)
                _assert_text_detail(page)
                page.reload()
                _assert_text_source(page)

                _open_from_workbench(page, audio_id_encounter)
                expect(page.locator("#transcriptHeading")).to_have_text("问诊转写")
                expect(page.locator("#transcriptSourceNotice")).not_to_be_visible()
                expect(page.locator("#consultationAudioPlayer")).to_be_visible()
                rows = page.locator("#transcriptList .transcript-table-row")
                expect(rows).to_have_count(3)
                expect(rows.nth(0).locator(".transcript-row-time")).to_have_text("00:00")
                expect(rows.nth(1).locator(".transcript-row-time")).to_have_text("01:00")
                expect(rows.nth(2).locator(".transcript-row-time")).to_have_text("时间未记录")
                assert rows.nth(2).get_attribute("data-segment-start") is None
                page.wait_for_function(
                    "document.querySelector('#consultationAudio').duration >= 64.9"
                )
                expect(page.locator("#audioTimeLabel")).to_contain_text("01:05")
                _assert_player_controls_fit(page)
                _assert_first_segment_body_fits_initial_list(page)
                rows.nth(1).locator(".transcript-row-link").click()
                expect(page.locator("#detailDrawerContent .transcript-row-time")).to_have_text(
                    ["00:00", "01:00", "时间未记录"]
                )
                page.locator("#closeDrawerButton").click()
                rows.nth(1).locator(".transcript-row-time").click()
                page.wait_for_function(
                    "document.querySelector('#consultationAudio').currentTime >= 60"
                )
                page.get_by_role("button", name="暂停音频", exact=True).click()
                current_time = page.locator("#consultationAudio").evaluate("audio => audio.currentTime")
                assert 60 <= current_time < 64

                # Audio's follow mode must not hide a subsequent text-only source.
                page.locator('[data-transcript-pace="follow"]').click()
                _open_from_workbench(page, text_id)
                _assert_text_source(page)
                page.reload()
                _assert_text_source(page)
                assert mutating_requests == []
            finally:
                browser.close()
    finally:
        server.close()
