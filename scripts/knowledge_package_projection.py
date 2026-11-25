"""Document-source snapshots shared by the two offline knowledge copy tools."""
from __future__ import annotations

import sqlite3

from app.services.knowledge_store import insert_document_source


def read_document_sources(connection, documents, sources) -> list[dict]:
    """A missing historical table and a damaged modern snapshot are different."""
    versioned = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_document_source'"
    ).fetchone()
    if not versioned and connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_publication_schema'"
    ).fetchone():
        raise ValueError("versioned source metadata table is missing")
    sources_by_id = {row["source_id"]: dict(row) for row in sources}
    snapshots = []
    for document in documents:
        document_id = document["document_id"]
        if versioned:
            snapshot = connection.execute(
                "SELECT * FROM knowledge_document_source WHERE document_id=?", (document_id,)
            ).fetchone()
            if snapshot is None:
                raise ValueError(f"missing versioned source metadata for {document_id}")
            snapshots.append(dict(snapshot))
        else:
            if document["source_id"] not in sources_by_id:
                raise ValueError(f"missing knowledge source for {document_id}")
            source = sources_by_id[document["source_id"]].copy()
            del source["source_id"]
            snapshots.append(dict(source, document_id=document_id, metadata_origin="legacy_observed"))
    return snapshots


def copy_document_sources(connection: sqlite3.Connection, snapshots: list[dict]) -> int:
    inserted = 0
    for snapshot in snapshots:
        document_id = snapshot["document_id"]
        old = connection.execute(
            "SELECT * FROM knowledge_document_source WHERE document_id=?", (document_id,)
        ).fetchone()
        if old is None:
            insert_document_source(connection, document_id, snapshot, metadata_origin=snapshot["metadata_origin"])
            inserted += 1
        elif dict(old) != snapshot:
            raise ValueError("existing versioned source metadata differs; refusing to overwrite")
    return inserted
