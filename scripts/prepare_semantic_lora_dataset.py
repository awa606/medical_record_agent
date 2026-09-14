"""Prepare the synthetic 60-case field extraction dataset for a LoRA smoke.

Generated JSONL stays in .artifacts. The committed manifest contains paths,
hashes, IDs and split facts without duplicating the source case content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PROMPT = (
    "你是病历事实整理器。只抽取输入中明确出现的事实，不诊断、不补充治疗建议。"
    "输出严格JSON，顶层只包含facts和field_status。"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case_number(case_id: str) -> int:
    match = re.search(r"ce2e_v1_(\d{3})_", case_id)
    if match is None:
        raise ValueError(f"unsupported case id: {case_id}")
    return int(match.group(1))


def _split(case_id: str) -> str:
    number = _case_number(case_id)
    if 1 <= number <= 30:
        return "train"
    if 31 <= number <= 40:
        return "validation"
    if 41 <= number <= 60:
        return "frozen_test"
    raise ValueError(f"case id outside 1-60: {case_id}")


def build_example(case: dict[str, Any]) -> dict[str, Any]:
    dialogue = "\n".join(f"{segment['role']}：{segment['text']}" for segment in case["segments"])
    expected = case["expected"]
    target = {
        "facts": expected.get("facts", []),
        "field_status": expected.get("field_status", {}),
    }
    return {
        "case_id": case["case_id"],
        "split": _split(case["case_id"]),
        "system": SYSTEM_PROMPT,
        "input": dialogue,
        "target": target,
        "source_case_sha256": None,
    }


def prepare(source_manifest: Path, output_dir: Path) -> dict[str, Any]:
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    source_root = source_manifest.parent
    by_split: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "frozen_test": []}
    source_hashes: list[dict[str, str]] = []
    for item in source["cases"]:
        case_path = source_root / item["case_path"]
        case = json.loads(case_path.read_text(encoding="utf-8"))
        example = build_example(case)
        example["source_case_sha256"] = _sha256(case_path)
        by_split[example["split"]].append(example)
        source_hashes.append(
            {
                "case_id": case["case_id"],
                "split": example["split"],
                "source_path": case_path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": example["source_case_sha256"],
            }
        )
    for rows in by_split.values():
        rows.sort(key=lambda row: _case_number(row["case_id"]))
    counts = {name: len(rows) for name, rows in by_split.items()}
    if counts != {"train": 30, "validation": 10, "frozen_test": 20}:
        raise ValueError(f"unexpected split counts: {counts}")

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, dict[str, Any]] = {}
    for split, rows in by_split.items():
        path = output_dir / f"{split}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        outputs[split] = {"path": path.name, "count": len(rows), "sha256": _sha256(path)}
    return {
        "schema_version": "semantic_lora_dataset_manifest_v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source_dataset": source["dataset_version"],
        "source_manifest_sha256": _sha256(source_manifest),
        "privacy": source["privacy"],
        "split_policy": "case 001-030 train; 031-040 validation; 041-060 frozen_test",
        "target_scope": "transcript_to_supported_facts_and_field_status_only",
        "excluded_targets": ["diagnosis", "treatment", "candidate_diagnoses", "risk_signals"],
        "outputs": outputs,
        "source_cases": source_hashes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the local semantic LoRA smoke dataset.")
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=PROJECT_ROOT / "data/clinical_e2e/field_disease_pack_v1/manifest.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare(args.source_manifest, args.output_dir)
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "outputs": manifest["outputs"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
