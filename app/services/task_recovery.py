"""Opt-in, single-worker recovery for cooperating processes on one OS.

This lock does not stop old applications that ignore it. Deployment must first
verify all such writers are stopped. It is not a distributed queue or lease.
"""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
from typing import BinaryIO

from app.db import sqlite as db


INTERRUPTIBLE_STATUSES = ("CREATED", "EXTRACTING_FIELDS", "GENERATING_DRAFT", "SAFETY_CHECKING")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"", "0", "false", "no", "off"}
# A successfully started application can still have request/daemon writers after
# lifespan exits. Keep its lock until OS process exit, not merely ASGI shutdown.
_PROCESS_LOCKS: dict[tuple[int, str], "TaskDatabaseLock"] = {}


class RecoveryConfigurationError(RuntimeError):
    """Refuse startup rather than bypass required ownership guarantees."""


class RecoveryStateError(RuntimeError):
    """Persisted workflow and signature disagree; operator inspection required."""


class TaskDatabaseLock:
    def __init__(self, database: Path):
        database = Path(database)
        if not database.is_absolute():
            raise RecoveryConfigurationError("启用中断恢复时数据库必须使用绝对路径。")
        self.database = database.resolve()
        self.path = self.database.with_name(self.database.name + ".instance.lock")
        self.handle: BinaryIO | None = None
        self.owner_pid: int | None = None

    def acquire(self) -> "TaskDatabaseLock":
        if (os.getpid(), str(self.database)) in _PROCESS_LOCKS:
            raise RecoveryConfigurationError("本进程已占用该数据库；恢复模式不支持同进程重新启动应用。")
        if self.handle is not None:
            raise RecoveryConfigurationError("数据库锁对象已经使用，不能重复获取。")
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
            raise RecoveryConfigurationError("数据库已被其他协作实例占用，拒绝启动。") from exc
        self.handle, self.owner_pid = handle, os.getpid()
        return self

    def require_owned(self) -> None:
        if self.handle is None or self.handle.closed or self.owner_pid != os.getpid():
            raise RecoveryConfigurationError("中断恢复必须持有本进程的有效锁。")
        try:
            os.fstat(self.handle.fileno())
        except (OSError, ValueError) as exc:
            raise RecoveryConfigurationError("中断恢复必须持有本进程的有效锁。") from exc
        if db.get_db_path().resolve() != self.database:
            raise RecoveryConfigurationError("取得锁后数据库配置发生变化，拒绝恢复。")

    def release(self) -> None:
        if _PROCESS_LOCKS.get((os.getpid(), str(self.database))) is self:
            raise RecoveryConfigurationError("已启动应用的数据库锁必须保留到进程退出。")
        if self.handle is None:
            return
        if self.owner_pid != os.getpid():
            raise RecoveryConfigurationError("其他进程持有的数据库锁不能由本进程释放。")
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
        # Never unlink: another opener must see the same inode/lock byte.

    def __enter__(self) -> "TaskDatabaseLock":
        return self.acquire()

    def __exit__(self, *_args) -> None:
        self.release()


def acquire_startup_lock() -> TaskDatabaseLock | None:
    """Default off. Environment declarations supplement deployment inspection."""
    if (os.getpid(), str(db.get_db_path().resolve())) in _PROCESS_LOCKS:
        raise RecoveryConfigurationError("本进程已占用该数据库；恢复模式不支持同进程重新启动应用。")
    enabled = os.environ.get("MRA_SINGLE_INSTANCE_RECOVERY_ENABLED", "0").strip().lower()
    if enabled in _FALSE:
        return None
    if enabled not in _TRUE:
        raise RecoveryConfigurationError("MRA_SINGLE_INSTANCE_RECOVERY_ENABLED 必须是明确的开关值。")
    if os.environ.get("MRA_RECOVERY_OLD_WRITERS_STOPPED", "").strip().lower() not in _TRUE:
        raise RecoveryConfigurationError("启用恢复前必须核验并声明旧写入实例已经停止。")
    if os.environ.get("MRA_RECOVERY_WORKER_COUNT", "").strip() != "1":
        raise RecoveryConfigurationError("中断恢复仅支持明确声明的单 worker。")
    for variable in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        value = os.environ.get(variable)
        if value is not None and value.strip() != "1":
            raise RecoveryConfigurationError(f"{variable} 与单 worker 恢复约束不一致。")
    return TaskDatabaseLock(db.get_db_path()).acquire()


def retain_lock_until_process_exit(lock: TaskDatabaseLock) -> None:
    """No atexit unlock: the OS closes the handle when the process is gone."""
    lock.require_owned()
    key = (os.getpid(), str(lock.database))
    if key in _PROCESS_LOCKS:
        raise RecoveryConfigurationError("本进程已占用该数据库，禁止重复绑定。")
    _PROCESS_LOCKS[key] = lock


def fail_interrupted_tasks(lock: TaskDatabaseLock) -> list[int]:
    """Atomically fail unfinished automatic work; never call or retry a provider."""
    lock.require_owned()
    with closing(db.get_connection()) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in INTERRUPTIBLE_STATUSES)
            tasks = connection.execute(
                f"SELECT * FROM agent_task WHERE status IN ({placeholders}) ORDER BY id",
                INTERRUPTIBLE_STATUSES,
            ).fetchall()
            for task in tasks:
                # Legacy approval.task_id can be NULL: follow any linked revision,
                # not only the task's current revision, before changing workflow.
                active = connection.execute(
                    "SELECT 1 FROM approval a LEFT JOIN record_revision r ON r.id = a.revision_id "
                    "WHERE a.status = 'active' AND a.invalidated_at IS NULL AND "
                    "(a.task_id = ? OR r.task_id = ? OR a.revision_id = ? OR a.encounter_id = ?) LIMIT 1",
                    (task["id"], task["id"], task["current_record_revision_id"], task["encounter_id"]),
                ).fetchone()
                if active:
                    raise RecoveryStateError("未完成任务存在有效批准关联，停止恢复，请核查任务与病历版本。")
            now = db.utc_now()
            message = "上次处理因服务中断未完成；原文和已有病历已保留，请检查后手动选择继续操作。系统未自动重试。"
            for task in tasks:
                connection.execute(
                    "UPDATE agent_task SET status = 'FAILED', current_stage = 'failed', "
                    "error_message = ?, updated_at = ?, completed_at = ? WHERE id = ?",
                    (message, now, now, task["id"]),
                )
                connection.execute(
                    "UPDATE agent_task_step SET status = 'FAILED', ended_at = ?, error_message = ? "
                    "WHERE task_id = ? AND status = 'RUNNING'",
                    (now, message, task["id"]),
                )
                db._insert_audit_log_row(
                    connection, task_id=task["id"], event_type="interrupted_task_recovered_as_failed",
                    event_detail={"previous_status": task["status"], "automatic_retry": False,
                                  "reason": "single_instance_startup_recovery"},
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return [int(task["id"]) for task in tasks]
