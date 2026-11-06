"""Run the synthetic text path against an already-ready local Alpha 5.1 server.

All output stays in an ignored .artifacts directory. This does not approve or
export a medical record; those gates are reported separately after inspection.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


CASE = (
    "[医生] 今天哪里不舒服？\n"
    "[患者] 今天发热，体温三十八点二度，伴咳嗽和咽痛。\n"
    "[医生] 有没有胸痛？有花生或药物过敏史吗？\n"
    "[患者] 没有胸痛。我没有花生过敏，也没有药物过敏史。"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    password = args.password_file.read_text(encoding="utf-8").strip()
    result: dict[str, object] = {"path": "text", "provider_expected": "ollama/qwen3:4b", "status": "started"}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.goto(args.base_url + "/static/doctor.html", wait_until="networkidle")
            page.locator("#loginUsername").fill("admin")
            page.locator("#loginPassword").fill(password)
            page.locator("#loginForm button[type='submit']").click()
            page.locator("#authUserLabel").wait_for(timeout=10000)
            page.locator("#localPatientDeidentifiedId").fill(f"SIM-ALPHA51-FEVER-{int(time.time())}")
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
            page.locator('#encounterView [data-input-method="text"]').click()
            page.locator("#conversationInput").fill(CASE)
            page.locator("#submitTextButton").click()
            page.wait_for_function("Boolean(window.__MRA_APP_STATE__?.currentTaskId)", timeout=30000)
            result["task_id"] = page.evaluate("window.__MRA_APP_STATE__.currentTaskId")
            page.wait_for_function(
                "Boolean(window.__MRA_APP_STATE__?.currentRecordFields) || window.__MRA_APP_STATE__?.taskStatus === 'FAILED'",
                timeout=240000,
            )
            result["task_status"] = page.evaluate("window.__MRA_APP_STATE__.taskStatus")
            result["fields_present"] = bool(page.evaluate("window.__MRA_APP_STATE__.currentRecordFields"))
            result["field_statuses"] = page.evaluate(
                """() => Object.fromEntries(Object.entries(window.__MRA_APP_STATE__.currentRecordFields || {})
                  .filter(([key, field]) => field && typeof field === 'object' && 'status' in field)
                  .map(([key, field]) => [key, field.status]))"""
            )
            result["provider_trace"] = page.evaluate(
                """() => {
                  const task = window.__MRA_APP_STATE__.currentTask || {};
                  return {status: task.status, current_stage: task.current_stage,
                    provider: task.provider, model: task.model, fallback: task.fallback};
                }"""
            )
            page.screenshot(path=str(args.output_dir / "text-path-after-generate.png"), full_page=True)
            result["status"] = "generated" if result["fields_present"] else "failed"
            browser.close()
    except Exception as exc:
        result["status"] = "failed"
        result["failure"] = f"{type(exc).__name__}: {exc}"
    (args.output_dir / "text-path-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in result.items() if key != "failure"}, ensure_ascii=False))
    if result["status"] != "generated":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
