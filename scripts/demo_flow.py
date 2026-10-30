from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from typing import Any
from urllib import error, request


DEFAULT_CONVERSATION = (
    "医生：您哪里不舒服？\n"
    "患者：发热、咳嗽、咽痛两天，最高体温38.2℃，没有胸痛，没有药物过敏史。\n"
    "医生：用过什么药？\n"
    "患者：昨天吃过一次布洛芬。\n"
)


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None


class HttpClient:
    """Minimal cookie-aware JSON client so the demo runs without extra deps."""

    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = request.build_opener(request.HTTPCookieProcessor(CookieJar()))

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Response:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                return Response(response.status, response.read(), dict(response.headers))
        except error.HTTPError as exc:
            return Response(exc.code, exc.read(), dict(exc.headers))
        except error.URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc.reason}") from exc


def _step(steps: list[dict[str, Any]], name: str, ok: bool, detail: Any = None) -> None:
    steps.append({"step": name, "ok": bool(ok), "detail": detail})


def _compact(body: Any) -> Any:
    """Keep the report small: scalars plus a couple of small structured fields."""
    if not isinstance(body, dict):
        return body
    out: dict[str, Any] = {}
    for key, value in body.items():
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            out[key] = value
        elif isinstance(value, str):
            out[key] = value if len(value) <= 200 else value[:200] + "..."
    for key in ("exports", "export_event", "errors", "user"):
        if key in body:
            out[key] = body[key]
    return out


def _require(steps: list[dict[str, Any]], name: str, response: Response, expected: int | tuple[int, ...]) -> Any:
    allowed = (expected,) if isinstance(expected, int) else expected
    body = response.json()
    ok = response.status in allowed
    _step(steps, name, ok, {"status": response.status, "body": _compact(body) if ok else body})
    if not ok:
        raise RuntimeError(f"{name} returned {response.status}: {body}")
    return body


def _approval_payload(task: dict[str, Any], readiness: dict[str, Any]) -> dict[str, Any]:
    fields = (task.get("result_json") or {}).get("fields") or {}
    missing_items = [
        {"key": key, "action": "accept_missing", "note": "演示流程接受本次缺失"}
        for key, value in fields.items()
        if key != "candidate_diagnoses"
        and isinstance(value, dict)
        and (value.get("missing") or not value.get("value"))
    ]
    diagnoses = [
        {
            "index": index,
            "action": "confirm_candidate",
            "high_risk_confirmed": bool(diagnosis.get("risk_warnings")),
        }
        for index, diagnosis in enumerate(fields.get("candidate_diagnoses") or [])
    ]
    return {
        "revision_id": readiness["revision_id"],
        "content_hash": readiness["content_hash"],
        "confirm_all_regular_fields": True,
        "fields": missing_items,
        "diagnoses": diagnoses,
    }


def _wait_for_result(
    http: HttpClient,
    task_id: int,
    steps: list[dict[str, Any]],
    *,
    timeout: float = 90.0,
) -> dict[str, Any]:
    """Poll until the background generation has produced a record result."""
    deadline = time.perf_counter() + timeout
    last: dict[str, Any] = {}
    while time.perf_counter() < deadline:
        response = http.request("GET", f"/api/tasks/{task_id}")
        last = response.json() or {}
        # The revision pointer is written after the result payload; both must
        # exist before export-readiness can answer.
        if (
            response.status == 200
            and last.get("result_json")
            and last.get("current_record_revision_id")
        ):
            _step(steps, "wait_generation", True, {"stage": last.get("current_stage")})
            return last
        if last.get("status") == "FAILED":
            break
        time.sleep(0.5)
    _step(steps, "wait_generation", False, {"status": last.get("status"), "stage": last.get("current_stage")})
    raise RuntimeError(f"generation did not produce a result in {timeout}s: {last.get('status')}")


