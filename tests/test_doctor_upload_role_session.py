"""Visible upload controls must retain a writable role-review session."""
from __future__ import annotations

import io
import json
import wave

import pytest
from playwright.sync_api import expect, sync_playwright

from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


@pytest.mark.parametrize("mode", ["fast", "follow"])
def test_uploaded_audio_can_save_role_review_after_generation_gate(mode):
    server = RunningServer({"MEDICAL_RECORD_AGENT_ASR_ENGINE": "mock",
                            "ASR_SESSION_REALTIME_UPLOAD_ENABLED": "0"})
    try:
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\x00\x00" * 16000)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)
            page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
            page.click("#createLocalEncounterButton")
            row = page.locator("#dashboardEncounterList article").filter(has_text="张示例")
            row.get_by_role("button", name="开始接诊", exact=True).click()
            responses = []
            page.on("response", lambda response: responses.append(response))
            # Force the existing 409 recovery path; ASR and PATCH use real local APIs.
            page.route("**/api/audio/*/generate-record*", lambda route: route.fulfill(
                status=409, content_type="application/json", body=json.dumps({"detail": {
                    "role_quality": {"status": "needs_review", "reasons": ["请确认说话人身份"]}
                }})))
            page.locator('#encounterView [data-input-method="audio"]').click()
            page.locator("#audioFileInput").set_input_files({
                "name": "role-session.wav", "mimeType": "audio/wav", "buffer": audio.getvalue(),
            })
            page.select_option("#recognitionModeSelect", mode)
            page.click("#submitAudioButton")
            recovery = page.locator('[data-workflow-action="open-role-review"]')
            expect(recovery).to_be_visible(timeout=30000)
            recovery.click()
            save = page.locator("[data-save-role-review]")
            expect(save).to_be_visible()
            expect(page.locator("#detailDrawerContent")).not_to_contain_text("当前内容只读")
            roles = page.locator("[data-speaker-role-select]")
            assert roles.count() >= 1
            # The mock doctor's role can already be reliable; confirm only pending groups.
            for role in roles.all():
                speaker = role.get_attribute("data-speaker-id") or ""
                role.select_option(label="医生" if speaker in {"医生", "doctor"} else "患者")
            with page.expect_response(lambda response: response.request.method == "PATCH"
                                      and "/api/asr/sessions/" in response.url) as saved:
                save.click()
            assert saved.value.status == 200
            assert saved.value.json()["asr_result"]["role_quality"]["status"] == "passed"
            created = [r for r in responses if r.request.method == "POST"
                       and "/api/asr/sessions?" in r.url]
            assert len(created) == 1
            assert created[0].json()["recognition_mode"] == mode
            browser.close()
    finally:
        server.close()
