import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import socket
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from scripts.data_browser import TABLES, choose_loopback_port, export_snapshot, make_datasette


class PortTests(unittest.TestCase):
    def test_windows_reserved_port_can_fall_back_without_stopping_anything(self):
        with patch("scripts.data_browser.socket.socket") as factory:
            probe = factory.return_value.__enter__.return_value
            probe.bind.side_effect = [PermissionError(13, "reserved"), None]
            self.assertEqual(choose_loopback_port([8796, 18896]), 18896)
            self.assertEqual(probe.bind.call_args.args, (("127.0.0.1", 18896),))

    def test_occupied_port_is_rejected_and_listener_remains_alive(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            with self.assertRaises(RuntimeError):
                choose_loopback_port([port])
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass

    def test_invalid_ports_cannot_select_privileged_or_random_binding(self):
        for ports in ([], [0], [80], [65536]):
            with self.assertRaises(ValueError):
                choose_loopback_port(ports)


@contextmanager
def database(path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.sqlite3"
        self.policy = self.root / "allow.json"
        self.policy.write_text(json.dumps({"confirmed_synthetic": True, "reviewed_by": "test", "synthetic_patient_ids": ["SIM-APPROVED"]}))
        with database(self.source) as c:
            for table, ddl in TABLES.items():
                if table in ("revision_field", "knowledge_embedding_metadata"):
                    continue
                c.execute(f'CREATE TABLE "{table}" ({ddl})')
            c.executescript("""
                ALTER TABLE patient ADD COLUMN secret_note TEXT;
                ALTER TABLE record_revision ADD COLUMN fields_json TEXT;
                CREATE TABLE knowledge_embedding(chunk_id TEXT,model_id TEXT,dimensions INTEGER,vector_json TEXT,created_at TEXT);
                CREATE TABLE auth_user(password_hash TEXT);
                CREATE TABLE auth_session(token_hash TEXT);
                INSERT INTO auth_user VALUES ('DO_NOT_EXPORT_PASSWORD');
                INSERT INTO auth_session VALUES ('DO_NOT_EXPORT_TOKEN');
                INSERT INTO patient(id,deidentified_id,display_name,secret_note) VALUES(1,'SIM-APPROVED','合成患者','DO_NOT_EXPORT_SECRET');
                INSERT INTO patient(id,deidentified_id,display_name) VALUES(2,'SIM-NOT-APPROVED','DO_NOT_EXPORT_OTHER_PATIENT');
                INSERT INTO agent_task(id,status) VALUES(1,'DONE');
                INSERT INTO encounter(id,patient_id,task_id,current_revision_id) VALUES(1,1,1,1);
                INSERT INTO record_revision(id,encounter_id,task_id,revision_no,draft_text) VALUES(1,1,1,1,'匿名发热病例');
                INSERT INTO approval(id,encounter_id,task_id,revision_id,status) VALUES(1,1,1,1,'approved');
                INSERT INTO export_event(id,encounter_id,task_id,revision_id,approval_id) VALUES(1,1,1,1,1);
                INSERT INTO knowledge_source(source_id,title) VALUES('source','官方指南');
                INSERT INTO knowledge_document(document_id,source_id,version,is_active) VALUES('doc','source','v1',0);
                INSERT INTO knowledge_chunk(chunk_id,document_id,section,page,content) VALUES('chunk','doc','章节',1,'完整片段正文');
                INSERT INTO knowledge_embedding VALUES('chunk','bge',384,'DO_NOT_EXPORT_VECTOR','2026-09-28');
            """)
            c.execute("UPDATE record_revision SET fields_json=?", (json.dumps({
                "chief_complaint": {"value": "发热", "status": "supported", "source_spans": [{"text": "发热", "index": 0, "secret": "DO_NOT_EXPORT_JSON"}], "extra": "DO_NOT_EXPORT_JSON"},
                "unknown": {"value": "DO_NOT_EXPORT_JSON"},
            }, ensure_ascii=False),))

    def export(self, name="out"):
        return export_snapshot(self.source, self.root / name, self.policy, "test anonymous source")

    def test_projection_preserves_relations_without_secrets_or_source_mutation(self):
        before = self.source.read_bytes()
        manifest = self.export()
        self.assertEqual(before, self.source.read_bytes())
        db = self.root / "out/mra_snapshot.sqlite3"
        self.assertEqual(manifest["database_sha256"], hashlib.sha256(db.read_bytes()).hexdigest())
        self.assertNotIn(b"DO_NOT_EXPORT", db.read_bytes())
        with database(db) as c:
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(c.execute("select count(*) from patient").fetchone()[0], 1)
            self.assertEqual(c.execute("select value from revision_field").fetchone()[0], "发热")
            self.assertEqual(c.execute("select is_active from knowledge_document").fetchone()[0], 0)
            self.assertEqual({r[0] for r in c.execute("select name from sqlite_master where type='table'")}, set(TABLES))

    def test_allowlist_required_and_unknown_id_rejected(self):
        self.policy.write_text(json.dumps({"confirmed_synthetic": False, "synthetic_patient_ids": ["SIM-APPROVED"]}))
        with self.assertRaises(ValueError): self.export()
        self.policy.write_text(json.dumps({"confirmed_synthetic": True, "reviewed_by": "test", "synthetic_patient_ids": ["UNKNOWN"]}))
        with self.assertRaises(ValueError): self.export()
        self.assertFalse((self.root / "out").exists())

    def test_refresh_keeps_old_snapshot(self):
        self.export()
        original = (self.root / "out/mra_snapshot.sqlite3").read_bytes()
        with self.assertRaises(ValueError): self.export()
        with database(self.source) as c:
            c.execute("update record_revision set draft_text='更新后的匿名草稿'")
        self.export("refresh")
        self.assertEqual(original, (self.root / "out/mra_snapshot.sqlite3").read_bytes())
        self.assertNotEqual(original, (self.root / "refresh/mra_snapshot.sqlite3").read_bytes())

    def test_dangling_link_cannot_publish(self):
        with database(self.source) as c:
            c.execute("update encounter set current_revision_id=999")
        with self.assertRaises(ValueError): self.export()
        self.assertFalse((self.root / "out/manifest.json").exists())

    def test_committed_wal_is_in_snapshot(self):
        with database(self.source) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("update record_revision set draft_text='WAL中的已提交文本'")
            c.commit()
            self.export()
            with database(self.root / "out/mra_snapshot.sqlite3") as output:
                self.assertEqual(output.execute("select draft_text from record_revision").fetchone()[0], "WAL中的已提交文本")


@unittest.skipUnless(importlib.util.find_spec("datasette"), "isolated Datasette tool dependency")
class ViewerTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_readonly_and_foreign_key_navigation(self):
        seed = SnapshotTests()
        seed.setUp()
        self.addCleanup(seed.doCleanups)
        seed.export()
        directory = seed.root / "out"
        ds = make_datasette(directory, "test-only-secret")
        cookie = ds.sign({"a": {"id": "root"}}, "actor")
        headers = {"cookie": "ds_actor=" + cookie}
        before = (directory / "mra_snapshot.sqlite3").read_bytes()
        for path in ("/", "/mra_snapshot/record_revision.json", "/mra_snapshot/knowledge_chunk"):
            self.assertEqual((await ds.client.get(path)).status_code, 403)
        for path in ("/mra_snapshot/record_revision/1.json", "/mra_snapshot/revision_field.json?revision_id=1", "/mra_snapshot/knowledge_chunk/chunk"):
            self.assertEqual((await ds.client.get(path, headers=headers)).status_code, 200)
        for path in ("/mra_snapshot.json?sql=select+1", "/mra_snapshot.db", "/mra_snapshot/auth_user", "/mra_snapshot/record_revision.csv?_stream=on"):
            self.assertIn((await ds.client.get(path, headers=headers)).status_code, (400, 403, 404))
        self.assertIn((await ds.client.post("/mra_snapshot/record_revision/-/insert", headers=headers, json={"id": 2})).status_code, (403, 404, 405))
        html = (await ds.client.get("/mra_snapshot/record_revision", headers=headers)).text
        self.assertIn("/mra_snapshot/encounter/1", html)
        self.assertIn("/mra-tools/readability.css", html)
        self.assertEqual((await ds.client.get("/mra-tools/readability.css")).status_code, 200)
        self.assertEqual((await ds.client.get("/mra-tools/../synthetic-allowlist.json")).status_code, 404)
        self.assertEqual(before, (directory / "mra_snapshot.sqlite3").read_bytes())
        with (directory / "mra_snapshot.sqlite3").open("ab") as f: f.write(b"tamper")
        with self.assertRaises(ValueError): make_datasette(directory, "test")


if __name__ == "__main__":
    unittest.main()
