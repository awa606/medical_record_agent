"""Synthetic startup/recovery contract; no providers or live databases."""
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from app import main
from app.db import sqlite as db
from app.services.llm import factory


ACTIVE = ("CREATED", "EXTRACTING_FIELDS", "GENERATING_DRAFT", "SAFETY_CHECKING")


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "state.sqlite3"))
    monkeypatch.setenv("MRA_ANONYMIZE", "0")
    monkeypatch.setenv("ASR_PREWARM_ENABLED", "0")
    for name in ("MRA_SINGLE_INSTANCE_RECOVERY_ENABLED", "MRA_RECOVERY_OLD_WRITERS_STOPPED",
                 "MRA_RECOVERY_WORKER_COUNT", "WEB_CONCURRENCY", "UVICORN_WORKERS"):
        monkeypatch.delenv(name, raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("No network/provider calls in recovery tests")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    original_connect = socket.socket.connect
    def local_event_loop_only(sock, address):
        # Windows asyncio implements its own wake-up pipe with loopback sockets.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        return forbidden()
    monkeypatch.setattr(socket.socket, "connect", local_event_loop_only)
    monkeypatch.setattr(factory, "get_llm_status", lambda **kw: {"provider": "mock", "mode": "demo"})
    monkeypatch.setattr(factory, "create_llm_provider", forbidden)
    monkeypatch.setattr(main, "start_funasr_prewarm", forbidden)
    yield tmp_path
    # Tests share one interpreter; production never clears the process registry.
    # Clean only this fixture's private database after every test has ended.
    from app.services import task_recovery
    for key, lock in list(task_recovery._PROCESS_LOCKS.items()):
        if lock.database.parent == tmp_path:
            task_recovery._PROCESS_LOCKS.pop(key)
            lock.release()


def enable(monkeypatch):
    monkeypatch.setenv("MRA_SINGLE_INSTANCE_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("MRA_RECOVERY_OLD_WRITERS_STOPPED", "1")
    monkeypatch.setenv("MRA_RECOVERY_WORKER_COUNT", "1")


def task(state="EXTRACTING_FIELDS"):
    task_id = db.create_task("text", state, current_stage="extract_fields", input_text="SYNTHETIC INPUT")
    result = {"fields": {}, "draft": "SYNTHETIC retained draft", "raw_response": "unchanged"}
    db.update_task(task_id, result_json=json.dumps(result), retry_count=2)
    db.create_record_revision_for_task(task_id, result, source="unit_test", workflow_status="draft")
    db.create_task_step(task_id, "extract_fields", "RUNNING", input_snapshot={"retained": True})
    db.create_task_step(task_id, "load_input", "SUCCEEDED", input_snapshot={"retained": True})
    return task_id


def snapshot():
    with closing(db.get_connection()) as connection:
        return {name: [dict(row) for row in connection.execute(f"SELECT * FROM {name} ORDER BY id")]
                for name in ("agent_task", "agent_task_step", "record_revision", "approval",
                             "export_event", "audit_log", "audit_chain")}


def run_lifespan():
    async def run():
        async with main.lifespan(main.app):
            pass
    asyncio.run(run())


def test_enabled_lifespan_recovers_interrupted_task_without_provider(isolated, monkeypatch):
    enable(monkeypatch)
    task_id = task()
    run_lifespan()
    assert db.get_task(task_id)["status"] == "FAILED"
    assert db.get_task_steps(task_id)[0]["status"] == "FAILED"


def test_default_disabled_preserves_existing_startup_and_task(isolated):
    task()
    before = snapshot()
    run_lifespan()
    assert snapshot() == before
    assert not (isolated / "state.sqlite3.instance.lock").exists()


@pytest.mark.parametrize("failure_point", ["init_db", "prewarm", "llm_status"])
def test_lifespan_always_releases_lock_on_startup_or_exit_error(isolated, monkeypatch, failure_point):
    from app.services.task_recovery import TaskDatabaseLock
    from app.services.llm import readiness
    enable(monkeypatch)
    original_init = main.init_db
    def fail(*a, **kw):
        raise RuntimeError("injected_" + failure_point)
    if failure_point == "init_db":
        monkeypatch.setattr(main, "init_db", fail)
    elif failure_point == "prewarm":
        monkeypatch.setattr(main, "is_prewarm_enabled", lambda: True)
        monkeypatch.setattr(main, "start_funasr_prewarm", fail)
    elif failure_point == "llm_status":
        monkeypatch.setattr(factory, "get_llm_status", fail)
    async def run():
        async with main.lifespan(main.app):
            pytest.fail("startup should have failed")
    with pytest.raises(RuntimeError, match="injected_"):
        asyncio.run(run())
    with TaskDatabaseLock(db.get_db_path()):
        pass
    monkeypatch.setattr(main, "init_db", original_init)


def test_lifespan_locks_before_init_and_normal_exit_retains_until_process_exit(isolated, monkeypatch):
    from app.services.task_recovery import TaskDatabaseLock, RecoveryConfigurationError
    enable(monkeypatch)
    original_init = main.init_db
    observed = []
    def checked_init():
        with pytest.raises(RecoveryConfigurationError, match="占用"):
            with TaskDatabaseLock(db.get_db_path()):
                pass
        observed.append("locked_before_init")
        original_init()
    monkeypatch.setattr(main, "init_db", checked_init)
    run_lifespan()
    assert observed == ["locked_before_init"]
    with pytest.raises(RecoveryConfigurationError, match="本进程已占用"):
        with TaskDatabaseLock(db.get_db_path()):
            pass


@pytest.mark.parametrize("failure_point", ["body", "monitor_cleanup"])
def test_after_start_shutdown_error_retains_process_lock(isolated, monkeypatch, failure_point):
    from app.services.task_recovery import TaskDatabaseLock, RecoveryConfigurationError
    from app.services.llm import readiness
    enable(monkeypatch)
    def fail(*a, **kw):
        raise RuntimeError("injected_" + failure_point)
    if failure_point == "monitor_cleanup":
        monkeypatch.setattr(factory, "get_llm_status", lambda **kw: {"provider": "ollama", "mode": "edge"})
        monkeypatch.setattr(factory, "create_llm_provider", lambda: SimpleNamespace(base_url="no-network", model="test"))
        monkeypatch.setattr(readiness, "start_monitor", lambda *a, **kw: (SimpleNamespace(set=lambda: None), SimpleNamespace(join=fail)))
    async def run():
        async with main.lifespan(main.app):
            if failure_point == "body":
                fail()
    with pytest.raises(RuntimeError, match="injected_"):
        asyncio.run(run())
    with pytest.raises(RecoveryConfigurationError, match="本进程已占用"):
        with TaskDatabaseLock(db.get_db_path()):
            pass


def test_second_lifespan_refused_before_database_init(isolated, monkeypatch):
    from app.services.task_recovery import RecoveryConfigurationError
    enable(monkeypatch)
    calls = []
    original_init = main.init_db
    def tracked_init():
        calls.append(1)
        original_init()
    monkeypatch.setattr(main, "init_db", tracked_init)
    async def run():
        async with main.lifespan(main.app):
            with pytest.raises(RecoveryConfigurationError, match="占用"):
                async with main.lifespan(main.app):
                    pytest.fail("second instance must not start")
    asyncio.run(run())
    assert calls == [1]


def test_disabling_flag_cannot_reuse_retained_same_process_lock(isolated, monkeypatch):
    from app.services.task_recovery import RecoveryConfigurationError
    enable(monkeypatch)
    run_lifespan()
    monkeypatch.setenv("MRA_SINGLE_INSTANCE_RECOVERY_ENABLED", "0")
    with pytest.raises(RecoveryConfigurationError, match="本进程已占用"):
        run_lifespan()


def test_wrong_process_cannot_release_inherited_lock_handle(isolated):
    from app.services.task_recovery import TaskDatabaseLock, RecoveryConfigurationError
    lock = TaskDatabaseLock(db.get_db_path()).acquire()
    original_pid = lock.owner_pid
    try:
        lock.owner_pid = original_pid + 1
        with pytest.raises(RecoveryConfigurationError, match="其他进程"):
            lock.release()
        assert not lock.handle.closed
    finally:
        lock.owner_pid = original_pid
        lock.release()


@pytest.mark.parametrize("name,value", [
    ("MRA_RECOVERY_OLD_WRITERS_STOPPED", "0"),
    ("MRA_RECOVERY_WORKER_COUNT", ""),
    ("MRA_RECOVERY_WORKER_COUNT", "2"),
    ("WEB_CONCURRENCY", "2"),
    ("UVICORN_WORKERS", "2"),
    ("UVICORN_WORKERS", "unknown"),
])
def test_missing_or_multiworker_precondition_refuses_before_init(isolated, monkeypatch, name, value):
    from app.services.task_recovery import RecoveryConfigurationError
    enable(monkeypatch)
    monkeypatch.setenv(name, value)
    def forbidden():
        pytest.fail("must validate before database init")
    monkeypatch.setattr(main, "init_db", forbidden)
    with pytest.raises(RecoveryConfigurationError):
        run_lifespan()


def test_relative_database_path_refused_when_enabled(isolated, monkeypatch):
    from app.services.task_recovery import RecoveryConfigurationError
    enable(monkeypatch)
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", "relative.sqlite3")
    with pytest.raises(RecoveryConfigurationError, match="绝对路径"):
        run_lifespan()


def test_recovery_atomic_preserved_data_four_statuses_and_idempotence(isolated):
    from app.services.task_recovery import TaskDatabaseLock, fail_interrupted_tasks
    ids = [task(state) for state in ACTIVE]
    for state in ("WAITING_DOCTOR_REVIEW", "DONE", "FAILED", "UNRECOGNIZED_STATE"):
        task(state)
    before = snapshot()
    with TaskDatabaseLock(db.get_db_path()) as lock:
        assert fail_interrupted_tasks(lock) == ids
        after = snapshot()
        assert fail_interrupted_tasks(lock) == []
        assert snapshot() == after
    for old, new in zip(before["agent_task"], after["agent_task"]):
        if old["id"] not in ids:
            assert old == new
            continue
        assert new["status"] == "FAILED" and new["completed_at"]
        for key in ("input_text", "result_json", "retry_count", "encounter_id", "current_record_revision_id"):
            assert old[key] == new[key]
    for old, new in zip(before["agent_task_step"], after["agent_task_step"]):
        if old["task_id"] in ids and old["status"] == "RUNNING":
            assert new["status"] == "FAILED" and new["ended_at"]
            assert old["input_snapshot_json"] == new["input_snapshot_json"]
            assert old["output_snapshot_json"] == new["output_snapshot_json"]
        else:
            assert old == new
    for table in ("record_revision", "approval", "export_event"):
        assert before[table] == after[table]
    assert len(after["audit_log"]) - len(before["audit_log"]) == 4
    assert len(after["audit_chain"]) - len(before["audit_chain"]) == 4


def test_audit_failure_rolls_back_tasks_steps_and_audit(isolated, monkeypatch):
    from app.services.task_recovery import TaskDatabaseLock, fail_interrupted_tasks
    task("CREATED")
    task("GENERATING_DRAFT")
    before = snapshot()
    original = db._insert_audit_log_row
    count = 0
    def fail_on_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("injected audit failure")
        return original(*args, **kwargs)
    monkeypatch.setattr(db, "_insert_audit_log_row", fail_on_second)
    with TaskDatabaseLock(db.get_db_path()) as lock, pytest.raises(RuntimeError, match="injected audit"):
        fail_interrupted_tasks(lock)
    assert count == 2
    assert snapshot() == before


def test_active_approval_anomaly_refuses_whole_lifespan_and_releases(isolated, monkeypatch):
    from app.services.task_recovery import TaskDatabaseLock, RecoveryStateError
    enable(monkeypatch)
    task("CREATED")
    signed = task()
    db.create_approval_for_task(signed)
    db.update_task(signed, status="EXTRACTING_FIELDS", current_stage="extract_fields")
    before = snapshot()
    with pytest.raises(RecoveryStateError, match="批准"):
        run_lifespan()
    assert snapshot() == before
    with TaskDatabaseLock(db.get_db_path()):
        pass


@pytest.mark.parametrize("legacy_task_id", [None, "other"])
def test_noncurrent_revision_approval_with_bad_task_link_refuses(isolated, legacy_task_id):
    from app.services.task_recovery import TaskDatabaseLock, RecoveryStateError, fail_interrupted_tasks
    signed = task()
    approval = db.create_approval_for_task(signed)
    other = task("WAITING_DOCTOR_REVIEW")
    other_encounter = db.get_task(other)["encounter_id"]
    db.create_record_revision_for_task(signed, {"fields": {}, "draft": "next synthetic revision"},
                                       source="test", workflow_status="draft", invalidate_approvals=False)
    with closing(db.get_connection()) as connection, connection:
        connection.execute("UPDATE approval SET task_id = ?, encounter_id = ? WHERE id = ?",
                           (None if legacy_task_id is None else other, other_encounter, approval["id"]))
    db.update_task(signed, status="GENERATING_DRAFT", current_stage="generate_draft")
    before = snapshot()
    with TaskDatabaseLock(db.get_db_path()) as lock, pytest.raises(RecoveryStateError, match="批准"):
        fail_interrupted_tasks(lock)
    assert snapshot() == before


def test_changed_database_and_closed_handle_refuse_without_writes(isolated, monkeypatch):
    from app.services.task_recovery import TaskDatabaseLock, RecoveryConfigurationError, fail_interrupted_tasks
    task()
    database = db.get_db_path()
    before = snapshot()
    lock = TaskDatabaseLock(database).acquire()
    try:
        monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(isolated / "different.sqlite3"))
        with pytest.raises(RecoveryConfigurationError, match="变化"):
            fail_interrupted_tasks(lock)
        monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(database))
        lock.handle.close()
        with TaskDatabaseLock(database):
            with pytest.raises(RecoveryConfigurationError, match="有效锁"):
                fail_interrupted_tasks(lock)
        assert snapshot() == before
    finally:
        lock.release()


