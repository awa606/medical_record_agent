def prepare_reference(root, api):
    """Seed a pristine rehearsal once. The caller owns the launch lock and an admin session."""
    import hashlib
    import json
    import os
    import sqlite3
    from contextlib import closing
    from pathlib import Path

    root = Path(root)
    fixture = (HERE / "固定素材/六条文书释义.json").read_bytes()
    file_sha = "5d470b317685af7b30653ce65285d0392c3d6cf8b76f1e48b1dc46c73c30737d"
    text_sha = "571013bb42cb3e50376b447522dc2fa77cdc4276db495b1bb467622c3060bab3"
    if hashlib.sha256(fixture).hexdigest() != file_sha:
        raise RuntimeError("本包的六条文书释义文件校验失败。")
    doc = json.loads(fixture)
    if (doc["source_id"] != "mra-review-outpatient-info-2024"
            or doc["version"] != "国卫办医政发〔2024〕16号 · 项目释义v2"
            or hashlib.sha256(doc["content"].encode("utf-8")).hexdigest() != text_sha):
        raise RuntimeError("本包文书的来源、版本或正文校验失败。")

    marker = root / "演练文书初始化.json"
    def mark(phase):
        tmp = marker.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump({"file_sha256": file_sha, "phase": phase}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(marker)

    phase = None
    if marker.exists():
        saved = json.loads(marker.read_bytes())
        phase = saved.get("phase")
        if saved.get("file_sha256") != file_sha or phase not in ("pending", "finished", "managed"):
            raise RuntimeError("文书索引初始化标记无法核对。")
        if phase != "pending":
            return phase

    directory = "/api/knowledge/admin/documents"
    documents = api("GET", directory)["documents"]
    if phase is None:
        if documents:
            mark("managed")
            return "managed"
        mark("pending")

    if not documents:
        api("POST", "/api/knowledge/admin/import", doc)
        documents = api("GET", directory)["documents"]

    # A new document or a metadata edit belongs to the administrator.
    metadata = ("source_id", "version", "title", "publisher", "source_url", "usage_scope",
                "document_type", "disease_scope", "published_at", "effective_date")
    if len(documents) != 1:
        mark("managed")
        return "managed"
    entry = documents[0]
    if entry.get("content_sha256") != text_sha or any(entry.get(k) != doc[k] for k in metadata):
        mark("managed")
        return "managed"
    document_id = entry["document_id"]
    if not (entry["is_active"] and entry["is_current"]):
        # Both a newly imported and an intentionally disabled document can be inactive.
        # The admin API records each action atomically with the document. Read only the
        # local rehearsal's target row; all state changes go through the authenticated API.
        uri = (root / "合成就诊.sqlite3").resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            events = db.execute(
                "SELECT action FROM knowledge_admin_audit WHERE document_id=? ORDER BY audit_id",
                (document_id,),
            ).fetchall()
        if events != [("knowledge_import",)]:
            mark("managed")
            return "managed"
        enabled = api("POST", directory + "/" + document_id + "/enable")
        if (enabled.get("document_id") != document_id or enabled.get("content_sha256") != text_sha
                or not (enabled.get("is_active") and enabled.get("is_current"))):
            raise RuntimeError("文书启用回执与冻结版本不一致。")
    mark("finished")
    return "finished"
