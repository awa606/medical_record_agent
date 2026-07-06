"""构建 Toyhom 感冒候选病例的 pseudo_fields 数据集。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dataset_pipeline.paths import PROCESSED_DIR
from app.dataset_pipeline.pseudo_emr import build_pseudo_emr_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="生成伪病历字段数据集")
    parser.add_argument("--input", type=Path, default=PROCESSED_DIR / "toyhom_cold_candidates.jsonl")
    parser.add_argument("--output", type=Path, default=PROCESSED_DIR / "pseudo_emr_cases.jsonl")
    args = parser.parse_args()

    count = build_pseudo_emr_dataset(args.input, args.output)
    print(f"已生成 {count} 条 pseudo EMR 样本：{args.output}")


if __name__ == "__main__":
    main()
