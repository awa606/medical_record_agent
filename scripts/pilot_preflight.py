from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from app.api.audio import DEFAULT_UPLOAD_DIR
from app.db.sqlite import DEFAULT_DB_PATH
from app.services.asr.speaker_profiles import DEFAULT_PROFILE_DIR
from app.services.exporter import DEFAULT_OUTPUT_DIR
from app.services.llm.factory import get_llm_status


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIN_FREE_BYTES = 50 * 1024 * 1024
SECRET_NAME_PARTS = ("PASSWORD", "TOKEN", "KEY", "SECRET")
WEAK_PASSWORDS = {"admin", "admin123", "admin123456", "password", "12345678"}


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def apply_env_file(path: Path | None) -> list[str]:
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(f"Environment file not found: {path}")
    values = parse_env_file(path)
    for key, value in values.items():
        os.environ[key] = value
    return sorted(values)


def sanitized_for_output(value: Any, key: str | None = None) -> Any:
    if key and _is_secret_name(key):
        return "" if value is None or value == "" else "***REDACTED***"
    if isinstance(value, dict):
        return {item_key: sanitized_for_output(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [sanitized_for_output(item) for item in value]
    return value


def run_preflight(
    *,
    env_file: Path | None = None,
    require_existing_db: bool = False,
    check_provider_reachable: bool = False,
) -> dict[str, Any]:
    loaded_env_keys = apply_env_file(env_file)
    min_free_bytes = _min_free_bytes()
    checks = {
        "database": _check_database(_db_path(), require_existing=require_existing_db),
        "uploads": _check_directory("uploads", _upload_dir(), min_free_bytes=min_free_bytes),
        "outputs": _check_directory("outputs", _output_dir(), min_free_bytes=min_free_bytes),
        "speaker_profiles": _check_directory(
            "speaker_profiles",
            _speaker_profile_dir(),
            min_free_bytes=min_free_bytes,
        ),
        "auth": _check_auth(),
        "provider": _check_provider(check_reachable=check_provider_reachable),
    }
    disk_ok = all(
        checks[name].get("free_bytes", 0) is not None
        and int(checks[name].get("free_bytes") or 0) >= min_free_bytes
        for name in ("uploads", "outputs", "speaker_profiles")
    )
    checks["disk"] = {
        "ok": disk_ok,
        "min_free_bytes": min_free_bytes,
        "paths": {
            name: {
                "path": checks[name].get("path"),
                "free_bytes": checks[name].get("free_bytes"),
            }
            for name in ("uploads", "outputs", "speaker_profiles")
        },
    }
    ok = all(bool(check.get("ok")) for check in checks.values())
    return sanitized_for_output(
        {
            "ok": ok,
            "loaded_env_keys": loaded_env_keys,
            "checks": checks,
        }
    )


def _db_path() -> Path:
    return Path(os.environ.get("MEDICAL_RECORD_AGENT_DB", DEFAULT_DB_PATH))


def _upload_dir() -> Path:
    return Path(os.environ.get("MEDICAL_RECORD_AGENT_UPLOAD_DIR", DEFAULT_UPLOAD_DIR))


def _output_dir() -> Path:
    return Path(os.environ.get("MEDICAL_RECORD_AGENT_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))


def _speaker_profile_dir() -> Path:
    return Path(os.environ.get("MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR", DEFAULT_PROFILE_DIR))


def _min_free_bytes() -> int:
    raw = os.environ.get("MEDICAL_RECORD_AGENT_MIN_FREE_BYTES")
    if not raw:
        return DEFAULT_MIN_FREE_BYTES
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MIN_FREE_BYTES
    return value if value > 0 else DEFAULT_MIN_FREE_BYTES


def _check_database(path: Path, *, require_existing: bool) -> dict[str, Any]:
    check: dict[str, Any] = {
        "ok": False,
        "path": str(path),
        "exists": path.exists(),
        "parent_writable": False,
        "quick_check": None,
        "error": None,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _probe_directory_write(path.parent)
        check["parent_writable"] = True
        if not path.exists():
            if require_existing:
                check["error"] = "SQLite database does not exist"
                return check
            check["ok"] = True
            check["note"] = "Database will be created by application startup"
            return check
        with closing(sqlite3.connect(f"file:{path}?mode=rw", uri=True)) as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
        check["quick_check"] = quick_check[0] if quick_check else None
        check["ok"] = check["quick_check"] == "ok"
        if not check["ok"]:
            check["error"] = f"sqlite quick_check returned {check['quick_check']}"
    except (OSError, sqlite3.Error) as exc:
        check["error"] = str(exc)
    return check


def _check_directory(name: str, path: Path, *, min_free_bytes: int) -> dict[str, Any]:
    check: dict[str, Any] = {
        "ok": False,
        "path": str(path),
        "exists": path.exists(),
        "free_bytes": None,
        "error": None,
    }
    try:
        path.mkdir(parents=True, exist_ok=True)
        _probe_directory_write(path)
        free_bytes = shutil.disk_usage(path).free
        check["free_bytes"] = free_bytes
        if free_bytes < min_free_bytes:
            check["error"] = f"{name} free space below {min_free_bytes} bytes"
            return check
        check["ok"] = True
    except OSError as exc:
        check["error"] = str(exc)
    return check


def _probe_directory_write(path: Path) -> None:
    with tempfile.NamedTemporaryFile(prefix=".mra-preflight-", dir=path, delete=False) as handle:
        probe_path = Path(handle.name)
        handle.write(b"ok")
    probe_path.unlink(missing_ok=True)


def _check_auth() -> dict[str, Any]:
    mode = _record_provider_mode()
    bootstrap_enabled = _truthy(os.environ.get("MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP", "1"))
    username = os.environ.get("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME", "admin")
    password = os.environ.get("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD", "")
    check: dict[str, Any] = {
        "ok": True,
        "mode": mode,
        "bootstrap_enabled": bootstrap_enabled,
        "username": username,
        "password_configured": bool(password),
        "error": None,
    }
    if mode not in {"edge", "live"}:
        if bootstrap_enabled and _is_weak_password(password or "admin123456", username):
            check["warning"] = "Bootstrap admin password is weak; do not use this outside demo mode"
        return check
    if not bootstrap_enabled:
        check["warning"] = "Auth bootstrap is disabled; verify users already exist in the pilot database"
        return check
    if not password:
        check["ok"] = False
        check["error"] = "Edge/Live mode requires MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD"
        return check
    if _is_weak_password(password, username):
        check["ok"] = False
        check["error"] = "Edge/Live mode requires a strong bootstrap admin password"
    return check


def _check_provider(*, check_reachable: bool) -> dict[str, Any]:
    status = get_llm_status(check_reachable=check_reachable)
    mode = str(status.get("mode") or _record_provider_mode()).lower()
    ok = True
    error = None
    if mode in {"edge", "live"}:
        if status.get("provider") == "mock":
            ok = False
            error = "Edge/Live mode requires online or ollama provider"
        elif not status.get("configured"):
            ok = False
            error = status.get("fallback_reason") or "Provider configuration is incomplete"
        elif status.get("fallback"):
            ok = False
            error = status.get("fallback_reason") or "Provider would fallback in edge/live mode"
        elif check_reachable and not status.get("reachable"):
            ok = False
            error = status.get("fallback_reason") or "Provider reachability check failed"
    return {"ok": ok, "status": status, "error": error}


def _record_provider_mode() -> str:
    return (os.environ.get("RECORD_PROVIDER_MODE") or "demo").strip().lower() or "demo"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() not in {"0", "false", "no", "off"}


def _is_weak_password(password: str, username: str) -> bool:
    lowered = password.lower()
    return len(password) < 10 or lowered in WEAK_PASSWORDS or lowered == username.lower()


def _is_secret_name(name: str) -> bool:
    upper_name = name.upper()
    return (
        upper_name == "PASSWORD"
        or upper_name.endswith("_PASSWORD")
        or upper_name.endswith("_TOKEN")
        or upper_name.endswith("_API_KEY")
        or upper_name.endswith("_KEY")
        or upper_name.endswith("_SECRET")
        or "_SECRET_" in upper_name
    )


def format_text_report(report: dict[str, Any]) -> str:
    lines = [f"pilot preflight: {'OK' if report['ok'] else 'FAILED'}"]
    loaded = report.get("loaded_env_keys") or []
    if loaded:
        lines.append(f"loaded env keys: {', '.join(loaded)}")
    for name, check in report["checks"].items():
        state = "OK" if check.get("ok") else "FAILED"
        detail = check.get("error") or check.get("warning") or check.get("note") or ""
        suffix = f" - {detail}" if detail else ""
        lines.append(f"[{state}] {name}{suffix}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run department pilot startup preflight checks.")
    parser.add_argument("--env-file", type=Path, help="Optional environment file to load before checking.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--require-existing-db", action="store_true", help="Fail if the SQLite database file is absent.")
    parser.add_argument(
        "--check-provider-reachable",
        action="store_true",
        help="Call the configured LLM provider instead of only checking configuration.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_preflight(
            env_file=args.env_file,
            require_existing_db=args.require_existing_db,
            check_provider_reachable=args.check_provider_reachable,
        )
    except Exception as exc:  # noqa: BLE001 - CLI should return a readable failure.
        report = {"ok": False, "checks": {"preflight": {"ok": False, "error": str(exc)}}}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
