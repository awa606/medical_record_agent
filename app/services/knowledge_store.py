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


SOURCE_FIELDS = ("title", "publisher", "source_url", "download_url", "published_at",
                 "usage_scope", "document_type", "disease_scope")
_SOURCE_COLUMNS = ", ".join(SOURCE_FIELDS)
_FTS_TABLES = ("knowledge_chunk_fts", "knowledge_chunk_terms_fts", "knowledge_published_terms_fts")


def knowledge_fts_available(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM pragma_module_list WHERE name = 'fts5'").fetchone() is not None


def register_knowledge_writer(conn: sqlite3.Connection) -> None:
    """Mark this connection as understanding version snapshots and the publication index."""
    try:
        conn.execute("SELECT mra_versioned_knowledge_writer()").fetchone()
    except sqlite3.OperationalError as exc:
        if "no such function" not in str(exc).lower():
            raise
        conn.create_function("mra_versioned_knowledge_writer", 0, lambda: 1, deterministic=True)


def _begin_write(conn: sqlite3.Connection) -> None:
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")


def _publication_schema_ready(conn: sqlite3.Connection, fts: bool) -> bool:
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='versioned_knowledge_admin_audit_insert' "
        "AND EXISTS(SELECT 1 FROM sqlite_master WHERE name='knowledge_publication_schema')"
    ).fetchone():
        return False
    row = conn.execute("SELECT fts_ready FROM knowledge_publication_schema WHERE singleton=1").fetchone()
    return row is not None and bool(row[0]) == fts


def init_knowledge_schema(connection: sqlite3.Connection | None = None) -> None:
    owns = connection is None
    conn = connection or get_connection()
    outer_transaction = conn.in_transaction
    try:
        register_knowledge_writer(conn)
        fts = knowledge_fts_available(conn)
        if _publication_schema_ready(conn, fts):
            return
        # Readers take no write lock once initialized. Recheck after waiting for a concurrent migration.
        _begin_write(conn)
        if not _publication_schema_ready(conn, fts):
            _migrate_knowledge_schema(conn, fts)
        if not outer_transaction:
            conn.commit()
    except Exception:
        if not outer_transaction:
            conn.rollback()
        raise
    finally:
        if owns:
            conn.close()


