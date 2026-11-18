from __future__ import annotations

import hmac
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.audio import DEFAULT_UPLOAD_DIR, get_upload_dir
from app.api.auth import require_current_user
from app.db import get_connection, get_db_path, init_db
from app.services.audit_anchor import verify_with_anchor
from app.services.exporter import DEFAULT_OUTPUT_DIR
from app.services.asr.prewarm import get_prewarm_status
from app.services.llm.factory import get_llm_status
from app.services.llm.readiness import check as check_local_model
from app.services.llm.online_readiness import check as check_online_model
from app.services.runtime_limits import directory_free_bytes


router = APIRouter(tags=["runtime"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STARTED_AT = datetime.now(UTC).isoformat()


def _deployment_metadata() -> dict[str, Any]:
    path = PROJECT_ROOT / "static" / "deployment.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


@router.get("/version")
def version() -> dict[str, Any]:
    """Version and provider identity for demo evidence and support tickets."""
    metadata = _deployment_metadata()
    status = get_llm_status(check_reachable=False)
    return {
        "service": "medical-record-agent",
        "version": metadata.get("version") or "unregistered",
        "deployment_mode": metadata.get("mode") or "development",
        "label": metadata.get("label"),
        "provider": status.get("provider"),
        "record_provider_mode": status.get("mode"),
        "started_at": STARTED_AT,
    }


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
    if mode == "edge" and status.get("provider") != "ollama":
        ok, error = False, "Edge mode requires a local Ollama provider"
    if (mode == "live" and status.get("provider") == "online"
            and os.environ.get("ONLINE_LLM_PROFILE") != "deepseek_demo"):
        ok, error = False, "ONLINE_READINESS_PROFILE_REQUIRED"
    if ok and mode in {"live", "edge"} and status.get("provider") == "ollama":
        from app.services.llm.factory import create_llm_provider
        try:
            provider = create_llm_provider(mode=mode)
        except RuntimeError:
            return {"ok": False, "status": status, "error": "Local provider configuration is invalid"}
        probe = check_local_model(provider.base_url, provider.model)
        status["runtime_probe"] = probe
        ok, error = probe["ok"], probe.get("error")
        status.update(checked=True, reachable=ok, fallback=False, fallback_reason=error)
        if mode == "edge":
            status["fallback_provider"] = None
    if (ok and mode == "live" and status.get("provider") == "online"
            and os.environ.get("ONLINE_LLM_PROFILE") == "deepseek_demo"):
        from app.services.llm.factory import create_llm_provider
        try:
            provider = create_llm_provider(mode=mode)
            probe = check_online_model(provider)
        except Exception:
            probe = {"ok": False, "error": "ONLINE_CONFIGURATION_INVALID", "inference_called": False}
        ok, error = probe["ok"], probe.get("error")
        status["runtime_probe"] = probe
        status.update(checked=True, reachable=ok, fallback=False, fallback_reason=error,
                      fallback_provider=None)
    return {"ok": ok, "status": status, "error": error}


def _check_asr_models() -> dict[str, Any]:
    status = get_prewarm_status()
    configured_asr = (
        os.environ.get("MEDICAL_RECORD_AGENT_ASR_ENGINE")
        or os.environ.get("ASR_ENGINE")
        or ""
    ).strip().lower()
    require_funasr = os.environ.get("MEDICAL_RECORD_AGENT_REQUIRE_FUNASR", "").lower() in {"1", "true", "yes"}
    require_funasr = require_funasr or configured_asr == "funasr"
    ok = True
    error = None
    if require_funasr and status.get("status") != "ready":
        ok = False
        error = status.get("last_error") or "FunASR model prewarm has not completed"
    if require_funasr and status.get('profile', 'streaming') != os.getenv('ASR_PREWARM_PROFILE', 'streaming'):
        ok, error = False, 'ASR profile changed; restart and warm the selected models'
    return {
        "ok": ok,
        "status": status.get("status"),
        "profile": status.get('profile', 'streaming'),
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


def _metrics_authorized(request: Request) -> bool:
    expected = os.environ.get("MRA_METRICS_TOKEN", "").strip()
    if expected:
        header = request.headers.get("authorization") or ""
        if header.lower().startswith("bearer "):
            supplied = header.split(" ", 1)[1].strip()
            # compare_digest needs bytes: a non-ASCII header must be a clean
            # rejection, not a TypeError that surfaces as HTTP 500.
            if hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
                return True
    try:
        user = require_current_user(request)
    except HTTPException:
        return False
    return user.role == "admin"


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"]) if row is not None else 0


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(request: Request) -> PlainTextResponse:
    """Aggregate-only Prometheus metrics. No patient text is ever exposed."""
    if not _metrics_authorized(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    init_db()
    db_path = get_db_path()
    with closing(get_connection()) as connection:
        counts = {
            table: _table_count(connection, table)
            for table in (
                "patient",
                "encounter",
                "record_revision",
                "approval",
                "export_event",
                "audit_log",
                "audit_chain",
                "auth_user",
            )
        }
    try:
        db_size = db_path.stat().st_size
    except OSError:
        db_size = 0
    chain = verify_with_anchor()
    status = get_llm_status(check_reachable=False)
    lines = [
        "# HELP mra_info Build information as labels.",
        "# TYPE mra_info gauge",
        f'mra_info{{mode="{status.get("mode")}",provider="{status.get("provider")}"}} 1',
    ]
    for table, value in counts.items():
        lines.extend(
            [
                f"# HELP mra_{table}_total Rows in the {table} table.",
                f"# TYPE mra_{table}_total gauge",
                f"mra_{table}_total {value}",
            ]
        )
    lines.extend(
        [
            "# HELP mra_db_size_bytes Size of the SQLite database file.",
            "# TYPE mra_db_size_bytes gauge",
            f"mra_db_size_bytes {db_size}",
            "# HELP mra_audit_chain_valid Whether the audit hash chain verifies.",
            "# TYPE mra_audit_chain_valid gauge",
            f"mra_audit_chain_valid {1 if chain.get('ok') else 0}",
            "# HELP mra_audit_chain_entries Entries in the audit hash chain.",
            "# TYPE mra_audit_chain_entries gauge",
            f"mra_audit_chain_entries {int(chain.get('entries') or 0)}",
            "# HELP mra_audit_anchor_checked Whether an external anchor was compared.",
            "# TYPE mra_audit_anchor_checked gauge",
            f"mra_audit_anchor_checked {1 if (chain.get('anchor') or {}).get('checked') else 0}",
        ]
    )
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
