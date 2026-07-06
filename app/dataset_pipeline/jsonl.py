"""JSONL 读写工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """写出 JSONL 文件，并返回写入条数。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            file.write("\n")
            count += 1
    return count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 文件。"""

    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
