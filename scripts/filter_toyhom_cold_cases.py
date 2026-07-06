"""筛选 Toyhom 感冒/上呼吸道感染相关候选病例。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dataset_pipeline.filtering import filter_toyhom_cold_cases
from app.dataset_pipeline.paths import PROCESSED_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="筛选感冒相关病例")
    parser.add_argument("--input", type=Path, default=PROCESSED_DIR / "toyhom_clean.jsonl")
    parser.add_argument("--output", type=Path, default=PROCESSED_DIR / "toyhom_cold_candidates.jsonl")
    args = parser.parse_args()

    count = filter_toyhom_cold_cases(args.input, args.output)
    print(f"已筛选 {count} 条候选病例：{args.output}")


if __name__ == "__main__":
    main()
