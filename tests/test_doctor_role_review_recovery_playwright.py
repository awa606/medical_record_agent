from __future__ import annotations

import json

from playwright.sync_api import expect, sync_playwright

from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


def _inject_role_result(page, *, status: str) -> None:
    needs_review = status != "passed"
    page.evaluate(
        """
        ({ status, needsReview }) => {
          const state = window.__MRA_APP_STATE__;
          const manual = status === "passed";
          state.currentTaskId = null;
          state.currentTask = null;
          state.currentAudioId = "role-audio";
          state.currentAsrSessionId = "role-session";
          state.currentRecordFields = null;
          state.currentDraft = "";
          state.taskStatus = "TRANSCRIBED";
          state.busy = false;
          state.lastActionError = needsReview ? "speaker role quality gate failed" : "";
          state.viewMode = "doctor";
          state.currentAsrResult = {
            audio_id: "role-audio",
            text: "anonymous role-gate fixture",
            conversation_text: "anonymous role-gate fixture",
            segments: [
              {
                segment_id: "seg-doctor",
                speaker: "spk0",
                speaker_id: "spk0",
                role: manual ? "医生" : null,
                text: "anonymous prompt",
                reviewed_by_doctor: manual,
                needs_review: needsReview,
              },
              {
                segment_id: "seg-patient",
                speaker: "spk1",
                speaker_id: "spk1",
                role: manual ? "患者" : null,
                text: "anonymous response",
                reviewed_by_doctor: manual,
                needs_review: needsReview,
              },
            ],
            speaker_assignments: [
              {
                speaker_id: "spk0",
                role: manual ? "医生" : null,
                confidence: manual ? 0.99 : 0,
                source: manual ? "manual_speaker_map" : "unassigned",
                requires_confirmation: needsReview,
              },
              {
                speaker_id: "spk1",
                role: manual ? "患者" : null,
                confidence: manual ? 0.99 : 0,
                source: manual ? "manual_speaker_map" : "unassigned",
                requires_confirmation: needsReview,
              },
            ],
            role_quality: {
              status,
              reasons: needsReview ? ["请医生确认说话人身份"] : [],
              pending_confirmation: needsReview
                ? [{ speaker_id: "spk0" }, { speaker_id: "spk1" }]
                : [],
              unresolved_assignments: needsReview
                ? [{ speaker_id: "spk0" }, { speaker_id: "spk1" }]
                : [],
              low_confidence_clinical_roles: [],
              unmapped_speakers: [],
            },
          };
          state.liveTranscriptSegments = state.currentAsrResult.segments;
          state.speakerAssignments = state.currentAsrResult.speaker_assignments;
          state.speakerMappingRequired = needsReview;
          state.roleReviewDirty = false;
          state.pendingGenerateAfterRoleReview = needsReview;
          window.setProductView("encounter");
          window.renderAll();
        }
        """,
        {"status": status, "needsReview": needs_review},
    )


def test_role_review_recovery_action_only_appears_when_quality_gate_requires_it() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)

            _inject_role_result(page, status="needs_review")
            recovery = page.locator('[data-workflow-action="open-role-review"]')
            expect(recovery).to_have_text("确认说话人身份")
            expect(recovery).to_be_visible()
            assert page.evaluate("roleReviewPendingCount()") == 2
            recovery.click()
            expect(page.locator("#drawerTitle")).to_have_text("说话人身份确认")

            page.locator("#closeDrawerButton").click()
            _inject_role_result(page, status="passed")
            expect(page.locator('[data-workflow-action="open-role-review"]')).to_have_count(0)
            expect(page.locator('[data-workflow-action="generate-record"]')).to_be_visible()
            assert page.evaluate("roleReviewRequired()") is False

            browser.close()
    finally:
        server.close()