def run_flow(
    admin_http: HttpClient,
    doctor_http: HttpClient,
    *,
    admin: tuple[str, str] = ("admin", "admin123456"),
    doctor: tuple[str, str] = ("demo_doctor", "demo-pass-123"),
    conversation: str = DEFAULT_CONVERSATION,
    download_exports: bool = True,
    seed_only: bool = False,
) -> dict[str, Any]:
    """Run the continuous demo path: login → register → generate → review → export → reopen."""
    steps: list[dict[str, Any]] = []
    ids: dict[str, Any] = {}
    started = time.perf_counter()

    health = _require(steps, "health", admin_http.request("GET", "/health"), 200)
    version = _require(steps, "version", admin_http.request("GET", "/version"), 200)
    ready = admin_http.request("GET", "/ready")
    _step(steps, "ready", ready.status in (200, 503), {"status": ready.status})

    _require(steps, "admin_login", admin_http.request(
        "POST", "/api/auth/login", {"username": admin[0], "password": admin[1]}
    ), 200)

    created = admin_http.request("POST", "/api/auth/users", {
        "username": doctor[0],
        "password": doctor[1],
        "display_name": "演示医生",
        "role": "doctor",
        "department_id": "demo-department",
    })
    _step(
        steps,
        "ensure_demo_doctor",
        created.status in (201, 400),
        {"status": created.status, "body": created.json()},
    )
    if created.status not in (201, 400):
        raise RuntimeError(f"ensure_demo_doctor returned {created.status}")

    if seed_only:
        elapsed = round(time.perf_counter() - started, 2)
        return {
            "ok": all(step["ok"] for step in steps),
            "version": version,
            "ids": ids,
            "elapsed_seconds": elapsed,
            "steps": steps,
            "seed_only": True,
        }

    doctor_login = _require(steps, "doctor_login", doctor_http.request(
        "POST", "/api/auth/login", {"username": doctor[0], "password": doctor[1]}
    ), 200)
    ids["doctor_user_id"] = (doctor_login.get("user") or {}).get("id")

    encounter = _require(steps, "create_encounter", doctor_http.request(
        "POST", "/api/encounters", {"patient_display_name": "演示患者"}
    ), 200)
    encounter_id = encounter["id"]
    ids["encounter_id"] = encounter_id
    _step(steps, "department_inherited", encounter.get("department_id") == "demo-department", encounter.get("department_id"))

    _require(steps, "check_in", doctor_http.request("POST", f"/api/encounters/{encounter_id}/check-in"), 200)
    _require(steps, "start_encounter", doctor_http.request("POST", f"/api/encounters/{encounter_id}/start"), 200)

    generated = _require(steps, "generate_record", doctor_http.request(
        "POST",
        "/api/records/generate",
        {"conversation_text": conversation, "encounter_id": encounter_id},
    ), 200)
    task_id = int(generated["task_id"])
    ids["task_id"] = task_id

    task = _wait_for_result(doctor_http, task_id, steps)
    _step(steps, "read_task", True, {"task_id": task_id})
    readiness_before = _require(steps, "readiness_before_edit", doctor_http.request(
        "GET", f"/api/tasks/{task_id}/export-readiness"
    ), 200)
    fields = ((task.get("result_json") or {}).get("fields") or {})
    if not isinstance(fields, dict) or "chief_complaint" not in fields:
        raise RuntimeError("task result has no chief_complaint field")

    edited_fields = json.loads(json.dumps(fields, ensure_ascii=False))
    complaint = edited_fields.get("chief_complaint") or {}
    complaint["value"] = (complaint.get("value") or "") + "（医生已核对）"
    edited_fields["chief_complaint"] = complaint
    reviewed = _require(steps, "doctor_edit_review", doctor_http.request(
        "POST",
        f"/api/tasks/{task_id}/review",
        {
            "fields": edited_fields,
            "expected_revision_id": readiness_before["revision_id"],
            "expected_content_hash": readiness_before["content_hash"],
            "manual_takeover_fields": ["chief_complaint"],
        },
    ), 200)
    _step(steps, "review_stage", reviewed.get("current_stage") == "waiting_doctor_review", reviewed.get("current_stage"))

    readiness = _require(steps, "export_readiness", doctor_http.request(
        "GET", f"/api/tasks/{task_id}/export-readiness"
    ), 200)
    ids["revision_id"] = readiness.get("revision_id")

    approved = _require(steps, "approve", doctor_http.request(
        "POST", f"/api/tasks/{task_id}/approve", _approval_payload(task, readiness)
    ), 200)
    _step(steps, "approved_stage", approved.get("current_stage") == "approved", approved.get("current_stage"))

    exported = _require(steps, "export", doctor_http.request("POST", f"/api/tasks/{task_id}/export"), 200)
    task_after_export = _require(steps, "read_task_after_export", doctor_http.request(
        "GET", f"/api/tasks/{task_id}"
    ), 200)
    export_event = ((task_after_export.get("result_json") or {}).get("export_event") or {})
    ids["export_event_id"] = export_event.get("id")
    _step(steps, "export_event", bool(export_event.get("id")), export_event)
    _step(steps, "export_files", bool(exported.get("exports")), exported.get("exports"))

    if download_exports:
        for export_format in ("docx", "markdown"):
            response = doctor_http.request("GET", f"/api/tasks/{task_id}/exports/{export_format}")
            _step(
                steps,
                f"download_{export_format}",
                response.status == 200 and len(response.body) > 0,
                {"status": response.status, "bytes": len(response.body)},
            )

    reopened = _require(steps, "reopen_encounter", doctor_http.request(
        "GET", f"/api/encounters/{encounter_id}"
    ), 200)
    revision_count = len(reopened.get("revisions") or [])
    _step(steps, "revision_history", revision_count >= 2, revision_count)
    _step(
        steps,
        "export_persisted",
        (reopened.get("task") or {}).get("current_stage") == "exported",
        (reopened.get("task") or {}).get("current_stage"),
    )

    _require(steps, "complete_encounter", doctor_http.request(
        "POST", f"/api/encounters/{encounter_id}/complete"
    ), 200)

    chain = _require(steps, "audit_chain", admin_http.request("GET", "/api/security/audit-chain/verify"), 200)
    _step(steps, "audit_chain_valid", bool(chain.get("ok")), {"entries": chain.get("entries"), "reason": chain.get("reason")})

    metrics = admin_http.request("GET", "/metrics")
    _step(steps, "metrics", metrics.status == 200 and b"mra_patient_total" in metrics.body, {"status": metrics.status})

    elapsed = round(time.perf_counter() - started, 2)
    ok = all(step["ok"] for step in steps)
    return {
        "ok": ok,
        "version": version,
        "ids": ids,
        "elapsed_seconds": elapsed,
        "steps": steps,
    }


