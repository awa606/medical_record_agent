from __future__ import annotations

import json
import os
from contextlib import contextmanager

from playwright.sync_api import expect, sync_playwright

from app.db import bind_task_to_encounter, create_task, get_connection, update_task
from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


@contextmanager
def _server_database(server: RunningServer):
    previous = os.environ.get("MEDICAL_RECORD_AGENT_DB")
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(server.root / "edge.sqlite3")
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        else:
            os.environ["MEDICAL_RECORD_AGENT_DB"] = previous


def _set_backend_state(
    server: RunningServer,
    *,
    task_id: int,
    encounter_id: int,
    task_status: str,
    current_stage: str,
    encounter_status: str,
    with_fields: bool = False,
) -> None:
    result = {
        "fields": {} if with_fields else None,
        "draft": "匿名病历草稿" if with_fields else "",
    }
    with _server_database(server):
        update_task(
            task_id,
            status=task_status,
            current_stage=current_stage,
            result_json=json.dumps(result, ensure_ascii=False),
        )
        with get_connection() as connection:
            connection.execute(
                "UPDATE encounter SET status = ? WHERE id = ?",
                (encounter_status, encounter_id),
            )
            connection.commit()


def _observed_workflow(page, encounter_id: int) -> dict[str, str]:
    page.evaluate("(id) => restoreEncounter(id)", encounter_id)
    page.wait_for_function(
        "(id) => window.__MRA_APP_STATE__?.currentEncounter?.id === id",
        arg=encounter_id,
        timeout=15000,
    )
    page.evaluate("refreshEncounterWorklist()")
    page.wait_for_function("window.__MRA_APP_STATE__?.encounterWorklistStatus === 'ready'", timeout=15000)
    return page.evaluate(
        """
        () => ({
          displayState: document.body.dataset.displayState,
          worklistState: document.querySelector('.encounter-worklist-item.active')?.dataset.workflowState || '',
          phase: document.querySelector('.encounter-worklist-item.active .encounter-worklist-meta span:nth-child(3)')?.innerText || '',
          nextAction: document.querySelector('#nextActionPanel strong')?.innerText || '',
          activeStep: document.querySelector('.workflow-step.active .workflow-label')?.innerText || '',
        })
        """
    )


def test_backend_aliases_drive_one_consistent_doctor_workflow_state() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            _login(page, server.base_url)

            page.fill("#localPatientDeidentifiedId", "SIM-WORKFLOW-STATE")
            page.fill("#localPatientDisplayName", "匿名状态流样本")
            page.click("#createLocalEncounterButton")
            page.wait_for_function("window.__MRA_APP_STATE__?.currentEncounter?.id")
            encounter_id = int(page.evaluate("window.__MRA_APP_STATE__.currentEncounter.id"))
            owner_id = int(page.evaluate("window.__MRA_APP_STATE__.authUser.id"))

            with _server_database(server):
                task_id = create_task(
                    input_type="audio",
                    status="TRANSCRIBING",
                    current_stage="transcribing",
                    input_text="匿名状态流契约样本",
                )
                bind_task_to_encounter(task_id, encounter_id, owner_user_id=owner_id)

            cases = [
                {
                    "task_status": "TRANSCRIBING",
                    "current_stage": "transcribing",
                    "encounter_status": "draft",
                    "with_fields": False,
                    "state": "transcribing",
                    "phase": "智能转写",
                    "next_action": "智能转写中",
                    "step": "AI处理",
                },
                {
                    "task_status": "EXTRACTING_FIELDS",
                    "current_stage": "extract_fields",
                    "encounter_status": "draft",
                    "with_fields": False,
                    "state": "generating",
                    "phase": "生成病历",
                    "next_action": "病历生成中",
                    "step": "AI处理",
                },
                {
                    "task_status": "WAITING_DOCTOR_REVIEW",
                    "current_stage": "doctor_review",
                    "encounter_status": "pending_review",
                    "with_fields": True,
                    "state": "draft_generated",
                    "phase": "草稿已生成",
                    "next_action": "病历草稿已生成，可编辑",
                    "step": "病历审核",
                },
                {
                    "task_status": "WAITING_DOCTOR_REVIEW",
                    "current_stage": "waiting_doctor_review",
                    "encounter_status": "pending_review",
                    "with_fields": True,
                    "state": "pending_review",
                    "phase": "等待医生审核",
                    "next_action": "等待医生审核",
                    "step": "病历审核",
                },
                {
                    "task_status": "DONE",
                    "current_stage": "approved",
                    "encounter_status": "approved",
                    "with_fields": True,
                    "state": "approved",
                    "phase": "病历已审核",
                    "next_action": "病历审核已完成，可以导出",
                    "step": "导出完成",
                },
                {
                    "task_status": "FAILED",
                    "current_stage": "failed",
                    "encounter_status": "draft",
                    "with_fields": False,
                    "state": "failed",
                    "phase": "异常待处理",
                    "next_action": "流程中断",
                    "step": "AI处理",
                },
            ]

            for case in cases:
                _set_backend_state(
                    server,
                    task_id=task_id,
                    encounter_id=encounter_id,
                    task_status=case["task_status"],
                    current_stage=case["current_stage"],
                    encounter_status=case["encounter_status"],
                    with_fields=case["with_fields"],
                )
                observed = _observed_workflow(page, encounter_id)
                assert observed["displayState"] == case["state"], observed
                assert observed["worklistState"] == case["state"], observed
                assert case["phase"] in observed["phase"], observed
                assert observed["nextAction"] == case["next_action"], observed
                assert observed["activeStep"] == case["step"], observed

            expect(page.locator("[data-workflow-action='open-role-review']")).to_have_count(0)
            browser.close()
    finally:
        server.close()
