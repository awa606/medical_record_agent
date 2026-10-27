"""Audit three saved I01 selections without inference, repair or production writes.

Only four preregistered labels in two source units are inspected. The report is
research evidence, not a new extraction contract or a production field status.
Run with ``python -m scripts.experiments.audit_cross_field_coverage``.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
from unittest.mock import patch

from app.services.field_grounding import FIELD_KEYS
from scripts.experiments.clinical_fact_selection import FactUnit, map_selection, selection_schema
from scripts.experiments.run_clinical_fact_selection import EXPECTED, score


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / ".artifacts/doctor-negative-20261027-r1"
DEFAULT_ARCHIVE = ROOT / ".artifacts/fact-selection-20261012-110022/compare"
DEFAULT_TRACE = OUTPUT_ROOT / "i01-offline-trace.json"
AUDIT_EXPECTED = {
    "chief_complaint": ("发热", "两天"),
    "present_illness": ("发热", "两天", "咳嗽", "咽痛"),
    "accompanying_symptoms": ("咳嗽", "咽痛"),
}
PROTOCOL_KEYS = {"chief_complaint": "chief", "present_illness": "present",
                 "accompanying_symptoms": "accompanying"}


class AuditStopped(ValueError):
    """A corrupt or drifting record cannot support a coverage conclusion."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise AuditStopped(code)


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditStopped("ORIGINAL_UNREADABLE") from exc
    _require(isinstance(value, dict), "ORIGINAL_OBJECT_REQUIRED")
    return value


def _frozen_expected(protocol: dict) -> dict[str, list[str]]:
    expected = (protocol.get("expected") or {}).get("I01")
    # Keep the original complete scorer's labels, including out-of-scope ones.
    _require(expected == EXPECTED["I01"], "FROZEN_EXPECTED_DRIFT")
    return {key: [label for label in expected[PROTOCOL_KEYS[key]] if label in labels]
            for key, labels in AUDIT_EXPECTED.items()}


def _units(catalog_rows: list[dict]) -> tuple[FactUnit, ...]:
    try:
        rows = tuple(FactUnit(**{**row, "types": tuple(row["types"]),
            "allowed_fields": tuple(row["allowed_fields"]), "anchors": tuple(row.get("anchors", ()))})
            for row in catalog_rows)
    except (KeyError, TypeError, ValueError) as exc:
        raise AuditStopped("CATALOG_INVALID") from exc
    _require(bool(rows) and len({r.id for r in rows}) == len(rows), "CATALOG_ID_INVALID")
    _require(all(isinstance(r.id, str) and isinstance(r.text, str)
                 and set(r.allowed_fields) <= set(FIELD_KEYS) for r in rows), "CATALOG_INVALID")
    return rows


def _projection(rows: tuple[FactUnit, ...]) -> list[dict]:
    return [{"id": r.id, "text": r.text, "speaker": r.speaker,
             "experiencer": r.experiencer, "assertion": r.assertion,
             "types": list(r.types), "allowed_fields": list(r.allowed_fields),
             "subject_context": list(r.anchors)} for r in rows]


