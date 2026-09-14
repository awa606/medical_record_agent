from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from app.db.sqlite import get_connection


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_DISCLAIMER = "相关知识参考仅用于医生人工核验，不作为自动诊断或治疗建议。"
_HAN_OR_WORD = re.compile(r"[\u3400-\u9fff]+|[A-Za-z0-9][A-Za-z0-9_.+-]+")


@dataclass(frozen=True)
class KnowledgePage:
    page: int
    section: str
    content: str


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def init_knowledge_schema(connection: sqlite3.Connection | None = None) -> None:
    owns = connection is None
    conn = connection or get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS knowledge_source (
                source_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                publisher TEXT NOT NULL,
                source_url TEXT NOT NULL,
                download_url TEXT,
                published_at TEXT,
                usage_scope TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_document (
                document_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                version TEXT NOT NULL,
                content_sha256 TEXT NOT NULL UNIQUE,
                retrieved_at TEXT NOT NULL,
                page_count INTEGER NOT NULL,
                extraction_method TEXT NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY(source_id) REFERENCES knowledge_source(source_id)
            );

            CREATE TABLE IF NOT EXISTS knowledge_chunk (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                section TEXT NOT NULL,
                page INTEGER NOT NULL,
                content TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES knowledge_document(document_id)
            );

            CREATE TABLE IF NOT EXISTS knowledge_embedding (
                chunk_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(chunk_id, model_id),
                FOREIGN KEY(chunk_id) REFERENCES knowledge_chunk(chunk_id)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunk_fts USING fts5(
                chunk_id UNINDEXED,
                section,
                content,
                tokenize='trigram'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunk_terms_fts USING fts5(
                chunk_id UNINDEXED,
                terms,
                tokenize='unicode61'
            );
            """
        )
        conn.commit()
    finally:
        if owns:
            conn.close()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    if not normalized:
        normalized = "u-" + hashlib.sha256(value.strip().encode("utf-8")).hexdigest()[:12]
    return normalized


def _split_page(page: KnowledgePage, max_chars: int = 1800, overlap: int = 120) -> list[KnowledgePage]:
    content = re.sub(r"[ \t]+", " ", page.content).strip()
    if not content:
        return []
    if len(content) <= max_chars:
        return [KnowledgePage(page=page.page, section=page.section, content=content)]
    chunks: list[KnowledgePage] = []
    cursor = 0
    while cursor < len(content):
        end = min(len(content), cursor + max_chars)
        if end < len(content):
            split_at = max(content.rfind("。", cursor, end), content.rfind("；", cursor, end), content.rfind("\n", cursor, end))
            if split_at > cursor + max_chars // 2:
                end = split_at + 1
        chunks.append(KnowledgePage(page=page.page, section=page.section, content=content[cursor:end].strip()))
        if end >= len(content):
            break
        cursor = max(cursor + 1, end - overlap)
    return chunks


def _search_tokens(text: str) -> str:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in _HAN_OR_WORD.finditer(text):
        value = match.group(0).lower()
        candidates = [value]
        if re.fullmatch(r"[\u3400-\u9fff]+", value):
            candidates.extend(value[index : index + 2] for index in range(max(0, len(value) - 1)))
            candidates.extend(value[index : index + 3] for index in range(max(0, len(value) - 2)))
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                tokens.append(candidate)
    return " ".join(tokens)


def ingest_pages(
    *,
    source: dict[str, Any],
    document_bytes: bytes,
    pages: Iterable[KnowledgePage],
    extraction_method: str,
    retrieved_at: str | None = None,
    max_chunks: int | None = None,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    owns = connection is None
    conn = connection or get_connection()
    init_knowledge_schema(conn)
    now = utc_now()
    sha = _sha256_bytes(document_bytes)
    source_id = _safe_id(str(source["source_id"]))
    version = str(source["version"]).strip()
    document_id = f"{source_id}-{_safe_id(version)}-{sha[:12]}"
    try:
        existing = conn.execute(
            "SELECT document_id, page_count FROM knowledge_document WHERE content_sha256 = ?",
            (sha,),
        ).fetchone()
        if existing is not None:
            chunk_count = conn.execute(
                "SELECT COUNT(*) FROM knowledge_chunk WHERE document_id = ?", (existing["document_id"],)
            ).fetchone()[0]
            return {
                "source_id": source_id,
                "document_id": existing["document_id"],
                "content_sha256": sha,
                "page_count": existing["page_count"],
                "chunk_count": chunk_count,
                "created": False,
            }

        flattened: list[KnowledgePage] = []
        for page in pages:
            flattened.extend(_split_page(page))
        if max_chunks is not None:
            flattened = flattened[:max_chunks]
        if not flattened:
            raise ValueError("document produced no page-addressable text chunks")

        conn.execute(
            """
            INSERT INTO knowledge_source(
                source_id, title, publisher, source_url, download_url,
                published_at, usage_scope, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                title=excluded.title,
                publisher=excluded.publisher,
                source_url=excluded.source_url,
                download_url=excluded.download_url,
                published_at=excluded.published_at,
                usage_scope=excluded.usage_scope,
                updated_at=excluded.updated_at
            """,
            (
                source_id,
                source["title"],
                source["publisher"],
                source["source_url"],
                source.get("download_url"),
                source.get("published_at"),
                source["usage_scope"],
                now,
                now,
            ),
        )
        conn.execute("UPDATE knowledge_document SET is_current = 0 WHERE source_id = ?", (source_id,))
        conn.execute(
            """
            INSERT INTO knowledge_document(
                document_id, source_id, version, content_sha256, retrieved_at,
                page_count, extraction_method, is_current, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                document_id,
                source_id,
                version,
                sha,
                retrieved_at or now,
                len({page.page for page in flattened}),
                extraction_method,
                now,
            ),
        )
        for index, page in enumerate(flattened, start=1):
            chunk_sha = _sha256_bytes(page.content.encode("utf-8"))
            chunk_id = f"{document_id}-p{page.page:03d}-c{index:03d}"
            conn.execute(
                """
                INSERT INTO knowledge_chunk(chunk_id, document_id, section, page, content, content_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, document_id, page.section, page.page, page.content, chunk_sha, now),
            )
            conn.execute(
                "INSERT INTO knowledge_chunk_fts(chunk_id, section, content) VALUES (?, ?, ?)",
                (chunk_id, page.section, page.content),
            )
            conn.execute(
                "INSERT INTO knowledge_chunk_terms_fts(chunk_id, terms) VALUES (?, ?)",
                (chunk_id, _search_tokens(f"{page.section} {page.content}")),
            )
        conn.commit()
        return {
            "source_id": source_id,
            "document_id": document_id,
            "content_sha256": sha,
            "page_count": len({page.page for page in flattened}),
            "chunk_count": len(flattened),
            "created": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        if owns:
            conn.close()


def _fts_expression(query: str) -> str:
    grams: list[str] = []
    seen: set[str] = set()
    for match in _HAN_OR_WORD.finditer(query):
        value = match.group(0).lower()
        candidates = [value]
        if re.fullmatch(r"[\u3400-\u9fff]+", value):
            candidates = []
            candidates.extend(value[index : index + 2] for index in range(max(0, len(value) - 1)))
            candidates.extend(value[index : index + 3] for index in range(max(0, len(value) - 2)))
        for gram in candidates:
            if gram and gram not in seen:
                seen.add(gram)
                grams.append('"' + gram.replace('"', '""') + '"')
            if len(grams) >= 32:
                break
        if len(grams) >= 32:
            break
    if not grams:
        raise ValueError("knowledge query has no searchable terms")
    return " OR ".join(grams)


def _base_chunk_query() -> str:
    return """
        SELECT c.chunk_id, c.document_id, c.section, c.page, c.content,
               c.content_sha256, d.version, s.source_id, s.title, s.publisher,
               s.source_url, bm25(knowledge_chunk_terms_fts) AS bm25_score
        FROM knowledge_chunk_terms_fts
        JOIN knowledge_chunk c ON c.chunk_id = knowledge_chunk_terms_fts.chunk_id
        JOIN knowledge_document d ON d.document_id = c.document_id
        JOIN knowledge_source s ON s.source_id = d.source_id
        WHERE knowledge_chunk_terms_fts MATCH ? AND d.is_current = 1
        ORDER BY bm25_score ASC
        LIMIT ?
    """


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


@lru_cache(maxsize=4)
def _embedding_model(model_id: str, local_files_only: bool = True):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_id, local_files_only=local_files_only)


def build_embeddings(
    model_id: str = DEFAULT_EMBEDDING_MODEL,
    connection: sqlite3.Connection | None = None,
    *,
    allow_model_download: bool = False,
) -> dict[str, Any]:
    owns = connection is None
    conn = connection or get_connection()
    init_knowledge_schema(conn)
    try:
        rows = conn.execute(
            """
            SELECT c.chunk_id, c.content
            FROM knowledge_chunk c
            JOIN knowledge_document d ON d.document_id = c.document_id
            WHERE d.is_current = 1
            ORDER BY c.chunk_id
            """
        ).fetchall()
        if not rows:
            raise ValueError("knowledge index has no chunks")
        model = _embedding_model(model_id, not allow_model_download)
        vectors = model.encode([row["content"] for row in rows], normalize_embeddings=True, show_progress_bar=False)
        now = utc_now()
        for row, vector in zip(rows, vectors):
            payload = [float(value) for value in vector]
            conn.execute(
                """
                INSERT INTO knowledge_embedding(chunk_id, model_id, dimensions, vector_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id, model_id) DO UPDATE SET
                    dimensions=excluded.dimensions,
                    vector_json=excluded.vector_json,
                    created_at=excluded.created_at
                """,
                (row["chunk_id"], model_id, len(payload), json.dumps(payload, separators=(",", ":")), now),
            )
        conn.commit()
        return {"model_id": model_id, "chunk_count": len(rows), "dimensions": len(vectors[0])}
    finally:
        if owns:
            conn.close()


def retrieve_knowledge(
    query: str,
    *,
    limit: int = 5,
    model_id: str = DEFAULT_EMBEDDING_MODEL,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    owns = connection is None
    conn = connection or get_connection()
    init_knowledge_schema(conn)
    try:
        try:
            expression = _fts_expression(query)
        except ValueError:
            expression = None
        if expression is not None:
            rows = conn.execute(_base_chunk_query(), (expression, max(limit * 8, 20))).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT c.chunk_id, c.document_id, c.section, c.page, c.content,
                       c.content_sha256, d.version, s.source_id, s.title, s.publisher,
                       s.source_url, -1.0 AS bm25_score
                FROM knowledge_chunk c
                JOIN knowledge_document d ON d.document_id = c.document_id
                JOIN knowledge_source s ON s.source_id = d.source_id
                WHERE c.content LIKE ? AND d.is_current = 1
                ORDER BY c.chunk_id
                LIMIT ?
                """,
                (f"%{query.strip()}%", max(limit * 8, 20)),
            ).fetchall()
        if not rows:
            return {"results": [], "retrieval_mode": "fts5_v1"}
        lexical_values = [-float(row["bm25_score"]) for row in rows]
        lexical_max = max(lexical_values) or 1.0
        embeddings = {
            row["chunk_id"]: json.loads(row["vector_json"])
            for row in conn.execute(
                "SELECT chunk_id, vector_json FROM knowledge_embedding WHERE model_id = ?",
                (model_id,),
            ).fetchall()
        }
        query_vector: list[float] | None = None
        mode = "fts5_v1"
        if embeddings:
            try:
                model = _embedding_model(model_id, True)
                query_vector = [
                    float(value)
                    for value in model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
                ]
                mode = "hybrid_v1"
            except (OSError, RuntimeError, ValueError):
                # The lexical index remains usable when a copied database does not
                # have the embedding model in the local offline cache.
                query_vector = None
        results: list[dict[str, Any]] = []
        for row, lexical_raw in zip(rows, lexical_values):
            lexical_score = lexical_raw / lexical_max
            dense_score = None
            if query_vector is not None and row["chunk_id"] in embeddings:
                dense_score = max(0.0, _cosine(query_vector, embeddings[row["chunk_id"]]))
            score = lexical_score if dense_score is None else 0.45 * lexical_score + 0.55 * dense_score
            results.append(
                {
                    "source_id": row["source_id"],
                    "title": row["title"],
                    "document_id": row["document_id"],
                    "chunk_id": row["chunk_id"],
                    "publisher": row["publisher"],
                    "version": row["version"],
                    "section": row["section"],
                    "page": row["page"],
                    "source_url": row["source_url"],
                    "content_sha256": row["content_sha256"],
                    "excerpt": row["content"],
                    "lexical_score": round(lexical_score, 6),
                    "dense_score": round(dense_score, 6) if dense_score is not None else None,
                    "score": round(score, 6),
                    "retrieval_mode": mode,
                }
            )
        results.sort(key=lambda item: (-item["score"], item["chunk_id"]))
        return {"results": results[:limit], "retrieval_mode": mode}
    finally:
        if owns:
            conn.close()


def list_knowledge_sources(connection: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    owns = connection is None
    conn = connection or get_connection()
    init_knowledge_schema(conn)
    try:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT s.*, d.document_id, d.version, d.content_sha256,
                       d.retrieved_at, d.page_count, d.extraction_method,
                       (SELECT COUNT(*) FROM knowledge_chunk c WHERE c.document_id = d.document_id) AS chunk_count
                FROM knowledge_source s
                JOIN knowledge_document d ON d.source_id = s.source_id AND d.is_current = 1
                ORDER BY s.source_id
                """
            ).fetchall()
        ]
    finally:
        if owns:
            conn.close()


def get_knowledge_source(source_id: str, connection: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    return next((source for source in list_knowledge_sources(connection) if source["source_id"] == source_id), None)


def knowledge_index_available(connection: sqlite3.Connection | None = None) -> bool:
    owns = connection is None
    conn = connection or get_connection()
    init_knowledge_schema(conn)
    try:
        return bool(conn.execute("SELECT 1 FROM knowledge_chunk LIMIT 1").fetchone())
    finally:
        if owns:
            conn.close()
