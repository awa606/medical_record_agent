from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db import audit_chain_head, verify_audit_chain


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANCHOR_PATH = PROJECT_ROOT / "data" / "audit-anchors.jsonl"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def anchor_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    return Path(os.environ.get("MRA_AUDIT_ANCHOR_FILE", DEFAULT_ANCHOR_PATH))


def _anchor_key() -> bytes | None:
    raw = os.environ.get("MRA_AUDIT_ANCHOR_KEY", "").strip()
    return raw.encode("utf-8") if raw else None


def _canonical(entry: dict[str, Any]) -> str:
    payload = {
        "anchored_at": entry.get("anchored_at"),
        "entries": entry.get("entries"),
        "head_hash": entry.get("head_hash"),
        "key_id": entry.get("key_id"),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _signature(key: bytes, entry: dict[str, Any]) -> str:
    return hmac.new(key, _canonical(entry).encode("utf-8"), hashlib.sha256).hexdigest()


def append_anchor(path: Path | None = None) -> dict[str, Any]:
    """Record the current chain head outside the database.

    The file is the external witness: a chain that was truncated at its tail no
    longer reaches the anchored entry count or hash. With
    ``MRA_AUDIT_ANCHOR_KEY`` set, each line is also HMAC-signed so a forged
    anchor line is rejected.
    """
    target = anchor_path(path)
    head = audit_chain_head()
    entry: dict[str, Any] = {"anchored_at": datetime.now(UTC).isoformat(), **head}
    key = _anchor_key()
    if key is not None:
        entry["signature"] = _signature(key, entry)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_last_anchor(path: Path | None = None) -> dict[str, Any] | None:
    target = anchor_path(path)
    if not target.exists():
        return None
    last: dict[str, Any] | None = None
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except ValueError:
            continue
    return last


def verify_with_anchor(path: Path | None = None) -> dict[str, Any]:
    anchor = read_last_anchor(path)
    if anchor is None:
        report = verify_audit_chain()
        report["anchor"] = {"checked": False, "reason": "no_anchor"}
        if (os.environ.get("MRA_REQUIRE_AUDIT_ANCHOR") or "").strip().lower() in _TRUE_VALUES:
            report["ok"] = False
            report["reason"] = "anchor_missing"
        return report

    if not isinstance(anchor.get("entries"), int) or int(anchor["entries"]) <= 0:
        report = verify_audit_chain()
        report["ok"] = False
        report["reason"] = "anchor_invalid"
        report["anchor"] = anchor
        return report

    key = _anchor_key()
    if key is not None:
        supplied = anchor.get("signature")
        if not supplied:
            report = verify_audit_chain()
            report["ok"] = False
            report["reason"] = "anchor_signature_missing"
            report["anchor"] = anchor
            return report
        if not hmac.compare_digest(str(supplied), _signature(key, anchor)):
            report = verify_audit_chain()
            report["ok"] = False
            report["reason"] = "anchor_signature_invalid"
            report["anchor"] = anchor
            return report

    return verify_audit_chain(anchor)