def audit_selection(selection: dict, catalog_rows: list[dict], protocol: dict) -> dict:
    """Observe a field's own IDs only; never borrow or fill another field."""
    expected = _frozen_expected(protocol)
    units = _units(catalog_rows)
    prefix = (protocol.get("input_sha256") or {}).get("I01", "")
    _require(isinstance(prefix, str) and len(prefix) == 64, "INPUT_SHA_MISSING")
    _require(all(row.id.startswith(prefix[:16] + ":") for row in units), "CATALOG_FOREIGN_INPUT_ID")
    try:
        # Existing pure mapper enforces seven keys, IDs, uniqueness and scope.
        # Its newly constructed fields are discarded; no status is written back.
        map_selection(selection, units)
    except (ValueError, TypeError) as exc:
        raise AuditStopped(str(exc)) from exc
    bindings = {}
    for key, labels in expected.items():
        bindings[key] = {}
        for label in labels:
            matches = [r.id for r in units if label in r.text and key in r.allowed_fields
                       and r.experiencer == "patient" and r.speaker == "患者"
                       and r.assertion == "present"]
            _require(len(matches) == 1, "EXPECTED_UNIT_NOT_UNIQUE")
            bindings[key][label] = matches[0]
    result = {}
    for key, labels in expected.items():
        own = set(selection[key])
        covered = [label for label in labels if bindings[key][label] in own]
        missing = [label for label in labels if label not in covered]
        cross_missing = []
        for unit_id in dict.fromkeys(bindings[key][label] for label in missing):
            elsewhere = [other for other in FIELD_KEYS if other != key and unit_id in selection[other]]
            if elsewhere:
                cross_missing.append({"source_id": unit_id, "selected_in_fields": elsewhere,
                    "missing_labels": [label for label in missing if bindings[key][label] == unit_id]})
        result[key] = {"expected": labels, "selected_ids": deepcopy(selection[key]),
                       "covered": covered, "missing": missing, "cross_field_missing": cross_missing}
    return {"scope": "I01_FIXED_FOUR_LABELS_ONLY", "per_field": result,
            "distinct_label_count": len({label for labels in expected.values() for label in labels}),
            "distinct_source_unit_count": len({i for field in bindings.values() for i in field.values()}),
            "labels_are_not_independent_samples": True,
            "coverage_complete": all(not field["missing"] for field in result.values())}


