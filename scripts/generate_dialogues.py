"""根据知识库生成模拟医患对话测试集。

运行：
    python scripts/generate_dialogues.py

输出：
    data/output/generated_dialogues.json
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data_builder.dialogue_generator import generate_dialogues
from app.data_builder.paths import OUTPUT_DIR


def main() -> None:
    cases = generate_dialogues()
    print(f"已生成 {len(cases)} 条模拟医患对话。")
    print(f"输出文件：{OUTPUT_DIR / 'generated_dialogues.json'}")


if __name__ == "__main__":
    main()
