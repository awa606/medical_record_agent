"""Persisted text/audio source presentation; isolated API and synthetic media.

The WAV is silence used only to test duration/seeking. ASR segments are explicit
stored fixtures, not recognition output, and no model request is made here.
"""
from __future__ import annotations

import io
import json
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


def _saved_encounter(server, owner_id, patient_id, input_type, text, asr_source=None):
    result = {"conversation_text": text, "fields": {}, "draft": ""}
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
        "文本输入 · 未关联录音\n本病例没有音频时间"
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