def test_409_recovery_cannot_bypass_gate_and_continues_only_after_patch_passes() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            _login(page, server.base_url)
            _inject_role_result(page, status="passed")

            calls = {"generate": 0, "patch": 0}

            def route_generation(route) -> None:
                calls["generate"] += 1
                if calls["generate"] == 1:
                    route.fulfill(
                        status=409,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "detail": {
                                    "message": "Speaker role quality gate did not pass.",
                                    "policy_version": "speaker-role-policy-v1",
                                    "reason_code": "unmapped_speaker",
                                    "pending_confirmation": [
                                        {"speaker_id": "spk0", "action": "needs_review"},
                                        {"speaker_id": "spk1", "action": "needs_review"},
                                    ],
                                    "role_quality": {
                                        "status": "needs_review",
                                        "policy_version": "speaker-role-policy-v1",
                                        "reasons": ["请医生确认说话人身份"],
                                        "pending_confirmation": [
                                            {"speaker_id": "spk0", "action": "needs_review"},
                                            {"speaker_id": "spk1", "action": "needs_review"},
                                        ],
                                        "unresolved_assignments": [],
                                        "low_confidence_clinical_roles": [],
                                        "unmapped_speakers": [],
                                    },
                                }
                            },
                            ensure_ascii=False,
                        ),
                    )
                    return
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "task_id": 2301,
                            "status": "CREATED",
                            "events_url": "/api/tasks/2301/events",
                        }
                    ),
                )

            def route_patch(route) -> None:
                calls["patch"] += 1
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "session_id": "role-session",
                            "audio_id": "role-audio",
                            "status": "reviewed",
                            "updated_at": "2026-09-19T00:00:00Z",
                            "asr_result": {
                                "audio_id": "role-audio",
                                "engine": "funasr-paraformer-zh",
                                "text": "anonymous role-gate fixture",
                                "conversation_text": "anonymous role-gate fixture",
                                "segments": [
                                    {
                                        "segment_id": "seg-doctor",
                                        "speaker": "spk0",
                                        "speaker_id": "spk0",
                                        "role": "医生",
                                        "text": "anonymous prompt",
                                        "role_source": "manual_speaker_map",
                                        "role_confidence": 0.98,
                                        "reviewed_by_doctor": True,
                                        "needs_review": False,
                                    },
                                    {
                                        "segment_id": "seg-patient",
                                        "speaker": "spk1",
                                        "speaker_id": "spk1",
                                        "role": "患者",
                                        "text": "anonymous response",
                                        "role_source": "manual_speaker_map",
                                        "role_confidence": 0.98,
                                        "reviewed_by_doctor": True,
                                        "needs_review": False,
                                    },
                                ],
                                "speaker_assignments": [
                                    {
                                        "speaker_id": "spk0",
                                        "role": "医生",
                                        "confidence": 0.99,
                                        "source": "manual_speaker_map",
                                        "requires_confirmation": False,
                                    },
                                    {
                                        "speaker_id": "spk1",
                                        "role": "患者",
                                        "confidence": 0.99,
                                        "source": "manual_speaker_map",
                                        "requires_confirmation": False,
                                    },
                                ],
                                "role_quality": {
                                    "status": "passed",
                                    "policy_version": "speaker-role-policy-v1",
                                    "reasons": [],
                                    "pending_confirmation": [],
                                    "unresolved_assignments": [],
                                    "low_confidence_clinical_roles": [],
                                    "unmapped_speakers": [],
                                },
                            },
                        },
                        ensure_ascii=False,
                    ),
                )

            page.route("**/api/audio/role-audio/generate-record*", route_generation)
            page.route("**/api/asr/sessions/role-session/result", route_patch)

            page.evaluate("startRecordGenerationFromAudio('role-audio')")
            expect(page.locator('[data-workflow-action="open-role-review"]')).to_be_visible()
            assert page.evaluate("window.__MRA_APP_STATE__.currentTaskId") is None
            assert calls["generate"] == 1

            page.evaluate(
                """
                () => {
                  const state = window.__MRA_APP_STATE__;
                  state.speakerRoleCorrections = { spk0: "医生", spk1: "患者" };
                  state.currentAsrResult.segments.forEach((segment) => {
                    segment.role = state.speakerRoleCorrections[segment.speaker_id];
                    segment.reviewed_by_doctor = true;
                    segment.needs_review = false;
                  });
                  state.roleReviewDirty = true;
                  renderAll();
                }
                """
            )
            page.evaluate("saveRoleReview()")
            page.wait_for_function("window.__MRA_APP_STATE__.currentTaskId === 2301")

            assert calls == {"generate": 2, "patch": 1}
            assert page.evaluate("roleReviewRequired()") is False
            expect(page.locator('[data-workflow-action="open-role-review"]')).to_have_count(0)

            browser.close()
    finally:
        server.close()
