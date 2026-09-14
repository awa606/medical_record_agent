from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

from app.services.knowledge_store import KnowledgePage, build_embeddings, ingest_pages


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _page_numbers(source: dict[str, Any], page_count: int) -> list[int]:
    selected: list[int] = []
    for start, end in source.get("page_ranges", [[1, page_count]]):
        if start < 1 or end < start or end > page_count:
            raise ValueError(f"invalid page range {start}-{end} for {source['source_id']} ({page_count} pages)")
        selected.extend(range(start, end + 1))
    return sorted(set(selected))


def _section(text: str, fallback: str) -> str:
    compact = " ".join(text.split())
    match = re.search(r"(?:^|\s)((?:[一二三四五六七八九十]+、|\d+[.、])[^。；]{1,50})", compact)
    return match.group(1).strip() if match else fallback


def _ocr_page(path: Path, page_index: int) -> str:
    try:
        import pymupdf
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise RuntimeError("Scanned PDF requires PyMuPDF and rapidocr-onnxruntime") from exc
    document = pymupdf.open(path)
    try:
        pixmap = document[page_index].get_pixmap(matrix=pymupdf.Matrix(1.8, 1.8), alpha=False)
        result, _ = RapidOCR()(pixmap.tobytes("png"))
    finally:
        document.close()
    if not result:
        return ""
    ordered = sorted(result, key=lambda row: (min(point[1] for point in row[0]), min(point[0] for point in row[0])))
    return "\n".join(str(row[1]).strip() for row in ordered if str(row[1]).strip())


def _extract_pages(path: Path, source: dict[str, Any]) -> tuple[list[KnowledgePage], str, int]:
    reader = PdfReader(path)
    pages: list[KnowledgePage] = []
    methods: set[str] = set()
    for page_number in _page_numbers(source, len(reader.pages)):
        text = (reader.pages[page_number - 1].extract_text() or "").strip()
        method = "pypdf"
        if len(text) < 80:
            text = _ocr_page(path, page_number - 1).strip()
            method = "rapidocr"
        if len(text) < 80:
            raise ValueError(f"page {page_number} of {source['source_id']} has no reliable extracted text")
        methods.add(method)
        pages.append(
            KnowledgePage(
                page=page_number,
                section=_section(text, f"{source['title']} · 第{page_number}页"),
                content=text,
            )
        )
    return pages, "+".join(sorted(methods)), len(reader.pages)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest page-addressable official medical reference PDFs.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--build-embeddings", action="store_true")
    parser.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    args = parser.parse_args()

    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(args.db.resolve())
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    imported: list[dict[str, Any]] = []
    for source in manifest["sources"]:
        path = args.source_root / source["file_name"]
        actual_sha = _sha256(path)
        if actual_sha.lower() != source["expected_sha256"].lower():
            raise ValueError(f"SHA256 mismatch for {source['source_id']}: {actual_sha}")
        cache_dir = args.source_root.parent / "extracted"
        cache_path = cache_dir / f"{source['source_id']}-{actual_sha[:12]}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            pages = [KnowledgePage(**item) for item in cached["pages"]]
            method = cached["extraction_method"]
            pdf_page_count = cached["pdf_page_count"]
        else:
            pages, method, pdf_page_count = _extract_pages(path, source)
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(
                    {
                        "content_sha256": actual_sha,
                        "extraction_method": method,
                        "pdf_page_count": pdf_page_count,
                        "pages": [
                            {"page": page.page, "section": page.section, "content": page.content}
                            for page in pages
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        result = ingest_pages(
            source=source,
            document_bytes=path.read_bytes(),
            pages=pages,
            extraction_method=method,
            retrieved_at=generated_at,
            max_chunks=source.get("max_chunks"),
        )
        result.update(
            {
                "title": source["title"],
                "pdf_page_count": pdf_page_count,
                "selected_pages": [page.page for page in pages],
                "extraction_method": method,
                "acquisition_note": source.get("acquisition_note"),
            }
        )
        imported.append(result)

    embedding_result = None
    embedding_error = None
    if args.build_embeddings:
        try:
            embedding_result = build_embeddings(args.embedding_model)
        except Exception as exc:
            embedding_error = f"{type(exc).__name__}: {exc}"

    report = {
        "schema_version": "knowledge_ingest_report_v1",
        "package_id": manifest["package_id"],
        "generated_at": generated_at,
        "database": str(args.db),
        "source_count": len(imported),
        "chunk_count": sum(item["chunk_count"] for item in imported),
        "sources": imported,
        "embedding": embedding_result,
        "embedding_error": embedding_error,
        "gate": "PASS" if len(imported) == 3 and sum(item["chunk_count"] for item in imported) >= 30 else "NEEDS VALIDATION",
        "disclaimer": manifest["scope"],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "source_count": report["source_count"], "chunk_count": report["chunk_count"], "embedding": embedding_result, "embedding_error": embedding_error, "gate": report["gate"]}, ensure_ascii=False))
    return 0 if report["gate"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
