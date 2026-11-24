"""Legacy SQL and migrated histories must agree on which encounters require a new writer."""
import json
import sqlite3
from contextlib import closing

import pytest

from app.db import sqlite as store


ASSESSMENT = {"statement": "合成手录待核。", "certainty": "under_consideration"}


@pytest.fixture
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "protocol.sqlite3"))


def encounter_for_test():
    task_id = store.create_task("text", "WAITING_DOCTOR_REVIEW")
    return task_id, store.ensure_task_encounter(task_id)["id"]


def legacy_revision(conn, encounter_id, task_id, number, contents):
    return conn.execute(
        """INSERT INTO record_revision
           (encounter_id, task_id, revision_no, source, content_hash, result_json, created_at)
           VALUES (?, ?, ?, 'doctor_review', ?, ?, '2026-01-01')""",
        (encounter_id, task_id, number, f"original-hash-{task_id}-{number}", contents),
    ).lastrowid


def legacy_approve(conn, encounter_id, task_id, revision_id):
    return conn.execute(
        """INSERT INTO approval (encounter_id, task_id, revision_id, status, created_at)
           VALUES (?, ?, ?, 'active', '2026-01-01')""",
        (encounter_id, task_id, revision_id),
    ).lastrowid


def legacy_export(conn, encounter_id, task_id, revision_id, approval_id):
    return conn.execute(
        """INSERT INTO export_event (encounter_id, task_id, revision_id, approval_id, exports_json, created_at)
           VALUES (?, ?, ?, ?, '{}', '2026-01-01')""",
        (encounter_id, task_id, revision_id, approval_id),
    ).lastrowid


def watermarks(conn):
    return dict(conn.execute("SELECT id, min_writer_protocol FROM encounter"))


def history(conn):
    return list(conn.execute(
        "SELECT id, encounter_id, revision_no, content_hash, result_json FROM record_revision ORDER BY id"
    ))


def test_upgrade_scans_all_revisions_and_preserves_legacy_history(isolated_database, monkeypatch):
    # Build the pre-protocol shape through the rest of the ordinary initialization.
    with monkeypatch.context() as previous:
        previous.setattr(store, "_migrate_clinician_writer_protocol", lambda conn: None)
        first_task, protected = encounter_for_test()
        second_task, ordinary = encounter_for_test()
        with closing(store.get_connection()) as conn, conn:
            assert "min_writer_protocol" not in {row[1] for row in conn.execute("PRAGMA table_info(encounter)")}
            for table in ("record_revision", "approval", "export_event"):
                assert "writer_protocol" not in {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            legacy_revision(conn, protected, first_task, 1, json.dumps({"clinician_assessment": ASSESSMENT}))
            legacy_revision(conn, protected, first_task, 2, '{"clinician_assessment":null}')
            for i, old in enumerate((None, "", "old malformed archive", '{"clinician_assessment":null}', "{}"), 1):
                legacy_revision(conn, ordinary, second_task, i, old)
            preserved = history(conn)

    for _ in range(2):
        store.init_db()
        with closing(store.get_connection()) as conn:
            assert watermarks(conn) == {protected: 2, ordinary: 1}
            assert history(conn) == preserved
            assert {row[0] for row in conn.execute("SELECT writer_protocol FROM record_revision")} == {1}


def test_legacy_writes_remain_valid_without_assessment_and_cannot_introduce_one(isolated_database):
    task_id, encounter_id = encounter_for_test()
    with closing(store.get_connection()) as conn:
        with conn:
            revision = legacy_revision(conn, encounter_id, task_id, 1, "{}")
            approval = legacy_approve(conn, encounter_id, task_id, revision)
            legacy_export(conn, encounter_id, task_id, revision, approval)
        for table in ("record_revision", "approval", "export_event"):
            assert tuple(conn.execute(f"SELECT writer_protocol FROM {table}").fetchone()) == (1,)
        with pytest.raises(sqlite3.IntegrityError, match="compatible application"), conn:
            legacy_revision(conn, encounter_id, task_id, 2, json.dumps({"clinician_assessment": ASSESSMENT}))
        assert watermarks(conn)[encounter_id] == 1
        assert len(history(conn)) == 1


def test_supported_transactions_and_legacy_rollback_after_clear(isolated_database):
    task_id, encounter_id = encounter_for_test()
    stored = store.create_record_revision_for_task(
        task_id, {"fields": {}, "clinician_assessment": ASSESSMENT}, source="doctor_review", workflow_status="reviewed",
    )
    store.apply_review_revision_transaction(
        task_id, {"fields": {}}, expected_revision_id=stored["id"], expected_content_hash=stored["content_hash"],
        status="WAITING_DOCTOR_REVIEW", current_stage="needs_review", source="doctor_review",
        workflow_status="reviewed", event_type="review_saved", event_detail={},
    )
    approval = store.create_approval_for_task(task_id)
    revision_id = approval["revision_id"]
    store.create_export_event_for_task(
        task_id, approval_id=approval["id"], actor_user_id=None, revision_id=revision_id,
        exports={"pdf_sha256": "0" * 64},
    )
    with closing(store.get_connection()) as conn:
        assert watermarks(conn)[encounter_id] == 2
        assert "clinician_assessment" not in json.loads(
            conn.execute("SELECT result_json FROM record_revision WHERE id=?", (revision_id,)).fetchone()[0]
        )
        prior = history(conn)
        assert len(prior) == 2
        for table in ("record_revision", "approval", "export_event"):
            assert {row[0] for row in conn.execute(f"SELECT writer_protocol FROM {table}")} == {2}
        for old_insert in (
            lambda: legacy_revision(conn, encounter_id, task_id, 3, "{}"),
            lambda: legacy_approve(conn, encounter_id, task_id, revision_id),
            lambda: legacy_export(conn, encounter_id, task_id, revision_id, approval["id"]),
        ):
            with pytest.raises(sqlite3.IntegrityError, match="compatible application"), conn:
                # Legacy revision/approval may invalidate a previous signature before its INSERT.
                conn.execute("UPDATE approval SET status='invalidated' WHERE id=?", (approval["id"],))
                old_insert()
            assert history(conn) == prior
            assert [tuple(r) for r in conn.execute("SELECT id,status FROM approval")] == [(approval["id"], "active")]
            assert conn.execute("SELECT COUNT(*) FROM export_event").fetchone()[0] == 1
