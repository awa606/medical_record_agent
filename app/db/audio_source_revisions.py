from contextlib import closing

from app.db import sqlite as db
from app.services.audio_source_revisions import RevisionConflict


def _visit(connection, task_id, doctor_id):
    row = connection.execute(
        """
        SELECT t.encounter_id,t.current_record_revision_id,t.result_json AS task_result,
               e.doctor_user_id,e.check_in_status,e.task_id AS active_task,t.owner_user_id,
               r.id,r.revision_no,r.content_hash,r.result_json
        FROM agent_task t LEFT JOIN encounter e ON e.id=t.encounter_id
        LEFT JOIN record_revision r ON r.id=t.current_record_revision_id AND r.task_id=t.id
        WHERE t.id=?""",
        (task_id,),
    ).fetchone()
    if row is None:
        raise LookupError("任务不存在。")
    if row["owner_user_id"] != doctor_id or row["doctor_user_id"] != doctor_id:
        raise PermissionError("仅本次就诊的经治医生可审阅订正后的录音。")
    return row


def _unfinished(connection, row, task_id):
    if row["id"] is None or row["active_task"] != task_id or row["check_in_status"] != "in_progress":
        raise RevisionConflict(
            "audio_source_revision_unavailable", "仅可为本次进行中就诊的当前未签草稿创建修订。"
        )
    signed = connection.execute(
        """
        SELECT EXISTS(SELECT 1 FROM approval WHERE encounter_id=?)
            OR EXISTS(SELECT 1 FROM export_event WHERE encounter_id=?)""",
        (row["encounter_id"], row["encounter_id"]),
    ).fetchone()[0]
    if signed:
        raise RevisionConflict("audio_revision_previously_signed", "本次就诊已有批准或签件，请保留原记录。")


def source_revision_context(task_id: int, doctor_id: int) -> dict:
    with closing(db.get_connection()) as connection:
        row = _visit(connection, task_id, doctor_id)
        _unfinished(connection, row, task_id)
        return dict(row)


def _receipt(connection, task_id, doctor_id, request_id, request_hash):
    row = connection.execute(
        """
        SELECT a.request_hash,a.source_sha256,r.id,r.revision_no,r.content_hash,r.source,r.encounter_id
        FROM audio_source_revision_request a JOIN record_revision r ON r.id=a.revision_id
        WHERE a.task_id=? AND a.doctor_id=? AND a.request_id=?""",
        (task_id, doctor_id, request_id),
    ).fetchone()
    if row is None:
        return None
    if row["request_hash"] != request_hash:
        raise RevisionConflict(
            "source_revision_request_conflict", "该请求已保存其他内容，请查看已保存的修订。"
        )
    return {
        "task_id": task_id,
        "encounter_id": row["encounter_id"],
        "source_sha256": row["source_sha256"],
        "revision": {k: row[k] for k in ("id", "revision_no", "source", "content_hash")},
    }


def saved_source_revision(task_id, doctor_id, request_id, request_hash):
    with closing(db.get_connection()) as connection:
        _visit(connection, task_id, doctor_id)
        return _receipt(connection, task_id, doctor_id, request_id, request_hash)


def append_source_revision(task_id, doctor_id, request_id, request_hash, result):
    proof = result["audio_source_revision"]
    with closing(db.get_connection()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = _visit(connection, task_id, doctor_id)
        prior = _receipt(connection, task_id, doctor_id, request_id, request_hash)
        if prior:
            return prior
        _unfinished(connection, row, task_id)
        if (
            row["id"] != proof["previous_revision_id"]
            or row["content_hash"] != proof["previous_content_hash"]
        ):
            raise RevisionConflict("stale_record_revision", "病历版本已变化，请重新打开当前版本核对。")
        eid = row["encounter_id"]
        # Old writers must not create a later revision which loses the source proof.
        connection.execute(
            "UPDATE encounter SET min_writer_protocol=MAX(min_writer_protocol,4) WHERE id=?", (eid,)
        )
        rid = db._insert_record_revision_row(
            connection,
            task_id=task_id,
            encounter_id=eid,
            result=result,
            actor_user_id=doctor_id,
            source="doctor_audio_source_revision",
        )
        db._update_encounter_revision_row(
            connection, encounter_id=eid, revision_id=rid, workflow_status="waiting_review"
        )
        identity = connection.execute(
            "SELECT id,revision_no,source,content_hash FROM record_revision WHERE id=?", (rid,)
        ).fetchone()
        result["record_revision"] = dict(identity)
        connection.execute(
            "UPDATE agent_task SET input_text=? WHERE id=?", (result["conversation_text"], task_id)
        )
        db._update_task_result_revision_row(
            connection,
            task_id=task_id,
            result=result,
            status="WAITING_DOCTOR_REVIEW",
            current_stage="waiting_doctor_review",
            encounter_id=eid,
            revision_id=rid,
            expected_previous_revision_id=row["id"],
            expected_previous_content_hash=row["content_hash"],
        )
        connection.execute(
            "INSERT INTO audio_source_revision_request VALUES(?,?,?,?,?,?)",
            (task_id, doctor_id, request_id, request_hash, rid, proof["source_sha256"]),
        )
        db._insert_audit_log_row(
            connection,
            task_id=task_id,
            event_type="reviewed_audio_source_revision",
            actor_user_id=doctor_id,
            resource_type="record_revision",
            resource_id=rid,
            event_detail={
                "encounter_id": eid,
                "revision_id": rid,
                "previous_revision_id": row["id"],
                "request_id": request_id,
                "source_sha256": proof["source_sha256"],
                "previous_source_sha256": proof["previous_source_sha256"],
                "content_hash": identity["content_hash"],
                "reviewed_fields": sorted(proof["choices"]),
            },
        )
        return _receipt(connection, task_id, doctor_id, request_id, request_hash)
