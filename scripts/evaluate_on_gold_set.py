"""评估人工 gold set 上的字段抽取效果。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dataset_pipeline.gold_eval import evaluate_on_gold_set
from app.dataset_pipeline.paths import ANNOTATION_DIR, OUTPUT_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="评估 Toyhom gold set 字段抽取效果")
    parser.add_argument("--gold", type=Path, default=ANNOTATION_DIR / "gold_100.jsonl")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "toyhom_gold_evaluation_report.md")
    args = parser.parse_args()

    report = evaluate_on_gold_set(args.gold, args.output)
    aggregate = report["aggregate"]
    print("Toyhom gold set 评估完成：")
    print(f"- Precision: {aggregate['precision']}")
    print(f"- Recall: {aggregate['recall']}")
    print(f"- F1: {aggregate['f1']}")
    print(f"- 字段完整率: {aggregate['field_completeness']}")
    print(f"- 证据片段命中率: {aggregate['evidence_hit_rate']}")
    print(f"- 幻觉率: {aggregate['hallucination_rate']}")
    print(f"- 输出文件: {args.output}")


if __name__ == "__main__":
    main()
