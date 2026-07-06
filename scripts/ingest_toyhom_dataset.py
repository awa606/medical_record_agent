"""导入 Toyhom 中文医疗问答 CSV。

默认读取 data/raw_external/ 下的 CSV，输出 data/processed/toyhom_clean.jsonl。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dataset_pipeline.ingest import ingest_toyhom_dataset
from app.dataset_pipeline.paths import PROCESSED_DIR, RAW_EXTERNAL_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="导入 Toyhom 中文医疗问答 CSV")
    parser.add_argument("--raw-dir", type=Path, default=RAW_EXTERNAL_DIR)
    parser.add_argument("--output", type=Path, default=PROCESSED_DIR / "toyhom_clean.jsonl")
    args = parser.parse_args()

    count = ingest_toyhom_dataset(args.raw_dir, args.output)
    print(f"已导入 {count} 条记录：{args.output}")


if __name__ == "__main__":
    main()
