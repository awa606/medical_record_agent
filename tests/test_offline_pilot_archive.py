import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from app.services.auth import verify_password
from scripts.offline_pilot_archive import (TABLES, fingerprints, file_inventory, verify,
                                           sanitize_database, restore_credentials,
                                           assert_models_idle, choose_port)


class OfflineDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def seed(self):
        db = self.root / 'source.sqlite3'
        with closing(sqlite3.connect(db)) as c:
            for table in TABLES:
                if table == 'patient':
                    c.execute('CREATE TABLE patient(id INTEGER PRIMARY KEY, deidentified_id TEXT)')
                    c.execute("INSERT INTO patient VALUES(1,'SIM-APPROVED')")
                else:
                    c.execute(f'CREATE TABLE {table}(id INTEGER PRIMARY KEY, owner_user_id INTEGER)')
                    c.execute(f'INSERT INTO {table} VALUES(1,7)')
            c.executescript("""
                CREATE TABLE auth_user(id INTEGER PRIMARY KEY,username TEXT,display_name TEXT,role TEXT,password_hash TEXT,is_active INTEGER,last_login_at TEXT);
                CREATE TABLE auth_session(token_hash TEXT);
                CREATE TABLE audit_log(detail_json TEXT);
                INSERT INTO auth_user VALUES(7,'old-admin','原账号','admin','OLD_PASSWORD_HASH',1,'yesterday');
                INSERT INTO auth_session VALUES('OLD_LOGIN_TOKEN');
                INSERT INTO audit_log VALUES('private audit');
            """)
            c.commit()
        policy = self.root / 'policy.json'
        policy.write_text(json.dumps({'confirmed_synthetic': True, 'reviewed_by': 'unit test',
                                     'synthetic_patient_ids': ['SIM-APPROVED']}))
        return db, policy

    def test_backup_removes_credentials_but_preserves_owner_ids_and_history(self):
        source, policy = self.seed()
        original = source.read_bytes()
        target = self.root / 'anonymous.sqlite3'
        expected = fingerprints(source)
        sanitize_database(source, target, policy)
        self.assertEqual(expected, fingerprints(target))
        self.assertEqual(original, source.read_bytes())
        self.assertNotIn(b'OLD_PASSWORD_HASH', target.read_bytes())
        self.assertNotIn(b'OLD_LOGIN_TOKEN', target.read_bytes())
        with closing(sqlite3.connect(target)) as c:
            self.assertEqual(c.execute('SELECT id,is_active FROM auth_user').fetchone(), (7, 0))
            self.assertEqual(c.execute('SELECT count(*) FROM auth_session').fetchone()[0], 0)
        credentials = restore_credentials(target, self.root / 'credentials.private.json')
        with closing(sqlite3.connect(target)) as c:
            user = c.execute('SELECT id,password_hash,is_active FROM auth_user').fetchone()
        self.assertEqual((user[0], user[2]), (7, 1))
        self.assertTrue(verify_password(credentials[0]['password'], user[1]))
        self.assertEqual(expected, fingerprints(target))

    def test_unapproved_patient_blocks_export(self):
        source, policy = self.seed()
        with closing(sqlite3.connect(source)) as c:
            c.execute("INSERT INTO patient VALUES(2,'UNKNOWN')")
            c.commit()
        with self.assertRaisesRegex(ValueError, 'outside reviewed'):
            sanitize_database(source, self.root / 'out.sqlite3', policy)

    def test_verify_rejects_tamper_extra_missing_and_traversal(self):
        p = self.root / 'package'
        p.mkdir()
        data = p / 'model.bin'
        data.write_bytes(b'fixed')
        manifest = {'schema_version': 'mra-offline-pilot-v2', 'files': file_inventory(p)}
        (p / 'manifest.json').write_text(json.dumps(manifest))
        verify(p)
        data.write_bytes(b'changed')
        with self.assertRaises(ValueError): verify(p)
        data.write_bytes(b'fixed')
        (p / 'unexpected.txt').write_text('extra')
        with self.assertRaises(ValueError): verify(p)
        (p / 'unexpected.txt').unlink()
        data.unlink()
        with self.assertRaises(ValueError): verify(p)
        manifest['files'] = {'../escape.txt': {'sha256': 'x', 'bytes': 1}}
        (p / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'escapes'): verify(p)

    def test_running_model_peer_is_refused_without_stopping_it(self):
        peer = json.dumps({'Names': 'mra51usage8798-ollama-1'})
        with patch('scripts.offline_pilot_archive.run', return_value=peer) as runner:
            with self.assertRaises(ValueError): assert_models_idle('newrestore')
            self.assertEqual(runner.call_count, 1)
        with patch('scripts.offline_pilot_archive.run', return_value=''):
            assert_models_idle('newrestore')

    def test_occupied_port_refuses_and_keeps_other_service(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            with self.assertRaises(ValueError): choose_port((port,))
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                pass


if __name__ == '__main__':
    unittest.main()
