"""Isolated interruption audit: real orchestration, a blocking recorded provider.

Only terminates the child it creates. No server, Docker or model is started.
All database/files are synthetic and live in the unique evidence run directory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time


REPO = Path(__file__).resolve().parents[3]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def isolated_environment(folder):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("ONLINE_LLM_"):
            del env[key]
    env.update({"MEDICAL_RECORD_AGENT_DB": str(folder / "state.sqlite3"),
                "MEDICAL_RECORD_AGENT_OUTPUT_DIR": str(folder / "exports"),
                "LLM_PROVIDER": "mock", "RECORD_PROVIDER_MODE": "demo",
                "LLM_MAX_RETRIES": "0", "MRA_ANONYMIZE": "0",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
                "PYTHONPATH": str(REPO)})
    return env


def deny_network(*args, **kwargs):
    raise AssertionError("Network forbidden in task interruption experiment")


def snapshot(folder):
    from app.db import get_task, get_task_steps
    task_id = json.loads((folder / "task.json").read_text(encoding="utf-8"))["task_id"]
    task = get_task(task_id)
    return {"task_id": task_id, "status": task["status"], "current_stage": task["current_stage"],
            "error_message": task.get("error_message"),
            "current_record_revision_id": task.get("current_record_revision_id"),
            "step_statuses": [{"step": row["step_name"], "status": row["status"]}
                              for row in get_task_steps(task_id)],
            "recorded_provider_calls": len(json.loads((folder / "calls.json").read_text(encoding="utf-8")))}


def worker(folder):
    socket.create_connection = deny_network
    from app.db import init_db
    from app.agents import MedicalRecordOrchestrator
    from app.services.llm.llm_record_generator import LLMRecordGenerator

    init_db()

    class BlockingProvider:
        name = "recorded-blocking-provider"
        model = "no-model-call"

        def generate_fields_json(self, *_args, **_kwargs):
            save(folder / "calls.json", [{"kind": "fixed_provider_entered", "pid": os.getpid()}])
            save(folder / "before.json", snapshot(folder))
            (folder / "entered.txt").write_text("provider-entered", encoding="utf-8")
            threading.Event().wait(90)
            raise AssertionError("Parent did not terminate its isolated worker in time")

    generator = LLMRecordGenerator(provider=BlockingProvider(), mode="edge", allow_mock_fallback=False)
    generator.max_retries = 0
    orchestrator = MedicalRecordOrchestrator(generator)
    source = "患者：本样例为合成运行中断测试，发热两天。"
    task_id = orchestrator.create_text_task(source)
    save(folder / "task.json", {"task_id": task_id})
    orchestrator.run_existing_text_task(task_id, source)


def read_after_restart(folder):
    socket.create_connection = deny_network
    from app.db import init_db
    init_db()  # Same database initialization performed by application lifespan.
    save(folder / "after_restart.json", snapshot(folder))


def run():
    evidence = REPO / ".artifacts" / "backend-improvement-20261106" / "task-interruption"
    evidence.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="isolated-", dir=evidence)).resolve()
    env = isolated_environment(folder)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    child = None
    with (folder / "worker.log").open("w", encoding="utf-8") as log:
        try:
            child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "--worker", str(folder)],
                                     cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            deadline = time.monotonic() + 25
            while not (folder / "entered.txt").exists():
                if child.poll() is not None:
                    raise RuntimeError(f"Isolated worker exited early: {child.returncode}; inspect {folder}")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Isolated worker did not enter its fixed provider")
                time.sleep(.05)
            child.terminate()
            child.wait(timeout=5)
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.wait(timeout=5)
    subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--read", str(folder)],
                   cwd=REPO, env=env, check=True, timeout=20, creationflags=flags,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    before = json.loads((folder / "before.json").read_text(encoding="utf-8"))
    after = json.loads((folder / "after_restart.json").read_text(encoding="utf-8"))
    result = {"scope": "isolated_database_reinitialization_not_live_server_restart",
              "real_model_calls": 0, "external_api_calls": 0,
              "production_changed": False, "child_pid": child.pid, "child_exit_code": child.returncode,
              "before": before, "after_restart": after,
              "interrupted_task_still_processing": after["status"] == "EXTRACTING_FIELDS",
              "automatic_retry_observed": after["recorded_provider_calls"] != before["recorded_provider_calls"],
              "evidence_directory": str(folder)}
    save(folder / "result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--read", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
    elif args.read:
        read_after_restart(args.read)
    else:
        run()
