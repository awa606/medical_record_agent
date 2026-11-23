"""Measure a fresh, private classroom deployment and replay the synthetic review actions."""
import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from tempfile import TemporaryDirectory

import requests


def sha(data):
    return hashlib.sha256(data).hexdigest()


def field_hash(fields):
    return sha(json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())


@contextmanager
def deployed(bundle, data_root):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    started = time.perf_counter()
    log = data_root.parent / "controlled-launch.log"
    with log.open("w", encoding="utf-8") as stream:
        proc = subprocess.Popen(
            [sys.executable, "-B", "-X", "utf8", str(bundle / "课堂启动.py"), "--no-browser",
             "--port", str(port), "--data-root", str(data_root)],
            stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        try:
            while "受控验证模式" not in log.read_text(encoding="utf-8"):
                if proc.poll() is not None or time.perf_counter() - started > 65:
                    raise RuntimeError("课堂启动器未在65秒内就绪")
                time.sleep(.05)
            yield f"http://127.0.0.1:{port}", round((time.perf_counter() - started) * 1000, 2)
        finally:
            if proc.poll() is None:
                proc.communicate(input=b"\n", timeout=25)


def verify(bundle, actions, target, result):
    with TemporaryDirectory(prefix="medilisten-platform-") as temp:
        root = Path(temp)
        installed = root / "software"
        shutil.copytree(bundle, installed)
        data = root / "state"
        with deployed(installed, data) as (base, startup), requests.Session() as api:
            api.trust_env = False
            account = json.loads((data / "本机账户.json").read_text(encoding="utf-8"))
            if os.name == "posix":
                assert (data / "本机账户.json").stat().st_mode & 0o077 == 0
            login = api.post(base + "/api/auth/login", timeout=15, json={
                "username": account["username"], "password": account["password"]})
            login.raise_for_status()
            def get(path):
                response = api.get(base + path, timeout=15)
                response.raise_for_status()
                return response

            result["startup_ms"] = startup
            identity = get("/course/identity").json()
            manifest = (installed / "运行源/runtime-sha256.json").read_bytes()
            assert identity["runtime_sha256"] == sha(manifest) and identity["variant"] == "classroom-review-2"
            result["runtime_sha256"] = sha(manifest)
            result["files_sha256"] = {name: sha((installed / name).read_bytes()) for name in (
                "课堂启动.py", "course_service.py", "冻结资产/fixtures/input.json",
                "冻结资产/fixtures/model_first_output.json")}
            assert get("/health").json()["status"] == "ok"
            get("/ready")
            items = get("/api/encounters").json()["encounters"]
            assert len(items) == 1 and items[0]["patient_deidentified_id"] == "SIM-COURSE-FEVER-01"
            eid, tid = items[0]["id"], items[0]["task_id"]
            assert tid == 1 and eid == 1, "需要全新课堂数据库"
            task_path = f"/api/tasks/{tid}"
            first = get(task_path).json()["result_json"]["fields"]
            result.update(field_count=len(first), first_field_hash=field_hash(first))
            routes = {"queue": "/api/encounters", "encounter": f"/api/encounters/{eid}", "task": task_path}
            samples = {name: [] for name in routes}
            result["samples_ms"] = samples
            for i in range(33):
                for name, path in routes.items():
                    start = time.perf_counter_ns()
                    response = get(path)
                    latency = (time.perf_counter_ns() - start) / 1_000_000
                    payload = response.json()
                    if name == "queue":
                        assert len(payload["encounters"]) == 1 and payload["encounters"][0]["id"] == eid
                    elif name == "encounter":
                        assert payload.get("encounter", payload)["task_id"] == tid
                    else:
                        assert payload["result_json"]["fields"] == first
                    if i >= 3:
                        samples[name].append(round(latency, 3))
            result["latency"] = {name: {"n": len(ms), "median_ms": statistics.median(ms),
                "p95_ms": sorted(ms)[math.ceil(.95 * len(ms)) - 1]} for name, ms in samples.items()}

            # Only allow the four operations captured from the fixed case and an empty classroom DB.
            steps = [json.loads(line) for line in actions.read_text(encoding="utf-8").splitlines()]
            assert [step["route"] for step in steps] == [task_path + suffix for suffix in
                ("/review", "/review", "/approve", "/export?expected_revision_id=3&expected_approval_id=1")]
            assert all(step["method"] == "POST" for step in steps)
            result["review_actions_sha256"] = sha(actions.read_bytes())
            blocked = api.post(base + task_path + "/export", timeout=15)
            result["unsigned_export_http"] = blocked.status_code
            assert blocked.status_code == 400
            result["actions_http"] = []
            for step in steps:
                body = step["json"]
                if body is not None:
                    revision = get(task_path + "/export-readiness").json()
                    if step["route"].endswith("/review"):
                        assert body["expected_revision_id"] == revision["revision_id"]
                        body["expected_content_hash"] = revision["content_hash"]
                    if step["route"].endswith("/approve"):
                        assert body["revision_id"] == revision["revision_id"]
                        body["content_hash"] = revision["content_hash"]
                response = api.post(base + step["route"], json=body, timeout=30)
                result["actions_http"].append([step["route"], response.status_code])
                response.raise_for_status()
            final_fields = get(task_path).json()["result_json"]["fields"]
            assert final_fields != first and "布洛芬" in str(final_fields["present_illness"])
            result["final_field_hash"] = field_hash(final_fields)
            ready = get(task_path + "/export-readiness").json()
            assert ready["revision_id"] == 3 and ready["approval_id"] == 1 and not ready["errors"]
            result["signed_revision"] = ready["revision_id"]
            pdf = get(task_path + "/exports/pdf")
            assert pdf.content.startswith(b"%PDF") and "_R3_" in pdf.headers["Content-Disposition"]
            (target / "合成病例_R3.pdf").write_bytes(pdf.content)
            result["pdf_sha256"] = sha(pdf.content)
            events = [json.loads(row) for row in (data / "replay-events.jsonl").read_text().splitlines()]
            assert len(events) == 1 and events[0]["event"] == "matched" and events[0]["model_calls"] == 0
            result["live_model_calls"] = 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "actions", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = {"status": "FAIL", "started_utc": datetime.now(timezone.utc).isoformat(),
              "os": platform.platform(), "python": platform.python_version(),
              "dependencies": {k: metadata.version(k) for k in
                               ("requests", "fastapi", "uvicorn", "pydantic", "reportlab", "python-docx")}}
    try:
        verify(args.bundle, args.actions, args.output, result)
        result["status"] = "PASS"
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
