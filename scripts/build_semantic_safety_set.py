"""Build the deterministic, synthetic Alpha 3.2 semantic safety set.

The fixtures contain no patient data and are not clinical validation evidence.
They exercise assertion, experiencer, temporality, questions, and numeric units.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ALLERGIES = [
    "花生过敏", "青霉素过敏", "头孢过敏", "磺胺类过敏", "阿司匹林过敏",
    "海鲜过敏", "鸡蛋过敏", "牛奶过敏", "芒果过敏", "酒精过敏",
    "碘造影剂过敏", "乳胶过敏", "尘螨过敏", "花粉过敏", "猫毛过敏",
    "大豆过敏", "小麦过敏", "芝麻过敏", "核桃过敏", "鱼类过敏",
]

SYMPTOMS = [
    "发热", "咳嗽", "胸痛", "胸闷", "气促",
    "呼吸困难", "咽痛", "咳痰", "寒战", "乏力",
]

TEMPERATURES = ["36.5", "36.8", "37.0", "37.2", "37.3", "37.8", "38.0", "38.2", "39.0", "40.0"]


def expected_fact(
    fact_type: str,
    concept: str,
    assertion: str,
    *,
    experiencer: str = "patient",
    temporality: str = "current",
    certainty: str = "confirmed",
    value: str | None = None,
    unit: str | None = None,
) -> dict:
    return {
        "type": fact_type,
        "concept": concept,
        "assertion": assertion,
        "experiencer": experiencer,
        "temporality": temporality,
        "certainty": certainty,
        "value": value,
        "unit": unit,
    }


def cases() -> list[dict]:
    rows: list[dict] = []

    def add(category: str, text: str, expected: list[dict]) -> None:
        rows.append(
            {
                "id": f"sem-v1-{len(rows) + 1:03d}",
                "category": category,
                "text": text,
                "expected": expected,
            }
        )

    for concept in ALLERGIES:
        add("allergy_present", f"患者说我有{concept}。", [expected_fact("allergy", concept, "present")])
        add("allergy_absent", f"患者说我没有{concept}。", [expected_fact("allergy", concept, "absent")])
        add(
            "allergy_uncertain",
            f"患者说我不确定是不是{concept}。",
            [expected_fact("allergy", concept, "uncertain", certainty="uncertain")],
        )
        add(
            "allergy_resolved",
            f"患者说我以前有{concept}，现在已经脱敏了。",
            [expected_fact("allergy", concept, "resolved", temporality="resolved")],
        )
        add(
            "allergy_family",
            f"患者说我父亲有{concept}。",
            [expected_fact("allergy", concept, "present", experiencer="family")],
        )
        add("allergy_question", f"医生问患者有没有{concept}？", [])
        add(
            "allergy_double_negative",
            f"患者说不是没有{concept}，我是确实会过敏。",
            [expected_fact("allergy", concept, "present")],
        )
        add(
            "allergy_question_answer_absent",
            f"医生问是否{concept}，患者回答没有。",
            [expected_fact("allergy", concept, "absent")],
        )

    for concept in SYMPTOMS:
        add("symptom_present", f"患者说我有{concept}。", [expected_fact("symptom", concept, "present")])
        add("symptom_absent", f"患者说我没有{concept}。", [expected_fact("symptom", concept, "absent")])
        add(
            "symptom_uncertain",
            f"患者说我不确定是不是{concept}。",
            [expected_fact("symptom", concept, "uncertain", certainty="uncertain")],
        )
        add(
            "symptom_resolved",
            f"患者说我昨天有{concept}，现在已经好了。",
            [expected_fact("symptom", concept, "resolved", temporality="resolved")],
        )
        add(
            "symptom_family",
            f"患者说我母亲有{concept}。",
            [expected_fact("symptom", concept, "present", experiencer="family")],
        )
        add("symptom_question", f"医生问患者有没有{concept}？", [])

    for value in TEMPERATURES:
        expected = [
            expected_fact("measurement", "体温", "present", value=f"{value.rstrip('0').rstrip('.')}℃", unit="℃")
        ]
        if float(value) >= 37.3:
            expected.append(expected_fact("symptom", "发热", "present"))
        add("temperature_value", f"患者说体温{value}℃。", expected)
        add("temperature_question", f"医生问体温是不是{value}℃？", [])

    if len(rows) != 240:
        raise AssertionError(f"expected 240 cases, got {len(rows)}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/semantic_safety/clinical_assertion_v1.jsonl"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in cases()) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cases": 240}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
