from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright
from tests.auth_helpers import DEFAULT_ADMIN_PASSWORD


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str) -> None:
    import urllib.request

    last_error = None
    for _ in range(80):
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
        self.root = Path(self.temp_dir.name)
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["MEDICAL_RECORD_AGENT_DB"] = str(self.root / "edge.sqlite3")
        env["MEDICAL_RECORD_AGENT_UPLOAD_DIR"] = str(self.root / "uploads")
        env["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = str(self.root / "outputs")
        env["LLM_PROVIDER"] = "mock"
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
    page.fill("#loginPassword", DEFAULT_ADMIN_PASSWORD)
    page.click("#loginForm button[type='submit']")
    expect(page.locator("#authUserLabel")).to_contain_text("admin")


def _prepare_review_fixture(page) -> int:
    page.evaluate("createRecordTask('患者发热39度，胸闷气促，青霉素过敏。')")
    page.wait_for_function("window.__MRA_APP_STATE__?.currentRecordFields", timeout=30000)
    page.wait_for_function("window.__MRA_APP_STATE__?.eventSource === null", timeout=30000)
    page.evaluate(
        """
        async () => {
          const state = window.__MRA_APP_STATE__;
          const fields = state.currentRecordFields;
          fields.chief_complaint.value = '发热伴胸闷气促';
          fields.chief_complaint.missing = false;
          fields.chief_complaint.status = 'partial';
          fields.chief_complaint.doctor_review_status = 'pending';
          fields.present_illness.value = null;
          fields.present_illness.missing = true;
          fields.present_illness.status = 'missing';
          fields.present_illness.hint = '本次未采集起病时间';
          fields.physical_exam.value = '体温39度，胸闷气促';
          fields.physical_exam.missing = false;
          fields.physical_exam.status = 'conflicting';
          fields.physical_exam.source_spans = [{ text: '患者发热39度，胸闷气促', segment_id: null, index: 0 }];
          fields.physical_exam.fact_ids = ['fact-browser-high-risk'];
          fields.physical_exam.doctor_review_status = 'pending';
          fields.physical_exam.high_risk_confirmed_by_doctor = false;
          const existingDiagnosis = (fields.candidate_diagnoses || [])[0] || {};
          fields.candidate_diagnoses = [{
            ...existingDiagnosis,
            name: existingDiagnosis.name || '肺部感染待排',
            confidence: 0.76,
            evidence: existingDiagnosis.evidence?.length
              ? existingDiagnosis.evidence
              : [{ text: '患者发热39度，胸闷气促', segment_id: null, index: 0 }],
            risk_warnings: ['胸闷气促需医生及时评估'],
            doctor_review_status: 'pending',
            high_risk_confirmed_by_doctor: false
          }];
          const task = await api(`/api/tasks/${state.currentTaskId}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fields })
          });
          await refreshTask(state.currentTaskId, task);
          await refreshExportReadiness();
          setProductView('encounter');
          renderAll();
        }
        """
    )
    page.wait_for_function("window.__MRA_APP_STATE__?.currentExportReadiness?.revision_id", timeout=15000)
    return int(page.evaluate("window.__MRA_APP_STATE__.currentTaskId"))


def _select_all_review_items(page) -> None:
    page.evaluate("syncApprovalReviewStateWithRevision(window.__MRA_APP_STATE__.currentExportReadiness)")
    page.locator("#recordFields [data-approval-confirm-regular]").click()
    missing_keys = page.evaluate(
        """
        () => [...document.querySelectorAll('#recordFields [data-approval-missing-key][data-approval-action="accept_missing"]')]
          .map((button) => button.dataset.approvalMissingKey)
        """
    )
    for key in missing_keys:
        page.evaluate(
            """
            (key) => {
              const button = [...document.querySelectorAll('#recordFields [data-approval-missing-key]')]
                .find((item) => item.dataset.approvalMissingKey === key && item.dataset.approvalAction === 'accept_missing');
              button?.click();
            }
            """,
            key,
        )
    diagnosis_indexes = page.evaluate(
        """
        () => [...document.querySelectorAll('#recordFields [data-approval-diagnosis-index][data-approval-action="confirm_candidate"]')]
          .map((button) => button.dataset.approvalDiagnosisIndex)
        """
    )
    for index in diagnosis_indexes:
        page.evaluate(
            """
            (index) => {
              const button = [...document.querySelectorAll('#recordFields [data-approval-diagnosis-index]')]
                .find((item) => item.dataset.approvalDiagnosisIndex === index && item.dataset.approvalAction === 'confirm_candidate');
              button?.click();
            }
            """,
            index,
        )
    risk_keys = page.evaluate(
        """
        () => [...document.querySelectorAll('#recordFields [data-approval-risk-key]')]
          .map((button) => button.dataset.approvalRiskKey)
        """
    )
    for key in risk_keys:
        page.evaluate(
            """
            (key) => {
              const button = [...document.querySelectorAll('#recordFields [data-approval-risk-key]')]
                .find((item) => item.dataset.approvalRiskKey === key);
              button?.click();
            }
            """,
            key,
        )


def test_itemized_approval_invalidates_after_edit_and_downloads_docx() -> None:
    server = RunningServer()
    download_dir = Path(tempfile.mkdtemp(prefix="mra-itemized-downloads-"))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            _login(page, server.base_url)

            task_id = _prepare_review_fixture(page)
            expect(page.locator(".approval-checklist")).to_be_visible()
            expect(page.locator(".approval-item")).not_to_have_count(0)

            empty_status = page.evaluate(
                """async () => {
                  const response = await fetch(`/api/tasks/${window.__MRA_APP_STATE__.currentTaskId}/approve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}'
                  });
                  return response.status;
                }"""
            )
            assert empty_status in {400, 422}

            _select_all_review_items(page)
            stale_payload = page.evaluate("buildTaskApprovalPayload()")
            page.evaluate("confirmFields()")
            page.wait_for_function("window.__MRA_APP_STATE__?.currentTask?.current_stage === 'approved'", timeout=15000)
            first_revision = int(stale_payload["revision_id"])

            page.evaluate(
                """
                async () => {
                  const fields = window.__MRA_APP_STATE__.currentRecordFields;
                  fields.chief_complaint.value = `${fields.chief_complaint.value}，医生补充记录`;
                  await saveDraftReview();
                  await refreshExportReadiness();
                }
                """
            )
            page.wait_for_function(
                "(oldRevision) => Boolean(window.__MRA_APP_STATE__?.currentExportReadiness?.revision_id) && Number(window.__MRA_APP_STATE__.currentExportReadiness.revision_id) !== oldRevision",
                arg=first_revision,
                timeout=15000,
            )
            new_revision = int(page.evaluate("window.__MRA_APP_STATE__.currentExportReadiness.revision_id"))
            assert new_revision != first_revision

            stale_status = page.evaluate(
                """async (payload) => {
                  const response = await fetch(`/api/tasks/${window.__MRA_APP_STATE__.currentTaskId}/approve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                  });
                  return response.status;
                }""",
                stale_payload,
            )
            assert stale_status == 409

            export_status = page.evaluate(
                """async () => {
                  const response = await fetch(`/api/tasks/${window.__MRA_APP_STATE__.currentTaskId}/export`, { method: 'POST' });
                  return response.status;
                }"""
            )
            assert export_status == 400

            _select_all_review_items(page)
            page.evaluate("confirmFields()")
            page.wait_for_function("window.__MRA_APP_STATE__?.currentTask?.current_stage === 'approved'", timeout=15000)

            with page.expect_download(timeout=30000) as download_info:
                page.evaluate("exportRecord()")
            download = download_info.value
            docx_path = download_dir / download.suggested_filename
            download.save_as(docx_path)
            assert docx_path.exists()
            assert docx_path.stat().st_size > 0
            with ZipFile(docx_path) as docx:
                assert "word/document.xml" in docx.namelist()
                document_xml = docx.read("word/document.xml").decode("utf-8")
            assert "医生补充记录" in document_xml

            task_status = page.evaluate(
                """async (taskId) => {
                  const task = await fetch(`/api/tasks/${taskId}`).then((response) => response.json());
                  return task.current_stage;
                }""",
                task_id,
            )
            assert task_status in {"approved", "exported"}
            browser.close()
    finally:
        server.close()
