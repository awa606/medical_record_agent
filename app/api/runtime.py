from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.audio import DEFAULT_UPLOAD_DIR, get_upload_dir
from app.db import get_connection, get_db_path, init_db
from app.services.exporter import DEFAULT_OUTPUT_DIR
from app.services.asr.prewarm import get_prewarm_status
from app.services.llm.factory import get_llm_status
from app.services.runtime_limits import directory_free_bytes


router = APIRouter(tags=["runtime"])


def _output_dir() -> Path:
    return Path(os.environ.get("MEDICAL_RECORD_AGENT_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))


def _speaker_profile_dir() -> Path:
    return Path(
        os.environ.get(
            "MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR",
            Path(__file__).resolve().parents[2] / "data" / "speaker_profiles",
        )
    )


def _min_free_bytes() -> int:
    try:
        return int(os.environ.get("MEDICAL_RECORD_AGENT_MIN_FREE_BYTES", str(50 * 1024 * 1024)))
    except ValueError:
        return 50 * 1024 * 1024


def _check_directory(name: str, path: Path, *, min_free_bytes: int) -> dict[str, Any]:
    check = {"ok": False, "path": str(path), "free_bytes": None, "error": None}
    probe = path / f".ready-{uuid.uuid4().hex}.tmp"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        free_bytes = directory_free_bytes(path)
        check["free_bytes"] = free_bytes
        if free_bytes < min_free_bytes:
            check["error"] = f"{name} free space below {min_free_bytes} bytes"
            return check
        check["ok"] = True
    except Exception as exc:  # noqa: BLE001
        check["error"] = str(exc)
        probe.unlink(missing_ok=True)
    return check


def _check_sqlite() -> dict[str, Any]:
    db_path = get_db_path()
    check = {"ok": False, "path": str(db_path), "journal_mode": None, "quick_check": None, "error": None}
    try:
        init_db()
        with closing(get_connection()) as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
            connection.execute(
                "CREATE TABLE IF NOT EXISTS runtime_readiness_probe (id TEXT PRIMARY KEY, created_at TEXT NOT NULL)"
            )
            probe_id = uuid.uuid4().hex
            connection.execute(
                "INSERT INTO runtime_readiness_probe (id, created_at) VALUES (?, datetime('now'))",
                (probe_id,),
            )
            connection.execute("DELETE FROM runtime_readiness_probe WHERE id = ?", (probe_id,))
            connection.commit()
        check["quick_check"] = quick_check[0] if quick_check else None
        check["journal_mode"] = journal_mode[0] if journal_mode else None
        check["ok"] = check["quick_check"] == "ok"
        if not check["ok"]:
            check["error"] = f"sqlite quick_check returned {check['quick_check']}"
    except (RuntimeError, sqlite3.Error, OSError) as exc:
        check["error"] = str(exc)
    return check


def _check_provider() -> dict[str, Any]:
    status = get_llm_status(check_reachable=False)
    mode = str(status.get("mode") or "demo").lower()
    ok = True
    error = None
    if mode in {"live", "edge"}:
        if status.get("provider") == "mock" or status.get("fallback") or not status.get("configured"):
            ok = False
            error = status.get("fallback_reason") or "Live/Edge mode requires a configured non-mock provider"
    return {"ok": ok, "status": status, "error": error}


def _check_asr_models() -> dict[str, Any]:
    status = get_prewarm_status()
    require_funasr = os.environ.get("MEDICAL_RECORD_AGENT_REQUIRE_FUNASR", "").lower() in {"1", "true", "yes"}
    ok = True
    error = None
    if require_funasr and status.get("status") != "ready":
        ok = False
        error = status.get("last_error") or "FunASR model prewarm has not completed"
    return {
        "ok": ok,
        "status": status.get("status"),
        "error_category": status.get("error_category"),
        "retryable": status.get("retryable"),
        "components": status.get("components", []),
        "model_cache": status.get("model_cache"),
        "error": error,
    }


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def ready() -> JSONResponse:
    min_free = _min_free_bytes()
    checks = {
        "sqlite": _check_sqlite(),
        "uploads": _check_directory("uploads", get_upload_dir(), min_free_bytes=min_free),
        "outputs": _check_directory("outputs", _output_dir(), min_free_bytes=min_free),
        "speaker_profiles": _check_directory("speaker_profiles", _speaker_profile_dir(), min_free_bytes=min_free),
        "provider": _check_provider(),
        "asr_models": _check_asr_models(),
    }
    ok = all(check.get("ok") for check in checks.values())
    status_code = 200 if ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if ok else "not_ready",
            "checks": checks,
        },
    )
