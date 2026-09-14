"""Dependency-free scoring shared by CI and local training experiments."""
from __future__ import annotations

import json
from typing import Any


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _fact_key(fact: Any) -> str:
    if not isinstance(fact, dict):
        return "invalid"
    selected = {key: fact.get(key) for key in ("type", "name", "assertion", "value", "unit") if fact.get(key) is not None}
    return json.dumps(selected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def score_output(case_id: str, target: dict[str, Any], generated: str) -> dict[str, Any]:
    parsed = _extract_json(generated)
    if parsed is None:
        return {
            "case_id": case_id,
            "valid_json": False,
            "schema_complete": False,
            "fact_recall": 0.0,
            "field_status_accuracy": 0.0,
            "unsupported_fact_count": 0,
        }
    facts = parsed.get("facts")
    statuses = parsed.get("field_status")
    schema_complete = isinstance(facts, list) and isinstance(statuses, dict) and set(parsed) <= {"facts", "field_status"}
    facts = facts if isinstance(facts, list) else []
    statuses = statuses if isinstance(statuses, dict) else {}
    expected_facts = {_fact_key(item) for item in target.get("facts", [])}
    actual_facts = {_fact_key(item) for item in facts}
    fact_recall = len(expected_facts & actual_facts) / len(expected_facts) if expected_facts else float(not actual_facts)
    expected_statuses = target.get("field_status", {})
    status_accuracy = (
        sum(statuses.get(key) == value for key, value in expected_statuses.items()) / len(expected_statuses)
        if expected_statuses
        else float(not statuses)
    )
    return {
        "case_id": case_id,
        "valid_json": True,
        "schema_complete": schema_complete,
        "fact_recall": round(fact_recall, 6),
        "field_status_accuracy": round(status_accuracy, 6),
        "unsupported_fact_count": len(actual_facts - expected_facts),
    }