def _print_report(report: dict[str, Any]) -> None:
    version = report.get("version") or {}
    print(f"demo flow  version={version.get('version')}  provider={version.get('provider')}  ok={report['ok']}")
    for step in report["steps"]:
        mark = "PASS" if step["ok"] else "FAIL"
        print(f"  [{mark}] {step['step']:<22} {json.dumps(step['detail'], ensure_ascii=False)[:160]}")
    print(f"  ids: {json.dumps(report['ids'], ensure_ascii=False)}")
    print(f"  elapsed: {report['elapsed_seconds']}s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the continuous Medical Record Agent demo flow over HTTP.")
    parser.add_argument("--base-url", default="http://127.0.0.1:2626")
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--admin-password", default="admin123456")
    parser.add_argument("--doctor-user", default="demo_doctor")
    parser.add_argument("--doctor-password", default="demo-pass-123")
    parser.add_argument("--conversation-file", type=str, default=None)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--seed-only", action="store_true", help="Only ensure the demo doctor exists.")
    parser.add_argument("--json-out", type=str, default=None)
    args = parser.parse_args(argv)

    conversation = DEFAULT_CONVERSATION
    if args.conversation_file:
        with open(args.conversation_file, encoding="utf-8") as handle:
            conversation = handle.read()

    report = run_flow(
        HttpClient(args.base_url),
        HttpClient(args.base_url),
        admin=(args.admin_user, args.admin_password),
        doctor=(args.doctor_user, args.doctor_password),
        conversation=conversation,
        download_exports=not args.no_download,
        seed_only=args.seed_only,
    )
    _print_report(report)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
