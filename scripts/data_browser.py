"""Export an explicit synthetic allowlist to an authenticated, immutable viewer.

No application imports: inspecting the database must never initialize/migrate it.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import socket
import sqlite3
import webbrowser


TABLES = {
    "patient": "id INTEGER PRIMARY KEY, deidentified_id TEXT UNIQUE, display_name TEXT, created_at TEXT, updated_at TEXT",
    "agent_task": "id INTEGER PRIMARY KEY, input_type TEXT, status TEXT, current_stage TEXT, created_at TEXT, updated_at TEXT, completed_at TEXT",
    "encounter": "id INTEGER PRIMARY KEY, patient_id INTEGER REFERENCES patient(id), task_id INTEGER REFERENCES agent_task(id), status TEXT, check_in_status TEXT, current_revision_id INTEGER REFERENCES record_revision(id), created_at TEXT, updated_at TEXT",
    "record_revision": "id INTEGER PRIMARY KEY, encounter_id INTEGER REFERENCES encounter(id), task_id INTEGER REFERENCES agent_task(id), revision_no INTEGER, source TEXT, content_hash TEXT, draft_text TEXT, created_at TEXT",
    "revision_field": "id TEXT PRIMARY KEY, revision_id INTEGER REFERENCES record_revision(id), field_key TEXT, value TEXT, status TEXT, missing INTEGER, doctor_review_status TEXT, evidence_json TEXT",
    "approval": "id INTEGER PRIMARY KEY, encounter_id INTEGER REFERENCES encounter(id), revision_id INTEGER REFERENCES record_revision(id), task_id INTEGER REFERENCES agent_task(id), content_hash TEXT, status TEXT, created_at TEXT, invalidated_at TEXT, invalidation_reason TEXT",
    "export_event": "id INTEGER PRIMARY KEY, encounter_id INTEGER REFERENCES encounter(id), revision_id INTEGER REFERENCES record_revision(id), approval_id INTEGER REFERENCES approval(id), task_id INTEGER REFERENCES agent_task(id), created_at TEXT",
    "knowledge_source": "source_id TEXT PRIMARY KEY, title TEXT, publisher TEXT, source_url TEXT, published_at TEXT, usage_scope TEXT, document_type TEXT, disease_scope TEXT",
    "knowledge_document": "document_id TEXT PRIMARY KEY, source_id TEXT REFERENCES knowledge_source(source_id), version TEXT, content_sha256 TEXT, retrieved_at TEXT, page_count INTEGER, extraction_method TEXT, is_current INTEGER, is_active INTEGER, effective_date TEXT, content_format TEXT",
    "knowledge_chunk": "chunk_id TEXT PRIMARY KEY, document_id TEXT REFERENCES knowledge_document(document_id), section TEXT, page INTEGER, content TEXT, content_sha256 TEXT",
    "knowledge_embedding_metadata": "chunk_id TEXT REFERENCES knowledge_chunk(chunk_id), model_id TEXT, dimensions INTEGER, created_at TEXT, PRIMARY KEY(chunk_id,model_id)",
}
FIELD_KEYS = ("chief_complaint", "present_illness", "previous_treatment", "accompanying_symptoms", "past_history", "allergy_history", "physical_exam")
SPAN_KEYS = ("text", "index", "segment_id", "start_time", "end_time")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def choose_loopback_port(ports: list[int]) -> int:
    """Probe binding, including Windows exclusions not shown as listeners."""
    if not ports or any(not 1024 <= port <= 65535 for port in ports):
        raise ValueError("viewer ports must be in 1024..65535")
    failures = []
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind(("127.0.0.1", port))
            return port
        except OSError as exc:
            failures.append(f"{port}: {getattr(exc, 'winerror', None) or exc.errno}")
    raise RuntimeError("No bindable loopback port (" + ", ".join(failures) +
                       "); choose an explicit -Port. Existing services retained.")


def _rows(connection, table):
    return [dict(r) for r in connection.execute(f'SELECT * FROM "{table}"')]


def _insert_projection(connection, table, rows):
    columns = [r[1] for r in connection.execute(f'PRAGMA table_info("{table}")')]
    marks = ",".join("?" for _ in columns)
    names = ",".join(f'"{c}"' for c in columns)
    for row in rows:
        values = [row.get(c) for c in columns]
        if any(isinstance(v, (dict, list, bytes)) for v in values):
            raise ValueError(f"unexpected non-scalar value in {table}")
        connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', values)


def _field_rows(revisions):
    rows = []
    for revision in revisions:
        fields = json.loads(revision.get("fields_json") or "{}")
        if not isinstance(fields, dict):
            raise ValueError("revision fields must be an object")
        for key in FIELD_KEYS:
            field = fields.get(key)
            if not isinstance(field, dict):
                continue
            spans = []
            for span in field.get("source_spans") or []:
                spans.append({k: span[k] for k in SPAN_KEYS if k in span and isinstance(span[k], (str, int, float, type(None)))})
            rows.append({"id": f'{revision["id"]}:{key}', "revision_id": revision["id"],
                         "field_key": key, "value": field.get("value"), "status": field.get("status"),
                         "missing": int(bool(field.get("missing"))), "doctor_review_status": field.get("doctor_review_status"),
                         "evidence_json": json.dumps(spans, ensure_ascii=False)})
    return rows


def export_snapshot(source: Path, output: Path, allowlist: Path, source_label: str):
    source = source.resolve(strict=True)
    output = output.resolve()
    policy = json.loads(allowlist.read_text(encoding="utf-8"))
    markers = policy.get("synthetic_patient_ids")
    if (policy.get("confirmed_synthetic") is not True or not policy.get("reviewed_by")
            or not isinstance(markers, list) or not markers
            or any(not isinstance(x, str) or not x for x in markers)
            or len(set(markers)) != len(markers)):
        raise ValueError("explicit reviewed synthetic allowlist required")
    if output.exists():
        raise ValueError("output already exists; refresh into a NEW directory")
    # SQLite's backup API includes committed WAL data; raw database stays in memory.
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10)) as src, closing(sqlite3.connect(":memory:")) as snapshot:
        src.backup(snapshot)
        snapshot.row_factory = sqlite3.Row
        if snapshot.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("source quick_check failed")
        patients = [r for r in _rows(snapshot, "patient") if r["deidentified_id"] in markers]
        if {r["deidentified_id"] for r in patients} != set(markers):
            raise ValueError("allowlisted patient missing; no partial snapshot published")
        pids = {r["id"] for r in patients}
        encounters = [r for r in _rows(snapshot, "encounter") if r["patient_id"] in pids]
        eids = {r["id"] for r in encounters}
        tids = {r["task_id"] for r in encounters if r["task_id"] is not None}
        revisions = [r for r in _rows(snapshot, "record_revision") if r["encounter_id"] in eids]
        rids = {r["id"] for r in revisions}
        # Reject unexpected cross-encounter links rather than exporting outside the whitelist.
        if any(r.get("task_id") is not None and r["task_id"] not in tids for r in revisions):
            raise ValueError("revision task escapes selected encounters")
        projection = {
            "patient": patients, "encounter": encounters,
            "agent_task": [r for r in _rows(snapshot, "agent_task") if r["id"] in tids],
            "record_revision": revisions, "revision_field": _field_rows(revisions),
            "approval": [r for r in _rows(snapshot, "approval") if r["encounter_id"] in eids],
            "export_event": [r for r in _rows(snapshot, "export_event") if r["encounter_id"] in eids],
            **{t: _rows(snapshot, t) for t in ("knowledge_source", "knowledge_document", "knowledge_chunk")},
            "knowledge_embedding_metadata": _rows(snapshot, "knowledge_embedding"),
        }
        if any(r["revision_id"] not in rids for t in ("approval", "export_event") for r in projection[t]):
            raise ValueError("approval/export escapes selected revisions")
        output.mkdir(parents=True)
        database = output / "mra_snapshot.sqlite3"
        with closing(sqlite3.connect(database)) as dst:
            for table, definition in TABLES.items():
                dst.execute(f'CREATE TABLE "{table}" ({definition})')
                _insert_projection(dst, table, projection[table])
            dst.commit()
            if dst.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("snapshot contains broken foreign keys")
            if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("snapshot quick_check failed")
            counts = {t: dst.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in TABLES}
            assert counts == {t: len(projection[t]) for t in TABLES}
    stamp = datetime.now(timezone.utc).isoformat()
    manifest = {"schema_version": "mra-readonly-snapshot-v1", "captured_at": stamp,
                "exporter_sha256": sha256(Path(__file__)), "viewer_version": "datasette 0.65.5",
                "source_label": source_label, "synthetic_only": True,
                "allowlist_sha256": sha256(allowlist), "database_sha256": sha256(database), "table_counts": counts,
                "projection": "column/JSON allowlist; revision_field derived; embedding vectors and authentication data omitted"}
    description = f"只读匿名数据快照 · {source_label} · 采样 {stamp}。不是实时数据库。手动刷新生成新版本；停用知识仍保留供版本检查，不表示医生检索会使用。"
    metadata = {"title": "MediListen 数据与知识查看器（只读快照）", "description": description,
                "allow": {"id": "root"}, "allow_sql": False,
                "databases": {"mra_snapshot": {"title": "匿名就诊数据与知识资料",
                    "description": description, "tables": {
                        "patient": {"label_column": "deidentified_id"},
                        "knowledge_source": {"label_column": "title"},
                        "knowledge_document": {"label_column": "version"},
                        "knowledge_chunk": {"label_column": "section"},
                        "revision_field": {"description": "从病历版本提取的字段及原文证据；这里只能查看，修改请回到医生工作台。"},
                        "knowledge_embedding_metadata": {"description": "仅展示语义向量索引（embedding）的模型、维度与片段关联；数量不等于混合检索验收通过。"},
                    }}}}
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    # Manifest is the publish marker: failures before it must not be served.
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def make_datasette(directory: Path, secret: str):
    from datasette.app import Datasette
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    database = directory / "mra_snapshot.sqlite3"
    if manifest["database_sha256"] != sha256(database):
        raise ValueError("snapshot SHA mismatch")
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    # Enforce, not just trust user-editable metadata defaults.
    metadata["allow"], metadata["allow_sql"] = {"id": "root"}, False
    tool = Path(__file__).resolve().parents[1] / "tools/data-browser"
    assets = tool / "assets"
    metadata["title"] = "MediListen 数据与知识查看器（只读快照）"
    metadata["mra_context"] = {"source_label": manifest["source_label"],
                               "captured_at": manifest["captured_at"], "counts": manifest["table_counts"]}
    metadata["extra_css_urls"] = ["/mra-tools/readability.css"]
    metadata["extra_js_urls"] = ["/mra-tools/chinese-controls.js"]
    return Datasette(immutables=[str(database)], metadata=metadata, secret=secret,
                     template_dir=str(tool / "templates"), plugins_dir=str(tool / "plugins"),
                     static_mounts=[("mra-tools", str(assets))],
                     settings={"default_allow_sql": False, "allow_download": False, "allow_csv_stream": False,
                               "default_page_size": 25, "max_returned_rows": 100, "sql_time_limit_ms": 1000})


def serve(directory: Path, port: int, run_id: str):
    import uvicorn
    ds = make_datasette(directory, secrets.token_hex(32))
    # Built-in one-use local login; never print it in ordinary console output.
    url = f"http://127.0.0.1:{port}/-/auth-token?token={ds._root_token}"
    (directory / "login.private.json").write_text(json.dumps({"url": url, "run_id": run_id}), encoding="utf-8")
    uvicorn.run(ds.app(), host="127.0.0.1", port=port, access_log=False, log_level="warning")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("snapshot")
    p.add_argument("--source-db", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--allowlist", type=Path, required=True)
    p.add_argument("--source-label", required=True)
    p = sub.add_parser("serve")
    p.add_argument("--snapshot-dir", type=Path, required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--run-id", required=True)
    p = sub.add_parser("open")
    p.add_argument("--snapshot-dir", type=Path, required=True)
    p = sub.add_parser("choose-port")
    p.add_argument("ports", type=int, nargs="+")
    args = parser.parse_args()
    if args.command == "snapshot":
        print(json.dumps(export_snapshot(args.source_db, args.output, args.allowlist, args.source_label), ensure_ascii=False))
    elif args.command == "serve":
        if not 1024 <= args.port <= 65535:
            parser.error("viewer port must be in 1024..65535")
        serve(args.snapshot_dir, args.port, args.run_id)
    elif args.command == "choose-port":
        print(choose_loopback_port(args.ports))
    else:
        login_file = args.snapshot_dir / "login.private.json"
        login = json.loads(login_file.read_text(encoding="utf-8"))
        url = login["url"].split("/-/auth-token", 1)[0] + "/" if login.get("opened") else login["url"]
        if webbrowser.open(url):
            login["opened"] = True
            login_file.write_text(json.dumps(login), encoding="utf-8")


if __name__ == "__main__":
    main()
