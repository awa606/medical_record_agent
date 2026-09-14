from __future__ import annotations

import json
from pathlib import Path

from scripts.prepare_semantic_lora_dataset import prepare


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_prepare_semantic_dataset_uses_fixed_30_10_20_split_and_safe_targets(tmp_path: Path) -> None:
    manifest = prepare(
        PROJECT_ROOT / "data/clinical_e2e/field_disease_pack_v1/manifest.json",
        tmp_path / "dataset",
    )

    assert {key: value["count"] for key, value in manifest["outputs"].items()} == {
        "train": 30,
        "validation": 10,
        "frozen_test": 20,
    }
    rows = [
        json.loads(line)
        for line in (tmp_path / "dataset" / "train.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["case_id"].startswith("ce2e_v1_001_")
    assert rows[-1]["case_id"].startswith("ce2e_v1_030_")
    assert all(set(row["target"]) == {"facts", "field_status"} for row in rows)
    assert all("candidate_diagnoses" not in row["target"] for row in rows)
    assert all(row["source_case_sha256"] for row in rows)