def _migrate_knowledge_schema(conn: sqlite3.Connection, fts: bool) -> None:
    # executescript commits an existing transaction, including a bulk import in progress.
    ddl = """
            CREATE TABLE IF NOT EXISTS knowledge_source (
                source_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                publisher TEXT NOT NULL,
                source_url TEXT NOT NULL,
                download_url TEXT,
                published_at TEXT,
                usage_scope TEXT NOT NULL,
                document_type TEXT NOT NULL DEFAULT 'clinical-reference',
                disease_scope TEXT NOT NULL DEFAULT '',
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
                effective_date TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                original_filename TEXT,
                content_format TEXT NOT NULL DEFAULT 'pdf',
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

            CREATE TABLE IF NOT EXISTS knowledge_admin_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                document_id TEXT,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES knowledge_document(document_id)
            );

            CREATE TABLE IF NOT EXISTS knowledge_document_source (
                document_id TEXT PRIMARY KEY REFERENCES knowledge_document(document_id),
                title TEXT NOT NULL, publisher TEXT NOT NULL, source_url TEXT NOT NULL,
                download_url TEXT, published_at TEXT, usage_scope TEXT NOT NULL,
                document_type TEXT NOT NULL, disease_scope TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                metadata_origin TEXT NOT NULL CHECK (metadata_origin IN ('version_import','legacy_observed'))
            );

            CREATE TABLE IF NOT EXISTS knowledge_publication_schema (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1), fts_ready INTEGER NOT NULL
            );
    """
    for statement in ddl.split(";"):
        if statement.strip():
            conn.execute(statement)
    _ensure_column(conn, "knowledge_source", "document_type", "TEXT NOT NULL DEFAULT 'clinical-reference'")
    _ensure_column(conn, "knowledge_source", "disease_scope", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "knowledge_document", "effective_date", "TEXT")
    _ensure_column(conn, "knowledge_document", "is_active", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "knowledge_document", "original_filename", "TEXT")
    _ensure_column(conn, "knowledge_document", "content_format", "TEXT NOT NULL DEFAULT 'pdf'")

    # A legacy shared source is only a migration-time observation, even on the current edition.
    conn.execute(f"""
        INSERT INTO knowledge_document_source(document_id, {_SOURCE_COLUMNS}, created_at, updated_at, metadata_origin)
        SELECT d.document_id, {", ".join("s." + field for field in SOURCE_FIELDS)},
               s.created_at, s.updated_at, 'legacy_observed'
        FROM knowledge_document d JOIN knowledge_source s ON s.source_id=d.source_id
        WHERE NOT EXISTS (SELECT 1 FROM knowledge_document_source m WHERE m.document_id=d.document_id)
    """)
    if fts:
        indexed_before = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?,?,?)", _FTS_TABLES
        )}
        before = conn.execute("SELECT fts_ready FROM knowledge_publication_schema WHERE singleton=1").fetchone()
        restored_engine = before is not None and not before[0]
        fts_ddl = """
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
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_published_terms_fts USING fts5(
                chunk_id UNINDEXED, terms, tokenize='unicode61'
            );
        """
        for statement in fts_ddl.split(";"):
            if statement.strip():
                conn.execute(statement)
        # A database may have collected new chunks while running on SQLite without FTS5.
        for table in _FTS_TABLES[:2]:
            if restored_engine or table not in indexed_before:
                conn.execute(f"DELETE FROM {table}")
                if table == "knowledge_chunk_fts":
                    conn.execute(f"INSERT INTO {table}(chunk_id,section,content) SELECT chunk_id,section,content FROM knowledge_chunk")
                else:
                    rows = conn.execute("SELECT chunk_id, section, content FROM knowledge_chunk")
                    conn.executemany(f"INSERT INTO {table}(chunk_id,terms) VALUES (?,?)", (
                        (r["chunk_id"], _search_tokens(f'{r["section"]} {r["content"]}')) for r in rows
                    ))
        conn.execute("DELETE FROM knowledge_published_terms_fts")
        conn.execute("""
            INSERT INTO knowledge_published_terms_fts(chunk_id,terms)
            SELECT t.chunk_id,t.terms FROM knowledge_chunk_terms_fts t
            JOIN knowledge_chunk c ON c.chunk_id=t.chunk_id
            JOIN knowledge_document d ON d.document_id=c.document_id
            WHERE d.is_active=1 AND d.is_current=1
        """)
    # Old binaries also UPDATE columns in place. An INSERT-only row protocol would allow
    # their enable, disable and PATCH calls to leave stale names or stale BM25 membership.
    for table in ("knowledge_source", "knowledge_document", "knowledge_chunk", "knowledge_embedding", "knowledge_admin_audit"):
        for action in ("INSERT", "UPDATE", "DELETE"):
            conn.execute(f"""
                CREATE TRIGGER IF NOT EXISTS versioned_{table}_{action.lower()} BEFORE {action} ON {table}
                BEGIN
                    SELECT CASE WHEN mra_versioned_knowledge_writer() != 1
                        THEN RAISE(ABORT, 'Use a version-aware writer for this knowledge database') END;
                END
            """)
    conn.execute("INSERT OR REPLACE INTO knowledge_publication_schema(singleton,fts_ready) VALUES (1,?)", (int(fts),))


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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


def insert_document_source(
    conn: sqlite3.Connection, document_id: str, source: dict[str, Any], *, metadata_origin: str
) -> None:
    """Insert the version's own source record inside the caller's transaction."""
    now = utc_now()
    values = {**{"document_type": "clinical-reference", "disease_scope": ""}, **source}
    conn.execute(
        f"INSERT INTO knowledge_document_source(document_id, {_SOURCE_COLUMNS}, created_at, updated_at, metadata_origin) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (document_id, *(values.get(field) for field in SOURCE_FIELDS),
         source.get("created_at", now), source.get("updated_at", now), metadata_origin),
    )


def index_knowledge_chunk(conn: sqlite3.Connection, chunk_id: str, section: str, content: str) -> None:
    """Append one canonical chunk to the two all-edition indexes, if supported."""
    if knowledge_fts_available(conn):
        conn.execute("INSERT INTO knowledge_chunk_fts(chunk_id,section,content) VALUES (?,?,?)",
                     (chunk_id, section, content))
        conn.execute("INSERT INTO knowledge_chunk_terms_fts(chunk_id,terms) VALUES (?,?)",
                     (chunk_id, _search_tokens(f"{section} {content}")))


