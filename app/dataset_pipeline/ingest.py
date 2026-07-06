"""Toyhom CSV 清洗导入。

Toyhom/Chinese-medical-dialogue-data 的 CSV 通常是 GB18030 编码，字段为
department、title、ask、answer。这里统一转换为项目内部字段：
source、department、title、question、answer，并生成稳定 case_id。
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any, Iterable

from app.dataset_pipeline.jsonl import write_jsonl
from app.dataset_pipeline.paths import PROCESSED_DIR, RAW_EXTERNAL_DIR, ensure_pipeline_dirs


CSV_ENCODINGS = ("gb18030", "utf-8-sig", "utf-8")


def stable_case_id(source: str, department: str, title: str, question: str) -> str:
    """根据关键文本生成稳定编号，重复运行不会变化。"""

    raw = "\u241f".join([source, department, title, question])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"toyhom_{digest}"


def _open_csv_with_fallback(path: Path):
    """按常见编码依次尝试打开 CSV。"""

    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            file = path.open("r", encoding=encoding, errors="strict", newline="")
            sample = file.read(2048)
            file.seek(0)
            sample.encode("utf-8")
            return file
        except UnicodeDecodeError as exc:
            last_error = exc
            try:
                file.close()
            except Exception:
                pass
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"无法识别 CSV 编码：{path}") from last_error


def iter_toyhom_csv_records(raw_dir: Path = RAW_EXTERNAL_DIR) -> Iterable[dict[str, Any]]:
    """遍历 data/raw_external/ 下所有 Toyhom CSV，输出标准字段记录。"""

    for csv_path in sorted(raw_dir.rglob("*.csv")):
        with _open_csv_with_fallback(csv_path) as file:
            reader = csv.DictReader(file)
            for row_index, row in enumerate(reader, start=1):
                department = (row.get("department") or "").strip()
                title = (row.get("title") or "").strip()
                question = (row.get("question") or row.get("ask") or "").strip()
                answer = (row.get("answer") or "").strip()
                if not any([department, title, question, answer]):
                    continue

                source = csv_path.relative_to(raw_dir).as_posix()
                yield {
                    "case_id": stable_case_id(source, department, title, question),
                    "source": source,
                    "source_row": row_index,
                    "department": department,
                    "title": title,
                    "question": question,
                    "answer": answer,
                }


def ingest_toyhom_dataset(
    raw_dir: Path = RAW_EXTERNAL_DIR,
    output_path: Path = PROCESSED_DIR / "toyhom_clean.jsonl",
) -> int:
    """读取原始 Toyhom CSV 并写出清洗后的 JSONL。"""

    ensure_pipeline_dirs()
    return write_jsonl(output_path, iter_toyhom_csv_records(raw_dir))