@pytest.mark.parametrize("stop_mode", ["graceful", "kill"])
def test_real_process_holds_after_lifespan_and_os_releases_on_exit(isolated, stop_mode):
    from app.services.task_recovery import TaskDatabaseLock
    ready = isolated / "lifespan-exited.txt"
    stop = isolated / "exit-process.txt"
    environment = dict(os.environ)
    for key in list(environment):
        if key.startswith("ONLINE_LLM_"):
            del environment[key]
    environment.update({"MRA_SINGLE_INSTANCE_RECOVERY_ENABLED": "1", "MRA_RECOVERY_OLD_WRITERS_STOPPED": "1",
                        "MRA_RECOVERY_WORKER_COUNT": "1", "ASR_PREWARM_ENABLED": "0", "LLM_PROVIDER": "mock",
                        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    child_code = '''
import asyncio, pathlib, sys, time
from app import main
from app.services.llm import factory
factory.get_llm_status = lambda **kw: {"provider": "mock", "mode": "demo"}
def forbidden(*a, **kw): raise AssertionError("provider forbidden")
factory.create_llm_provider = forbidden
main.start_funasr_prewarm = forbidden
async def once():
    async with main.lifespan(main.app): pass
asyncio.run(once())
pathlib.Path(sys.argv[1]).write_text("lifespan exited; process alive")
deadline = time.monotonic() + 30
while not pathlib.Path(sys.argv[2]).exists() and time.monotonic() < deadline: time.sleep(.03)
'''
    child = subprocess.Popen([sys.executable, "-B", "-c", child_code, str(ready), str(stop)],
                             env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(.03)
        assert ready.exists(), child.communicate(timeout=2)
        from app.services.task_recovery import RecoveryConfigurationError
        with pytest.raises(RecoveryConfigurationError, match="占用"):
            with TaskDatabaseLock(db.get_db_path()):
                pass
        if stop_mode == "kill":
            child.kill()
        else:
            stop.write_text("normal exit", encoding="ascii")
        child.wait(timeout=10)
        if stop_mode == "graceful":
            assert child.returncode == 0, child.stderr.read()
        with TaskDatabaseLock(db.get_db_path()):
            pass
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