def _publish_source_metadata(conn: sqlite3.Connection, source_id: str) -> None:
    # Keep the legacy row readable by older tools, using the active version's observed timestamp.
    current = conn.execute("""
        SELECT s.* FROM knowledge_document_source s JOIN knowledge_document d USING(document_id)
        WHERE d.source_id=? AND d.is_current=1 AND d.is_active=1
    """, (source_id,)).fetchone()
    if current is not None:
        assignments = ", ".join(f"{key}=?" for key in (*SOURCE_FIELDS, "updated_at"))
        conn.execute(f"UPDATE knowledge_source SET {assignments} WHERE source_id=?",
                     (*(current[key] for key in (*SOURCE_FIELDS, "updated_at")), source_id))


def refresh_published_knowledge(conn: sqlite3.Connection, source_id: str) -> None:
    """Replace only this source's published projection, inside the caller's write transaction."""
    _publish_source_metadata(conn, source_id)
    if not knowledge_fts_available(conn):
        return
    conn.execute("""
        DELETE FROM knowledge_published_terms_fts WHERE chunk_id IN (
            SELECT c.chunk_id FROM knowledge_chunk c JOIN knowledge_document d USING(document_id)
            WHERE d.source_id=?
        )
    """, (source_id,))
    conn.execute("""
        INSERT INTO knowledge_published_terms_fts(chunk_id,terms)
        SELECT t.chunk_id,t.terms FROM knowledge_chunk_terms_fts t
        JOIN knowledge_chunk c ON c.chunk_id=t.chunk_id
        JOIN knowledge_document d ON d.document_id=c.document_id
        WHERE d.source_id=? AND d.is_current=1 AND d.is_active=1
    """, (source_id,))


class KnowledgeIdentityConflict(ValueError):
    """These bytes already belong to a different document identity."""


