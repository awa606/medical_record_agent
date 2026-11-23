"""Exercise four ordinary synthetic doctor sessions from intake to signed PDF.

Run with python -m scripts.benchmarks.verify_concurrent_visits OUTPUT_DIR
from a development install. Each arm starts its own temporary loopback service.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
from time import monotonic, perf_counter, perf_counter_ns, sleep

import httpx
import pymupdf

from tests.approval_helpers import approval_payload_for_fields
from tests.test_doctor_itemized_approval_playwright import RunningServer


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def marker(doctor: int, wave: int) -> str:
    return f"SYNV{doctor}W{wave}X"


def run_visit(client, doctor, wave, barrier, calls):
    started = perf_counter()

    def request(method, url, operation, payload=None):
        begin = perf_counter_ns()
        response = client.request(method, url, json=payload)
        finish = perf_counter_ns()
        calls.append({
            "doctor": doctor, "wave": wave, "operation": operation,
            "status": response.status_code, "start_ns": begin, "end_ns": finish,
            "ms": round((finish - begin) / 1_000_000, 3),
        })
        response.raise_for_status()
        return response

    token = marker(doctor, wave)
    encounter = request("POST", "/api/encounters", "register", {
        "patient_deidentified_id": token, "patient_display_name": "合成接诊",
    }).json()
    eid = encounter["id"]
    ep = f"/api/encounters/{eid}"
    for action in ("check-in", "start"):
        request("POST", ep + "/" + action, action, {})
    task = request("POST", "/api/records/generate", "generate", {
        "encounter_id": eid, "conversation_text": "患者：我这两天咳嗽，只在白天咳嗽。",
    }).json()
    tid = task["task_id"]
    tp = f"/api/tasks/{tid}"
    deadline = monotonic() + 30
    while monotonic() < deadline:
        draft = request("GET", tp, "read-draft").json()
        if draft["status"] == "WAITING_DOCTOR_REVIEW" and draft.get("current_record_revision_id"):
            break
        sleep(.1)
    else:
        raise RuntimeError(f"{token} did not reach a reviewable draft")
    r1 = request("GET", tp + "/export-readiness", "read-r1").json()
    assert r1["revision_number"] == 1 and draft["encounter_id"] == eid
    fields = draft["result_json"]["fields"]
    value = "患者自述白天咳嗽，合成核对编号 " + token
    fields["present_illness"].update(value=value, status="complete", missing=False,
                                     source_spans=[], missing_elements=[])
    review = request("POST", tp + "/review", "save", {
        "fields": fields, "manual_takeover_fields": ["present_illness"],
        "expected_revision_id": r1["revision_id"], "expected_content_hash": r1["content_hash"],
    }).json()
    r2 = request("GET", tp + "/export-readiness", "read-r2").json()
    saved = review["result_json"]["fields"]
    assert r2["revision_number"] == 2 and saved["present_illness"]["value"] == value
    payload = approval_payload_for_fields(saved)
    payload.update(revision_id=r2["revision_id"], content_hash=r2["content_hash"])
    for item in payload["fields"]:
        field = saved[item["key"]]
        item["action"] = "confirm_content" if field.get("value") and not field["missing"] else "confirm_not_asked"

    if barrier:
        barrier.wait()
    request("POST", tp + "/approve", "approve", payload)
    ready = request("GET", tp + "/export-readiness", "read-approval").json()
    assert ready["ready"] and ready["revision_id"] == r2["revision_id"]
    if barrier:
        barrier.wait()
    receipt = request("POST", tp + f"/export?expected_revision_id={r2['revision_id']}&expected_approval_id={ready['approval_id']}", "export").json()
    exported = receipt["exports"]
    pdf_hash = exported["pdf_sha256"]
    pdf = request("GET", tp + "/exports/pdf?sha256=" + pdf_hash, "download").content
    assert sha256(pdf).hexdigest() == pdf_hash
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        pdf_text = "".join("".join(page.get_text() for page in document).split())
    matches = [marker(d, w) for d in range(4) for w in range(3) if marker(d, w) in pdf_text]
    assert matches == [token], (token, matches)
    return {
        "doctor": doctor, "wave": wave, "encounter": eid, "task": tid,
        "r1": r1["revision_id"], "r2": r2["revision_id"], "hash": r2["content_hash"],
        "approval": ready["approval_id"], "pdf_sha256": pdf_hash, "bytes": len(pdf),
        "marker": token, "workflow_ms": round((perf_counter() - started) * 1000, 3),
    }


def verify_archive(database, clients, people, visits):
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as db:
        counts = {name: db.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                  for name in ("encounter", "record_revision", "approval", "export_event")}
        assert counts == {"encounter": 12, "record_revision": 24, "approval": 12, "export_event": 12}, counts
        for visit in visits:
            doctor = visit["doctor"]
            row = db.execute("""
                SELECT e.doctor_user_id, e.task_id, e.current_revision_id, r.created_by_user_id,
                       r.revision_no, r.content_hash, a.id, a.approved_by_user_id, x.exported_by_user_id
                FROM encounter e JOIN record_revision r ON r.id=e.current_revision_id AND r.encounter_id=e.id
                JOIN approval a ON a.revision_id=r.id AND a.encounter_id=e.id AND a.task_id=e.task_id
                JOIN export_event x ON x.approval_id=a.id AND x.revision_id=r.id
                                   AND x.encounter_id=e.id AND x.task_id=e.task_id
                WHERE e.id=?""", (visit["encounter"],)).fetchall()
            uid = people[doctor]
            assert row == [(uid, visit["task"], visit["r2"], uid, 2, visit["hash"], visit["approval"], uid, uid)]
            response = clients[doctor].get(f"/api/tasks/{visit['task']}/exports/pdf", params={"sha256": visit["pdf_sha256"]})
            response.raise_for_status()
            assert len(response.content) == visit["bytes"] and sha256(response.content).hexdigest() == visit["pdf_sha256"]
    assert len({v["pdf_sha256"] for v in visits}) == len(visits)
    return counts


def run_arm(output, parallel):
    label = "parallel" if parallel else "serial"
    result = {"arm": label, "visits": [], "calls": [], "wave_ms": []}
    admin = secrets.token_urlsafe(28)
    isolated = TemporaryDirectory(prefix="mra-synthetic-identity-")
    server = None
    try:
        server = RunningServer({"MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD": admin,
                                "ASR_PREWARM_ENABLED": "0", "RECORD_PROVIDER_MODE": "demo",
                                "MRA_IDENTITY_MAP_PATH": str(Path(isolated.name) / "identity.sqlite3")})
        with ExitStack() as stack:
            def session():
                return stack.enter_context(httpx.Client(base_url=server.base_url, timeout=30, trust_env=False))
            setup = session()
            setup.post("/api/auth/login", json={"username": "admin", "password": admin}).raise_for_status()
            clients, people = [], []
            for doctor in range(4):
                username, password = f"synthetic-doc-{doctor}", secrets.token_urlsafe(20)
                setup.post("/api/auth/users", json={"username": username, "password": password,
                           "display_name": f"合成医生{doctor}", "role": "doctor"}).raise_for_status()
                client = session()
                login = client.post("/api/auth/login", json={"username": username, "password": password})
                login.raise_for_status()
                who = login.json()["user"]
                assert who["role"] == "doctor"
                people.append(who["id"])
                clients.append(client)
            for wave in range(3):
                barrier = Barrier(4, timeout=30) if parallel else None
                logs = [[] for _ in clients]
                def visit(doctor):
                    try:
                        if barrier:
                            barrier.wait()
                        return run_visit(clients[doctor], doctor, wave, barrier, logs[doctor])
                    except Exception:
                        if barrier:
                            barrier.abort()
                        raise
                start = perf_counter()
                errors = []
                try:
                    with ThreadPoolExecutor(max_workers=4 if parallel else 1) as pool:
                        futures = [pool.submit(visit, doctor) for doctor in range(4)]
                        for future in futures:
                            try:
                                result["visits"].append(future.result())
                            except Exception as exc:
                                errors.append(f"{type(exc).__name__}: {exc}")
                    if errors:
                        raise RuntimeError(" | ".join(errors))
                finally:
                    result["calls"].extend(item for log in logs for item in log)
                    result["wave_ms"].append(round((perf_counter() - start) * 1000, 3))
            result["db_counts"] = verify_archive(server.root / "edge.sqlite3", clients, people, result["visits"])
            result["verified_redownloads"] = len(result["visits"])
            result["status"] = "passed"
            print(f"{label}: {len(result['visits'])} signed visits with matching revisions, signers and PDFs")
    except Exception as exc:
        result.update(status="failed", failure=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        write_json(output / (label + ".json"), result)
        if server is not None:
            server.close()
        isolated.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory for synthetic measurements")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for concurrent in (False, True):
        run_arm(args.output.resolve(), concurrent)
