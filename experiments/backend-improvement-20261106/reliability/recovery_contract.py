"""Offline, synthetic single-process recovery contract. NOT production startup.

OS locks are tested only within one OS/kernel. This does not protect against old
writers which never acquire this lock, nor support multiple application workers.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time


AUTOMATIC = ("CREATED", "EXTRACTING_FIELDS", "GENERATING_DRAFT", "SAFETY_CHECKING")


class InstanceLock:
    def __init__(self, database):
        self.database = Path(database).resolve()
        self.path = self.database.with_name(self.database.name + ".instance.lock")
        self.handle = None
        self.owner_pid = None

    def acquire(self):
        if self.handle is not None:
            raise RuntimeError("Lock object is already acquired")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            if self.path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError("Another cooperating instance owns this database") from exc
        self.handle, self.owner_pid = handle, os.getpid()
        return self

    def release(self):
        if self.handle is None:
            return
        if self.handle.closed:
            self.handle, self.owner_pid = None, None
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle, self.owner_pid = None, None
        # Do not unlink the lock file: a replacement inode could split ownership.

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.release()


def recover(database, lock, *, enabled=False, old_writers_stopped=False, fail_after_update=False):
    """Prototype only. No retries or provider imports/calls are permitted."""
    if not enabled:
        return []
    database = Path(database).resolve()
    if (lock is None or lock.handle is None or lock.handle.closed or lock.owner_pid != os.getpid()
            or lock.database != database):
        raise RuntimeError("Recovery requires this process's lifetime database lock")
    try:
        os.fstat(lock.handle.fileno())
    except (OSError, ValueError) as exc:
        raise RuntimeError("Recovery requires a valid lifetime database lock handle") from exc
    if not old_writers_stopped:
        raise RuntimeError("Old/noncooperating writers must be stopped before startup")
    from app.db import sqlite as db
    if db.get_db_path().resolve() != database:
        raise RuntimeError("Database configuration changed after locking")
    with closing(db.get_connection()) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in AUTOMATIC)
            tasks = connection.execute(
                f"SELECT * FROM agent_task WHERE status IN ({placeholders}) ORDER BY id", AUTOMATIC
            ).fetchall()
            # Refuse the whole unit of work if state disagrees with a signature.
            for task in tasks:
                active = connection.execute(
                    "SELECT 1 FROM approval WHERE status = 'active' AND invalidated_at IS NULL "
                    "AND (task_id = ? OR revision_id = ?) LIMIT 1",
                    (task["id"], task["current_record_revision_id"]),
                ).fetchone()
                if active:
                    raise RuntimeError("Automatic task unexpectedly has an active approval")
            now = db.utc_now()
            for task in tasks:
                message = "Process stopped before completion; input retained; explicit user action required."
                connection.execute(
                    "UPDATE agent_task SET status = 'FAILED', current_stage = 'failed', "
                    "error_message = ?, updated_at = ?, completed_at = ? WHERE id = ?",
                    (message, now, now, task["id"]),
                )
                if fail_after_update:
                    raise RuntimeError("Injected transaction failure")
                connection.execute(
                    "UPDATE agent_task_step SET status = 'FAILED', ended_at = ?, "
                    "error_message = ? WHERE task_id = ? AND status = 'RUNNING'",
                    (now, message, task["id"]),
                )
                db._insert_audit_log_row(
                    connection, task_id=task["id"], event_type="recovery_interrupted_task_spike",
                    event_detail={"previous_status": task["status"], "automatic_retry": False,
                                  "synthetic_experiment": True},
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return [task["id"] for task in tasks]


def deny_network(*_, **__):
    raise AssertionError("Network forbidden in recovery contract experiment")


def configure(folder):
    for key in list(os.environ):
        if key.startswith("ONLINE_LLM_"):
            del os.environ[key]
    database = folder / "state.sqlite3"
    os.environ.update({"MEDICAL_RECORD_AGENT_DB": str(database),
                       "MEDICAL_RECORD_AGENT_OUTPUT_DIR": str(folder / "exports"),
                       "MRA_ANONYMIZE": "0", "LLM_PROVIDER": "mock", "LLM_MAX_RETRIES": "0"})
    socket.create_connection = deny_network
    return database


def snapshot():
    from app.db import sqlite as db
    tables = ("agent_task", "agent_task_step", "record_revision", "approval", "export_event", "audit_log", "audit_chain")
    with closing(db.get_connection()) as connection:
        return {name: [dict(row) for row in connection.execute(f"SELECT * FROM {name} ORDER BY id")]
                for name in tables}


def fixture(folder):
    from app.db import sqlite as db
    database = configure(folder)
    # Fixtures use real schema/helpers but only the newly created synthetic DB.
    db.init_db()
    task_ids = {}
    for state in (*AUTOMATIC, "WAITING_DOCTOR_REVIEW", "DONE", "FAILED", "UNRECOGNIZED_STATE"):
        task = db.create_task("text", state, input_text="SYNTHETIC recovery contract " + state)
        raw = {"fields": {}, "draft": "synthetic preserved draft", "raw_evidence": [state]}
        db.update_task(task, result_json=json.dumps(raw), retry_count=2)
        revision = db.create_record_revision_for_task(task, raw, source="spike", workflow_status="draft")
        db.create_task_step(task, "extract_fields", "RUNNING", input_snapshot={"synthetic": state})
        db.create_task_step(task, "load_input", "SUCCEEDED", input_snapshot={"synthetic": state})
        task_ids[state] = task
    return database, task_ids


def expected_error(action, contains):
    try:
        action()
    except RuntimeError as exc:
        assert contains in str(exc), str(exc)
        return
    raise AssertionError("Expected refusal: " + contains)


def check_locks(folder):
    database = folder / "lock-only.sqlite3"
    ready = folder / "lock-ready.txt"
    command = [sys.executable, __file__, "--hold", str(database), "--ready", str(ready)]
    holder = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and holder.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), holder.communicate(timeout=1)
        contender = subprocess.run([sys.executable, __file__, "--try-lock", str(database)],
                                   capture_output=True, text=True, timeout=10)
        assert contender.returncode == 23, (contender.returncode, contender.stderr)
        holder.kill()  # only our own Popen experiment child
        holder.wait(timeout=10)
        with InstanceLock(database):
            pass
        released = subprocess.run([sys.executable, __file__, "--try-lock", str(database)],
                                  capture_output=True, text=True, timeout=10)
        assert released.returncode == 0, released.stderr
        return {"holder_pid": holder.pid, "holder_exit_code": holder.returncode,
                "contender_exit_code": contender.returncode, "reacquired_after_kill": True,
                "released_then_other_process_acquired": True}
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=10)


def check_closed_handle(folder):
    """Independent-review control: a stale Python object must not grant recovery."""
    folder.mkdir(parents=True, exist_ok=True)
    database, _ = fixture(folder / "closed-handle")
    before = snapshot()
    stale_lock = InstanceLock(database).acquire()
    stale_lock.handle.close()
    try:
        with InstanceLock(database):
            expected_error(lambda: recover(database, stale_lock, enabled=True,
                                           old_writers_stopped=True), "lifetime")
        assert snapshot() == before
    finally:
        # The test deliberately closed it externally; do not double-unlock it.
        stale_lock.handle, stale_lock.owner_pid = None, None
    result = {"platform": sys.platform, "closed_handle_refused": True,
              "second_lock_owner_unaffected": True, "database_unchanged": True, "cloud_calls": 0}
    (folder / "closed-handle-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


def run(folder):
    folder.mkdir(parents=True, exist_ok=True)
    result = {"platform": sys.platform, "python": sys.version.split()[0],
              "synthetic_only": True, "cloud_calls": 0, "checks": []}
    result["lock"] = check_locks(folder)
    result["checks"].extend(["concurrent_process_refused", "kill_releases_lock", "clean_release_reacquires"])
    database, task_ids = fixture(folder / "normal")
    before = snapshot()
    assert recover(database, None) == []
    assert snapshot() == before
    result["checks"].append("default_disabled_is_noop")
    expected_error(lambda: recover(database, None, enabled=True, old_writers_stopped=True), "lifetime")
    with InstanceLock(database) as lock:
        expected_error(lambda: recover(database, lock, enabled=True), "Old/noncooperating")
        expected_error(lambda: recover(database.with_name("other.sqlite3"), lock, enabled=True,
                                       old_writers_stopped=True), "lifetime")
        result["checks"].extend(["requires_owned_lock", "requires_old_writers_stopped", "database_identity_refused"])
        expected_error(lambda: recover(database, lock, enabled=True, old_writers_stopped=True,
                                       fail_after_update=True), "Injected")
        assert snapshot() == before
        result["checks"].append("transaction_failure_rolls_back_all_tables")
        ids = recover(database, lock, enabled=True, old_writers_stopped=True)
        after = snapshot()
        assert ids == [task_ids[state] for state in AUTOMATIC]
        for old, new in zip(before["agent_task"], after["agent_task"]):
            if old["id"] in ids:
                assert new["status"] == "FAILED" and new["completed_at"]
                for key in ("input_text", "result_json", "retry_count", "encounter_id", "current_record_revision_id"):
                    assert old[key] == new[key], key
            else:
                assert old == new
        for old, new in zip(before["agent_task_step"], after["agent_task_step"]):
            if old["task_id"] in ids and old["status"] == "RUNNING":
                assert new["status"] == "FAILED" and new["ended_at"]
                assert old["input_snapshot_json"] == new["input_snapshot_json"]
                assert old["output_snapshot_json"] == new["output_snapshot_json"]
            else:
                assert old == new
        for table in ("record_revision", "approval", "export_event"):
            assert before[table] == after[table], table
        assert len(after["audit_log"]) - len(before["audit_log"]) == 4
        assert len(after["audit_chain"]) - len(before["audit_chain"]) == 4
        assert recover(database, lock, enabled=True, old_writers_stopped=True) == []
        assert snapshot() == after
        result["checks"].extend(["exact_four_statuses_failed", "review_done_failed_unknown_untouched",
                                 "input_result_revision_unchanged", "running_steps_closed_same_transaction",
                                 "audit_written_same_transaction", "idempotent_no_extra_audit", "no_retry"])
    (folder / "before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    (folder / "after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
    # Corrupt synthetic state: signature exists but task wrongly says extracting.
    database, ids = fixture(folder / "approval-anomaly")
    from app.db import sqlite as db
    db.create_approval_for_task(ids["EXTRACTING_FIELDS"])
    db.update_task(ids["EXTRACTING_FIELDS"], status="EXTRACTING_FIELDS", current_stage="extract_fields")
    before_anomaly = snapshot()
    with InstanceLock(database) as lock:
        expected_error(lambda: recover(database, lock, enabled=True, old_writers_stopped=True), "active approval")
    assert snapshot() == before_anomaly
    result["checks"].append("active_approval_anomaly_refuses_entire_transaction")
    result["checks_passed"] = len(result["checks"])
    (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hold", type=Path)
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--try-lock", type=Path)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--closed-handle-only", action="store_true")
    args = parser.parse_args()
    if args.hold:
        with InstanceLock(args.hold):
            args.ready.write_text(str(os.getpid()), encoding="ascii")
            time.sleep(60)
        return
    if args.try_lock:
        try:
            with InstanceLock(args.try_lock):
                pass
        except RuntimeError:
            raise SystemExit(23)
        return
    if args.repo:
        sys.path.insert(0, str(args.repo.resolve()))
    output = args.output or Path(tempfile.mkdtemp(prefix="mra-recovery-contract-"))
    if args.closed_handle_only:
        check_closed_handle(output.resolve())
    else:
        run(output.resolve())


if __name__ == "__main__":
    main()