def ingest_pages(
    *,
    source: dict[str, Any],
    document_bytes: bytes,
    pages: Iterable[KnowledgePage],
    extraction_method: str,
    retrieved_at: str | None = None,
    max_chunks: int | None = None,
    connection: sqlite3.Connection | None = None,
    activate: bool = True,
    commit: bool = True,
) -> dict[str, Any]:
    owns = connection is None
    conn = connection or get_connection()
    now = utc_now()
    sha = _sha256_bytes(document_bytes)
    # The API permits case and dots in source identifiers. A display/file slug cannot
    # establish that "A.B" and "a-b" are the same publisher's entry.
    submitted_id = str(source["source_id"]).strip()
    source_id = submitted_id if re.fullmatch(r"[A-Za-z0-9._-]+", submitted_id) else _safe_id(submitted_id)
    version = str(source["version"]).strip()
    document_id = f"{_safe_id(source_id)}-{_safe_id(version)}-{sha[:12]}"
    try:
        _begin_write(conn)
        init_knowledge_schema(conn)
        existing = conn.execute(
            "SELECT document_id,source_id,version,page_count,is_active,is_current "
            "FROM knowledge_document WHERE content_sha256=?", (sha,),
        ).fetchone()
        if existing is not None:
            if (existing["source_id"], existing["version"]) != (source_id, version):
                raise KnowledgeIdentityConflict("identical content already belongs to a different source or version")
            chunk_count = conn.execute(
                "SELECT COUNT(*) FROM knowledge_chunk WHERE document_id = ?", (existing["document_id"],)
            ).fetchone()[0]
            if commit:
                conn.commit()
            return {
                "source_id": source_id,
                "document_id": existing["document_id"],
                "content_sha256": sha,
                "page_count": existing["page_count"],
                "chunk_count": chunk_count,
                "is_active": bool(existing["is_active"]),
                "is_current": bool(existing["is_current"]),
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
                published_at, usage_scope, document_type, disease_scope,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO NOTHING
            """,
            (
                source_id,
                source["title"],
                source["publisher"],
                source["source_url"],
                source.get("download_url"),
                source.get("published_at"),
                source["usage_scope"],
                source.get("document_type", "clinical-reference"),
                source.get("disease_scope", ""),
                now,
                now,
            ),
        )
        current = conn.execute(
            "SELECT document_id FROM knowledge_document WHERE source_id = ? AND is_current = 1 LIMIT 1",
            (source_id,),
        ).fetchone()
        if activate:
            conn.execute("UPDATE knowledge_document SET is_current = 0 WHERE source_id = ?", (source_id,))
        is_current = 1 if activate or current is None else 0
        conn.execute(
            """
            INSERT INTO knowledge_document(
                document_id, source_id, version, content_sha256, retrieved_at,
                page_count, extraction_method, is_current, effective_date, is_active,
                original_filename, content_format, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                source_id,
                version,
                sha,
                retrieved_at or now,
                len({page.page for page in flattened}),
                extraction_method,
                is_current,
                source.get("effective_date"),
                1 if activate else 0,
                source.get("original_filename"),
                source.get("content_format", "pdf"),
                now,
            ),
        )
        insert_document_source(conn, document_id, {**source, "created_at": now, "updated_at": now},
                               metadata_origin="version_import")
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
            index_knowledge_chunk(conn, chunk_id, page.section, page.content)
        if activate:
            refresh_published_knowledge(conn, source_id)
        if commit:
            conn.commit()
        return {
            "source_id": source_id,
            "document_id": document_id,
            "content_sha256": sha,
            "page_count": len({page.page for page in flattened}),
            "chunk_count": len(flattened),
            "is_active": activate,
            "is_current": bool(is_current),
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
            WHERE d.is_current = 1 AND d.is_active = 1
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
    document_id: str | None = None,
    include_inactive: bool = False,
) -> dict[str, Any]:
    owns = connection is None
    conn = connection or get_connection()
    init_knowledge_schema(conn)
    try:
        try:
            expression = _fts_expression(query)
        except ValueError:
            expression = None
        fts = knowledge_fts_available(conn)
        # Global administrative search follows the public corpus. A named version is required
        # to include historical/draft chunks in the preview.
        history = document_id is not None and include_inactive
        if expression is not None and fts:
            table = "knowledge_chunk_terms_fts" if history else "knowledge_published_terms_fts"
            from_chunks = f"{table} JOIN knowledge_chunk c ON c.chunk_id={table}.chunk_id"
            clauses = [f"{table} MATCH ?"]
            params: list[Any] = [expression]
            rank = f"bm25({table})"
        else:
            from_chunks = "knowledge_chunk c"
            clauses = ["c.content LIKE ?"]
            params = [f"%{query.strip()}%"]
            rank = "-1.0"
        if document_id is not None:
            clauses.append("d.document_id = ?")
            params.append(document_id)
        if not history:
            clauses.extend(["d.is_current=1", "d.is_active=1"])
        params.append(max(limit * 8, 20))
        rows = conn.execute(f"""
            SELECT c.chunk_id, c.document_id, c.section, c.page, c.content, c.content_sha256,
                   d.version, d.source_id, s.title, s.publisher, s.source_url, s.metadata_origin, s.usage_scope,
                   {rank} AS bm25_score
            FROM {from_chunks}
            JOIN knowledge_document d ON d.document_id=c.document_id
            JOIN knowledge_document_source s ON s.document_id=d.document_id
            WHERE {" AND ".join(clauses)}
            ORDER BY bm25_score, c.chunk_id
            LIMIT ?
        """, params).fetchall()
        mode = "fts5_v1" if fts else "like_v1"
        if not rows:
            return {"results": [], "retrieval_mode": mode}
        lexical_values = [-float(row["bm25_score"]) for row in rows]
        lexical_max = max(lexical_values) or 1.0
        chunk_ids = [row["chunk_id"] for row in rows]
        placeholders = ",".join("?" for _ in chunk_ids)
        embeddings = {
            row["chunk_id"]: json.loads(row["vector_json"])
            for row in conn.execute(
                f"SELECT chunk_id, vector_json FROM knowledge_embedding WHERE model_id=? AND chunk_id IN ({placeholders})",
                (model_id, *chunk_ids),
            )
        }
        query_vector: list[float] | None = None
        if embeddings:
            try:
                model = _embedding_model(model_id, True)
                query_vector = [
                    float(value)
                    for value in model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
                ]
                mode = "hybrid_v1"
            except ModuleNotFoundError as exc:
                # The optional semantic-search package may be absent from an ASR
                # image. Keep FTS usable without concealing unrelated import bugs.
                if exc.name != "sentence_transformers":
                    raise
                query_vector = None
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
                    "metadata_origin": row["metadata_origin"],
                    "usage_scope": row["usage_scope"],
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
                SELECT s.*, d.source_id, d.version, d.content_sha256,
                       d.retrieved_at, d.page_count, d.extraction_method,
                       d.effective_date, d.is_active, d.original_filename, d.content_format,
                       (SELECT COUNT(*) FROM knowledge_chunk c WHERE c.document_id = d.document_id) AS chunk_count
                FROM knowledge_document_source s JOIN knowledge_document d USING(document_id)
                WHERE d.is_current=1 AND d.is_active=1
                ORDER BY d.source_id
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
        return bool(
            conn.execute(
                """
                SELECT 1
                FROM knowledge_chunk c
                JOIN knowledge_document d ON d.document_id = c.document_id
                WHERE d.is_current = 1 AND d.is_active = 1
                LIMIT 1
                """
            ).fetchone()
        )
    finally:
        if owns:
            conn.close()


