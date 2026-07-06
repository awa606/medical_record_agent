"""从 Toyhom pseudo EMR 数据集中抽取人工标注样本。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dataset_pipeline.annotation import sample_annotation_set
from app.dataset_pipeline.paths import ANNOTATION_DIR, PROCESSED_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="生成人工标注样本")
    parser.add_argument("--input", type=Path, default=PROCESSED_DIR / "pseudo_emr_cases.jsonl")
    parser.add_argument("--output", type=Path, default=ANNOTATION_DIR / "annotation_sample_100.jsonl")
    parser.add_argument("--guide", type=Path, default=ANNOTATION_DIR / "annotation_guide.md")
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    count = sample_annotation_set(args.input, args.output, args.guide, args.sample_size, args.seed)
    print(f"已生成 {count} 条标注样本：{args.output}")
    print(f"标注指南：{args.guide}")


if __name__ == "__main__":
    main()