def audit_record(record: dict, protocol: dict) -> dict:
    """Read saved first selection and final fields without running Generator."""
    _frozen_expected(protocol)
    _require(record.get("input_id") == "I01" and record.get("arm") == "candidate", "WRONG_CASE_OR_ARM")
    try:
        attempts = record["stages"]["attempts"]
        source = attempts[0]["input"]
        source_sha = hashlib.sha256(source.encode()).hexdigest()
        _require(len(attempts) == 1, "SINGLE_RECORDED_ATTEMPT_REQUIRED")
        _require(source_sha == protocol["input_sha256"]["I01"], "INPUT_SHA_DRIFT")
        request = record["request"]
        _require(_digest(request) == record["request_sha256"], "REQUEST_SHA_DRIFT")
        units = _units(record["catalog"])
        message_catalog = json.loads(request["messages"][0]["content"].split("以下全部为数据：\n", 1)[1])
        _require(message_catalog == _projection(units), "CATALOG_REQUEST_DRIFT")
        _require(request["format"] == selection_schema(units), "SCHEMA_CATALOG_DRIFT")
        _require(all(row.text in source for row in units), "CATALOG_SOURCE_DRIFT")
        raw = record["raw_ollama"]
        _require(raw.get("done") is True and raw.get("done_reason") == "stop", "RAW_RESPONSE_INCOMPLETE")
        first = json.loads(raw["message"]["content"])
        _require(first == record["selection_or_raw_fields"], "RAW_SELECTION_MISMATCH")
    except (KeyError, TypeError, IndexError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditStopped("RECORDED_RESPONSE_NOT_OBSERVABLE") from exc
    coverage = audit_selection(first, record["catalog"], protocol)
    # Existing score is secondary, and cannot overwrite saved scores/statuses.
    return {"input_id": "I01", "run": record["run"], "record_state": "OBSERVED",
            "input_sha256": source_sha, "catalog_sha256": _digest(record["catalog"]),
            "existing_call_created_at_utc": raw.get("created_at", "NOT_OBSERVABLE"),
            "original_selected_ids": deepcopy(first), "coverage": coverage,
            "preserved": {key: deepcopy(record.get(key)) for key in
                ("mapped_or_raw", "fields", "first_output_score", "final_score")},
            "compatibility_score": score("I01", source, deepcopy(record["fields"])),
            "production_status_changed": False, "answers_added": False,
            "new_model_calls": 0, "model_improvement_claimed": False}


def _verified_read(path: Path, receipts: dict[str, str]) -> tuple[dict, str]:
    key = str(path.resolve()).casefold()
    _require(key in receipts, "ORIGINAL_RECEIPT_MISSING")
    digest = sha256_file(path) if path.is_file() else None
    _require(digest == receipts[key], "ORIGINAL_SHA_DRIFT")
    value = _read(path)
    _require(sha256_file(path) == digest, "ORIGINAL_CHANGED_DURING_READ")
    return value, digest


def audit_archive(archive: Path, trace_path: Path) -> dict:
    """Verify local receipts then audit exactly the three registered outputs."""
    trace = _read(trace_path)
    trace_sha = sha256_file(trace_path)
    receipts = {str(Path(item["path"]).resolve()).casefold(): item["sha256"]
                for item in trace.get("original_evidence", [])}
    protocol_path = archive / "protocol.json"
    protocol, protocol_sha = _verified_read(protocol_path, receipts)
    _frozen_expected(protocol)
    records = []
    catalog_sha = None
    for run in (1, 2, 3):
        path = archive / f"I01-candidate-r{run}.private.json"
        try:
            record, digest = _verified_read(path, receipts)
            _require(record.get("run") == run, "RECORDED_RUN_DRIFT")
            result = audit_record(record, protocol)
            if catalog_sha is not None:
                _require(result["catalog_sha256"] == catalog_sha, "CROSS_RECORD_CATALOG_DRIFT")
            catalog_sha = result["catalog_sha256"]
            result["original"] = {"path": str(path.resolve()), "sha256": digest}
            _require(sha256_file(path) == digest, "ORIGINAL_CHANGED_DURING_AUDIT")
            records.append(result)
        except (AuditStopped, OSError) as exc:
            # No text/raw result from invalid evidence is treated as observed.
            records.append({"input_id": "I01", "run": run, "record_state": "STOPPED",
                            "reason": str(exc) if isinstance(exc, AuditStopped) else "ORIGINAL_UNREADABLE"})
    _require(sha256_file(protocol_path) == protocol_sha and sha256_file(trace_path) == trace_sha,
             "ANCHOR_CHANGED_DURING_AUDIT")
    return {"kind": "I01_OFFLINE_COVERAGE_AUDIT", "records": records,
            "records_observed": sum(r["record_state"] == "OBSERVED" for r in records),
            "records_stopped": sum(r["record_state"] == "STOPPED" for r in records),
            "new_model_calls": 0, "production_changed": False, "model_improvement_claimed": False,
            "scope": {"fixed_labels": 4, "source_units": 2, "not_four_samples": True},
            "trace_anchor": {"path": str(trace_path.resolve()), "sha256": trace_sha},
            "protocol_anchor": {"path": str(protocol_path.resolve()), "sha256": protocol_sha}}


def _write_private(output: Path, report: dict) -> None:
    output = output.resolve()
    _require(output != OUTPUT_ROOT.resolve() and output.is_relative_to(OUTPUT_ROOT.resolve()), "OUTPUT_OUTSIDE_LOCAL_AUDIT")
    _require(not output.exists(), "OUTPUT_ALREADY_EXISTS")
    output.mkdir(parents=True, exist_ok=False)
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["auditor_source_sha256"] = sha256_file(Path(__file__))
    for record in report["records"]:
        (output / f'I01-r{record["run"]}.private.json').write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.private.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    observed = [r for r in report["records"] if r["record_state"] == "OBSERVED"]
    incomplete = sum(not r["coverage"]["coverage_complete"] for r in observed)
    summary = ("I01离线覆盖审计\n"
               f'已核验原记录：{len(observed)}；停止记录：{report["records_stopped"]}。\n'
               f"审计范围：四个核对标签、两个原句单元，不是四个独立样本。\n"
               f"覆盖不足的历史首次结果：{incomplete}份。\n"
               "模型调用：0；原始选择、正文、引用、字段状态和评分均保留。\n"
               "审计可以定位漏选，不能补答案，也不代表模型质量改善或产品验收通过。\n"
               "原件和逐字段结果仅保存在本地private JSON，不上传原句或原始响应。\n")
    (output / "summary.zh.txt").write_text(summary, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT / "i01-coverage-audit-r1")
    args = parser.parse_args(argv)
    try:
        with patch.object(socket.socket, "connect", side_effect=AssertionError("AUDIT_NETWORK_FORBIDDEN")):
            report = audit_archive(args.archive, args.trace)
        _write_private(args.output, report)
    except AuditStopped as exc:
        print(json.dumps({"audit_state": "STOPPED", "reason": str(exc), "new_model_calls": 0}))
        return 2
    print(json.dumps({"audit_state": "COMPLETED", "records_observed": report["records_observed"],
                      "records_stopped": report["records_stopped"], "new_model_calls": 0}))
    return 2 if report["records_stopped"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
