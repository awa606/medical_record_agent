"""Review and export an isolated synthetic Alpha 5.1 task in the doctor UI.

This is for a throwaway local run only. It refuses to approve conflicting fields
and writes private screenshots and DOCX to an ignored output directory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_doctor_itemized_approval_playwright import _select_all_review_items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--encounter-id", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--assert-old-approval-invalid", action="store_true")
    parser.add_argument("--text-case", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {"status": "started", "encounter_id": args.encounter_id}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.goto(args.base_url + "/static/doctor.html", wait_until="networkidle")
            page.locator("#loginUsername").fill("admin")
            page.locator("#loginPassword").fill(args.password_file.read_text(encoding="utf-8").strip())
            page.locator("#loginForm button[type='submit']").click()
            page.locator("#authUserLabel").wait_for(timeout=10000)
            page.wait_for_function(
                "window.__MRA_APP_STATE__?.authUser?.username === 'admin' "
                "&& window.__MRA_APP_STATE__?.encounterWorklistStatus === 'ready' "
                "&& !window.__MRA_APP_STATE__?.busy",
                timeout=15000,
            )
            result["encounter_http_status"] = page.evaluate(
                "async (id) => (await fetch(`/api/encounters/${id}`)).status",
                args.encounter_id,
            )
            page.evaluate("(id) => restoreEncounter(id)", args.encounter_id)
            result["restored_state"] = page.evaluate(
                """() => {const s=window.__MRA_APP_STATE__; return {
                  encounter_id:s?.currentEncounter?.id, task_id:s?.currentTaskId,
                  task_status:s?.taskStatus, current_stage:s?.currentTask?.current_stage,
                  has_fields:Boolean(s?.currentRecordFields), action_error:s?.actionError?.message || s?.actionError || null};}"""
            )
            if not result["restored_state"]["has_fields"]:
                page.screenshot(path=str(args.output_dir / "restore-failed.png"), full_page=True)
                raise RuntimeError("restored encounter has no record fields")
            result["task_id"] = page.evaluate("window.__MRA_APP_STATE__.currentTaskId")
            field_statuses = page.evaluate(
                """() => Object.fromEntries(Object.entries(window.__MRA_APP_STATE__.currentRecordFields || {})
                  .filter(([key, field]) => field && typeof field === 'object' && 'status' in field)
                  .map(([key, field]) => [key, field.status]))"""
            )
            result["field_statuses"] = field_statuses
            if any(status == "conflicting" for key, status in field_statuses.items()
                   if not (args.text_case and key == "chief_complaint")):
                raise RuntimeError("conflicting field blocks synthetic approval")
            readiness_before = page.evaluate("window.__MRA_APP_STATE__?.currentExportReadiness?.revision_id")
            page.locator("#editRecordButton").click()
            page.locator('[data-record-field-input="chief_complaint"]').fill(
                "今日发热伴咳嗽、咽痛。" if args.text_case else "发热伴咳嗽。"
            )
            page.locator("#saveDraftButton").click()
            page.wait_for_function("!window.__MRA_APP_STATE__.recordEditMode", timeout=15000)
            page.wait_for_function(
                "(old) => Number(window.__MRA_APP_STATE__?.currentExportReadiness?.revision_id) > Number(old)",
                arg=readiness_before, timeout=15000,
            )
            result["revision_before"] = readiness_before
            result["revision_after"] = page.evaluate("window.__MRA_APP_STATE__?.currentExportReadiness?.revision_id")
            result["field_statuses_after_edit"] = page.evaluate(
                """() => Object.fromEntries(Object.entries(window.__MRA_APP_STATE__.currentRecordFields || {})
                  .filter(([key, field]) => field && typeof field === 'object' && 'status' in field)
                  .map(([key, field]) => [key, field.status]))"""
            )
            if any(status == "conflicting" for status in result["field_statuses_after_edit"].values()):
                raise RuntimeError("conflicting field remains after doctor edit")
            if args.assert_old_approval_invalid:
                result["old_approval_export_status"] = page.evaluate(
                    """async () => (await fetch(`/api/tasks/${window.__MRA_APP_STATE__.currentTaskId}/export`,
                      {method:'POST'})).status"""
                )
                if result["old_approval_export_status"] not in {400, 409}:
                    raise RuntimeError("old approval unexpectedly allowed export")
            _select_all_review_items(page)
            page.locator("#confirmFieldsButton").click()
            page.wait_for_function(
                "window.__MRA_APP_STATE__?.currentTask?.current_stage === 'approved'",
                timeout=30000,
            )
            result["approved"] = True
            with page.expect_download(timeout=30000) as download_info:
                page.locator("#exportButton").click()
            download = download_info.value
            docx = args.output_dir / download.suggested_filename
            download.save_as(docx)
            with ZipFile(docx) as archive:
                result["docx_valid"] = "word/document.xml" in archive.namelist()
            result["docx_size_bytes"] = docx.stat().st_size
            result["exported"] = bool(result["docx_valid"])
            page.screenshot(path=str(args.output_dir / "approved-exported.png"), full_page=True)
            result["status"] = "passed" if result["exported"] else "failed"
            browser.close()
    except Exception as exc:
        result["status"] = "failed"
        result["failure"] = f"{type(exc).__name__}: {exc}"
    (args.output_dir / "review-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in result.items() if key != "failure"}, ensure_ascii=False))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