def knowledge_index_configured(connection: sqlite3.Connection | None = None) -> bool:
    """Return true once the managed index has documents, even if all are disabled."""
    owns = connection is None
    conn = connection or get_connection()
    init_knowledge_schema(conn)
    try:
        return bool(conn.execute("SELECT 1 FROM knowledge_document LIMIT 1").fetchone())
    finally:
        if owns:
            conn.close()


def parse_text_document(content: str, content_format: str) -> list[KnowledgePage]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("knowledge document is empty")
    if content_format == "txt":
        return [KnowledgePage(page=1, section="正文", content=normalized)]
    if content_format != "markdown":
        raise ValueError("only UTF-8 TXT and Markdown documents are supported")

    pages: list[KnowledgePage] = []
    section = "正文"
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            pages.append(KnowledgePage(page=1, section=section, content=text))

    for line in normalized.split("\n"):
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            flush()
            section = heading.group(1).strip()
            buffer = []
        else:
            buffer.append(line)
    flush()
    if not pages:
        pages.append(KnowledgePage(page=1, section=section, content=normalized))
    return pages


def _record_admin_audit(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int,
    action: str,
    document_id: str | None,
    detail: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO knowledge_admin_audit(actor_user_id, action, document_id, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (actor_user_id, action, document_id, json.dumps(detail, ensure_ascii=False, sort_keys=True), utc_now()),
    )


def import_text_document(
    *,
    source: dict[str, Any],
    filename: str,
    content: str,
    actor_user_id: int,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    format_by_suffix = {".txt": "txt", ".md": "markdown", ".markdown": "markdown"}
    if suffix not in format_by_suffix:
        raise ValueError("only .txt, .md and .markdown files are supported")
    try:
        document_bytes = content.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("knowledge document must be valid UTF-8 text") from exc
    content_format = format_by_suffix[suffix]
    pages = parse_text_document(content, content_format)
    owns = connection is None
    conn = connection or get_connection()
    try:
        _begin_write(conn)
        init_knowledge_schema(conn)
        payload = {
            **source,
            "original_filename": Path(filename).name,
            "content_format": content_format,
        }
        result = ingest_pages(
            source=payload,
            document_bytes=document_bytes,
            pages=pages,
            extraction_method=f"browser_utf8_{content_format}_v1",
            connection=conn,
            activate=False,
            commit=False,
        )
        _record_admin_audit(
            conn,
            actor_user_id=actor_user_id,
            action="knowledge_import" if result["created"] else "knowledge_import_duplicate",
            document_id=result["document_id"],
            detail={
                "source_id": result["source_id"],
                "content_sha256": result["content_sha256"],
                "filename": Path(filename).name,
                "created": result["created"],
            },
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        if owns:
            conn.close()


def _list_knowledge_documents_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT d.*, s.title, s.publisher, s.source_url, s.download_url,
               s.published_at, s.usage_scope, s.document_type, s.disease_scope, s.metadata_origin,
               (SELECT COUNT(*) FROM knowledge_chunk c WHERE c.document_id = d.document_id) AS chunk_count,
               (SELECT COUNT(*) FROM knowledge_embedding e
                JOIN knowledge_chunk c ON c.chunk_id = e.chunk_id
                WHERE c.document_id = d.document_id) AS embedding_count
        FROM knowledge_document d
        JOIN knowledge_document_source s ON s.document_id = d.document_id
        ORDER BY d.source_id, d.created_at DESC, d.document_id
        """
    ).fetchall()
    return [{**dict(row), "is_active": bool(row["is_active"]), "is_current": bool(row["is_current"])} for row in rows]


def _get_knowledge_document_row(conn: sqlite3.Connection, document_id: str) -> dict[str, Any] | None:
    return next((row for row in _list_knowledge_documents_rows(conn) if row["document_id"] == document_id), None)


def list_knowledge_documents(connection: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    owns = connection is None
    conn = connection or get_connection()
    init_knowledge_schema(conn)
    try:
        return _list_knowledge_documents_rows(conn)
    finally:
        if owns:
            conn.close()


def get_knowledge_document(
    document_id: str,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    owns = connection is None
    conn = connection or get_connection()
    init_knowledge_schema(conn)
    try:
        return _get_knowledge_document_row(conn, document_id)
    finally:
        if owns:
            conn.close()


def update_knowledge_document_metadata(
    document_id: str,
    *,
    metadata: dict[str, Any],
    actor_user_id: int,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    source_fields = set(SOURCE_FIELDS)
    document_fields = {"effective_date", "original_filename"}
    unexpected = set(metadata) - source_fields - document_fields
    if unexpected:
        raise ValueError(f"immutable or unsupported metadata fields: {', '.join(sorted(unexpected))}")
    if any(metadata.get(field, "") is None for field in ("title", "publisher", "source_url", "usage_scope", "document_type", "disease_scope")):
        raise ValueError("required source metadata cannot be null")
    if "original_filename" in metadata and metadata["original_filename"]:
        filename = str(metadata["original_filename"])
        if Path(filename).name != filename:
            raise ValueError("original_filename must not contain a path")
    owns = connection is None
    conn = connection or get_connection()
    try:
        _begin_write(conn)
        init_knowledge_schema(conn)
        current = _get_knowledge_document_row(conn, document_id)
        if current is None:
            raise KeyError(document_id)
        source_updates = {key: value for key, value in metadata.items() if key in source_fields}
        document_updates = {key: value for key, value in metadata.items() if key in document_fields}
        if source_updates:
            assignments = ", ".join(f"{key} = ?" for key in source_updates)
            conn.execute(
                f"UPDATE knowledge_document_source SET {assignments}, updated_at=? WHERE document_id=?",
                (*source_updates.values(), utc_now(), document_id),
            )
            if current["is_active"] and current["is_current"]:
                _publish_source_metadata(conn, current["source_id"])
        if document_updates:
            assignments = ", ".join(f"{key} = ?" for key in document_updates)
            conn.execute(
                f"UPDATE knowledge_document SET {assignments} WHERE document_id = ?",
                (*document_updates.values(), document_id),
            )
        _record_admin_audit(
            conn,
            actor_user_id=actor_user_id,
            action="knowledge_metadata_updated",
            document_id=document_id,
            detail={"fields": sorted(metadata)},
        )
        updated = _get_knowledge_document_row(conn, document_id)
        if updated is None:
            raise KeyError(document_id)
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        if owns:
            conn.close()


def set_knowledge_document_active(
    document_id: str,
    *,
    active: bool,
    actor_user_id: int,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    owns = connection is None
    conn = connection or get_connection()
    try:
        _begin_write(conn)
        init_knowledge_schema(conn)
        current = _get_knowledge_document_row(conn, document_id)
        if current is None:
            raise KeyError(document_id)
        if active:
            conn.execute("UPDATE knowledge_document SET is_current = 0 WHERE source_id = ?", (current["source_id"],))
            conn.execute(
                "UPDATE knowledge_document SET is_active = 1, is_current = 1 WHERE document_id = ?",
                (document_id,),
            )
        else:
            conn.execute("UPDATE knowledge_document SET is_active = 0 WHERE document_id = ?", (document_id,))
        refresh_published_knowledge(conn, current["source_id"])
        _record_admin_audit(
            conn,
            actor_user_id=actor_user_id,
            action="knowledge_enabled" if active else "knowledge_disabled",
            document_id=document_id,
            detail={"active": active, "source_id": current["source_id"]},
        )
        updated = _get_knowledge_document_row(conn, document_id)
        if updated is None:
            raise KeyError(document_id)
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        if owns:
            conn.close()


def knowledge_health(connection: sqlite3.Connection | None = None) -> dict[str, Any]:
    owns = connection is None
    conn = connection or get_connection()
    init_knowledge_schema(conn)
    try:
        counts = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM knowledge_source) AS source_count,
                (SELECT COUNT(*) FROM knowledge_document) AS document_count,
                (SELECT COUNT(*) FROM knowledge_document WHERE is_active = 1 AND is_current = 1) AS active_document_count,
                (SELECT COUNT(*) FROM knowledge_chunk) AS chunk_count,
                (SELECT COUNT(*) FROM knowledge_embedding) AS embedding_count,
                (SELECT COUNT(*) FROM knowledge_admin_audit) AS audit_count
            """
        ).fetchone()
        return {
            **dict(counts),
            "index_available": bool(counts["active_document_count"] and counts["chunk_count"]),
            "embedding_model": DEFAULT_EMBEDDING_MODEL,
        }
    finally:
        if owns:
            conn.close()
