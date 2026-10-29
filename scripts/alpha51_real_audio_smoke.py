"""Exercise the uploaded-audio path in an isolated local-real Alpha 5.1 run.

The input must be an explicitly selected anonymous WAV; private output stays
under .artifacts. A blocked role or evidence gate is recorded as a failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--audio-file", type=Path, required=True)
    parser.add_argument("--recognition-mode", choices=("fast", "follow"), default="fast")
    parser.add_argument("--confirm-fever-fixture-roles", action="store_true",
                        help="Confirm spk0=patient and spk1=doctor for the authorized fever fixture only")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audio = args.audio_file.resolve()
    result: dict[str, object] = {
        "path": "uploaded_audio", "status": "started", "recognition_mode": args.recognition_mode,
        "input_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
        "input_size_bytes": audio.stat().st_size,
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.goto(args.base_url + "/static/doctor.html", wait_until="networkidle")
            page.locator("#loginUsername").fill("admin")
            page.locator("#loginPassword").fill(args.password_file.read_text(encoding="utf-8").strip())
            page.locator("#loginForm button[type='submit']").click()
            page.locator("#authUserLabel").wait_for(timeout=10000)
            page.locator("#localPatientDeidentifiedId").fill(f"SIM-ALPHA51-AUDIO-{int(time.time())}")
            page.locator("#localPatientDisplayName").fill("模拟患者")
            page.locator("#createLocalEncounterButton").click()
            page.wait_for_function("Boolean(window.__MRA_APP_STATE__?.currentEncounter?.id)")
            encounter_id = page.evaluate("window.__MRA_APP_STATE__.currentEncounter.id")
            result["encounter_id"] = encounter_id
            page.evaluate("(id) => performEncounterAction(id, 'check-in')", encounter_id)
            page.wait_for_function("window.__MRA_APP_STATE__?.currentEncounter?.check_in_status === 'checked_in'")
            page.evaluate("(id) => performEncounterAction(id, 'start')", encounter_id)
            page.wait_for_function("window.__MRA_APP_STATE__?.currentEncounter?.check_in_status === 'in_progress'")
            page.evaluate("setProductView('encounter'); renderAll()")
            page.locator('#encounterView [data-input-method="audio"]').click()
            page.locator("#audioFileInput").set_input_files(str(audio))
            page.locator("#recognitionModeSelect").select_option(args.recognition_mode)
            page.locator("#submitAudioButton").click()
            page.wait_for_function(
                "Boolean(window.__MRA_APP_STATE__?.currentAudioId) || Boolean(window.__MRA_APP_STATE__?.actionError)",
                timeout=180000,
            )
            page.wait_for_function(
                "Boolean(window.__MRA_APP_STATE__?.currentAsrResult?.engine) || "
                "Boolean(window.__MRA_APP_STATE__?.actionError) || "
                "window.__MRA_APP_STATE__?.taskStatus === 'FAILED'",
                timeout=180000,
            )
            result.update(page.evaluate(
                """() => {
                  const s = window.__MRA_APP_STATE__;
                  return {audio_id:s.currentAudioId, session_id:s.currentAsrSessionId,
                    asr_engine:s.currentAsrResult?.engine, transcript_length:(s.currentAsrResult?.conversation_text || '').length,
                    role_quality:s.currentAsrResult?.role_quality?.status || s.currentAsrResult?.role_quality,
                    role_review_required:Boolean(roleReviewRequired()), task_id:s.currentTaskId,
                    task_status:s.taskStatus, has_fields:Boolean(s.currentRecordFields),
                    action_error:s.actionError?.message || s.actionError || null};
                }"""
            ))
            if args.confirm_fever_fixture_roles and result.get("session_id") and result.get("role_review_required"):
                page.locator('#nextActionPanel [data-workflow-action="open-role-review"]').click()
                for speaker, role in (("spk0", "患者"), ("spk1", "医生")):
                    page.locator(f'[data-speaker-role-select][data-speaker-id="{speaker}"]').select_option("")
                    page.locator(f'[data-speaker-role-select][data-speaker-id="{speaker}"]').select_option(role)
                page.locator('#detailDrawerContent [data-save-role-review]').click()
                page.wait_for_function("roleQualityPassed(window.__MRA_APP_STATE__?.currentAsrResult)", timeout=30000)
                result["role_confirmed"] = True
                result["role_review_required_after"] = page.evaluate("roleReviewRequired()")
                page.wait_for_function("Boolean(window.__MRA_APP_STATE__?.currentTaskId)", timeout=30000)
                page.wait_for_function(
                    "Boolean(window.__MRA_APP_STATE__?.currentRecordFields) || window.__MRA_APP_STATE__?.taskStatus === 'FAILED'",
                    timeout=240000,
                )
                result["task_id"] = page.evaluate("window.__MRA_APP_STATE__?.currentTaskId")
                result["task_status"] = page.evaluate("window.__MRA_APP_STATE__?.taskStatus")
                result["has_fields"] = bool(page.evaluate("window.__MRA_APP_STATE__?.currentRecordFields"))
            page.screenshot(path=str(args.output_dir / "audio-path-after-submit.png"), full_page=True)
            result["status"] = "asr_completed" if str(result.get("asr_engine") or "").startswith("funasr") else "failed"
            browser.close()
    except Exception as exc:
        result["status"] = "failed"
        result["failure"] = f"{type(exc).__name__}: {exc}"
    (args.output_dir / "audio-path-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in result.items() if key not in {"failure", "action_error"}}, ensure_ascii=False))
    if result["status"] != "asr_completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
