"""Evaluate deterministic clinical-fact extraction on a frozen JSONL set."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.clinical_facts import extract_clinical_facts


FIELDS = ("type", "concept", "assertion", "experiencer", "temporality", "certainty", "value", "unit")


def normalized_actual(fact: Any) -> dict:
    raw = asdict(fact) if is_dataclass(fact) else dict(fact)
    return {
        "type": raw.get("type"),
        "concept": raw.get("name") or raw.get("concept"),
        "assertion": raw.get("assertion", "present"),
        "experiencer": raw.get("experiencer", "unknown"),
        "temporality": raw.get("temporality", "unknown"),
        "certainty": raw.get("certainty", "unknown"),
        "value": raw.get("value"),
        "unit": raw.get("unit"),
    }


def signature(item: dict) -> tuple:
    return tuple(item.get(key) for key in FIELDS)


def evaluate(dataset: Path) -> dict:
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    category_counts: Counter[str] = Counter()
    failure_counts: Counter[str] = Counter()
    failures: list[dict] = []
    expected_facts = matched_facts = exact_cases = 0
    dangerous_polarity_flips = unsupported_facts = missing_facts = 0
    question_leakage = experiencer_errors = temporality_errors = certainty_errors = value_unit_errors = 0

    for row in rows:
        category_counts[row["category"]] += 1
        expected = row["expected"]
        actual = [normalized_actual(item) for item in extract_clinical_facts(row["text"])]
        expected_facts += len(expected)
        remaining = actual.copy()
        row_errors: list[str] = []

        for target in expected:
            exact = next((item for item in remaining if signature(item) == signature(target)), None)
            if exact is not None:
                matched_facts += 1
                remaining.remove(exact)
                continue

            same_concept = next(
                (
                    item
                    for item in remaining
                    if item["type"] == target["type"] and item["concept"] == target["concept"]
                ),
                None,
            )
            if same_concept is None:
                missing_facts += 1
                row_errors.append("missing_fact")
                continue
            remaining.remove(same_concept)
            if {same_concept["assertion"], target["assertion"]} == {"present", "absent"}:
                dangerous_polarity_flips += 1
                row_errors.append("dangerous_polarity_flip")
            if same_concept["experiencer"] != target["experiencer"]:
                experiencer_errors += 1
                row_errors.append("experiencer_error")
            if same_concept["temporality"] != target["temporality"]:
                temporality_errors += 1
                row_errors.append("temporality_error")
            if same_concept["certainty"] != target["certainty"]:
                certainty_errors += 1
                row_errors.append("certainty_error")
            if (same_concept["value"], same_concept["unit"]) != (target["value"], target["unit"]):
                value_unit_errors += 1
                row_errors.append("value_unit_error")
            if same_concept["assertion"] != target["assertion"]:
                row_errors.append("assertion_error")

        if remaining:
            unsupported_facts += len(remaining)
            row_errors.append("unsupported_fact")
        if not expected and actual:
            question_leakage += len(actual)
            row_errors.append("question_leakage")
        if not row_errors:
            exact_cases += 1
        else:
            for error in set(row_errors):
                failure_counts[error] += 1
            failures.append(
                {
                    "id": row["id"],
                    "category": row["category"],
                    "text": row["text"],
                    "expected": expected,
                    "actual": actual,
                    "errors": sorted(set(row_errors)),
                }
            )

    metrics = {
        "dataset": str(dataset),
        "case_count": len(rows),
        "expected_fact_count": expected_facts,
        "matched_fact_count": matched_facts,
        "exact_case_count": exact_cases,
        "exact_case_rate": round(exact_cases / len(rows), 6) if rows else 0.0,
        "dangerous_polarity_flips": dangerous_polarity_flips,
        "unsupported_fact_count": unsupported_facts,
        "missing_fact_count": missing_facts,
        "question_leakage_count": question_leakage,
        "experiencer_errors": experiencer_errors,
        "temporality_errors": temporality_errors,
        "certainty_errors": certainty_errors,
        "value_unit_errors": value_unit_errors,
        "category_counts": dict(sorted(category_counts.items())),
        "failure_counts": dict(sorted(failure_counts.items())),
    }
    metrics["safety_gate_pass"] = all(
        metrics[key] == 0
        for key in (
            "dangerous_polarity_flips",
            "unsupported_fact_count",
            "missing_fact_count",
            "question_leakage_count",
            "experiencer_errors",
            "temporality_errors",
            "certainty_errors",
            "value_unit_errors",
        )
    )
    return {"metrics": metrics, "failures": failures}


def markdown(report: dict) -> str:
    m = report["metrics"]
    return "\n".join(
        [
            "# Alpha 3.2 Semantic Safety Evaluation",
            "",
            "> Synthetic engineering regression set; not clinical validation evidence.",
            "",
            f"- Cases: {m['case_count']}",
            f"- Exact cases: {m['exact_case_count']} ({m['exact_case_rate']:.2%})",
            f"- Dangerous polarity flips: {m['dangerous_polarity_flips']}",
            f"- Unsupported facts: {m['unsupported_fact_count']}",
            f"- Missing facts: {m['missing_fact_count']}",
            f"- Question leakage: {m['question_leakage_count']}",
            f"- Experiencer errors: {m['experiencer_errors']}",
            f"- Temporality errors: {m['temporality_errors']}",
            f"- Certainty errors: {m['certainty_errors']}",
            f"- Value/unit errors: {m['value_unit_errors']}",
            f"- Safety gate: {'PASS' if m['safety_gate_pass'] else 'FAIL'}",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    args = parser.parse_args()
    report = evaluate(args.dataset)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    return 0 if report["metrics"]["safety_gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
