import importlib.util
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock
from contextlib import contextmanager

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('restore_inputs', HERE.parent / 'scripts/experiments/prepare_restore.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RestoreInputGuards(unittest.TestCase):
    def test_identity_port_ledger_snapshot_and_lock_guards(self):
        cfg = dict(m.EXPECTED, containers={s: {'image': m.IMAGE} for s in ('app', 'gateway')})
        m.guard_identity(cfg)
        for key, value in [('backend_git_sha', 'a' * 40), ('app_git_sha', 'b' * 40), ('port', 18029)]:
            with self.subTest(key=key), self.assertRaises(m.GuardError):
                m.guard_identity(dict(cfg, **{key: value}))
        for value in (8798, 18028, 80):
            with self.subTest(port=value), self.assertRaises(m.GuardError):
                m.guard_target_port(value)
        with tempfile.TemporaryDirectory(dir=HERE, prefix='guard-ledger-') as tmp:
            path = Path(tmp) / 'ledger.json'
            path.write_text(json.dumps({'calls': [{'unknown_cost_schema': 99}]}), encoding='utf8')
            summary = m.ledger_summary(path)
            self.assertEqual(summary['calls'], 1)
            self.assertEqual(summary['sha256'], m.sha(path))
            self.assertNotIn('charged_micro_cny', summary)
            self.assertNotIn('budget_micro_cny', summary)
            self.assertFalse(summary['budget_reset'])
        with patch.object(m, 'run', return_value='{}') as run:
            m.source_db_fingerprint('synthetic-container')
            self.assertIn("s.execute('BEGIN')", run.call_args.kwargs['input_text'])
        events = []
        @contextmanager
        def lock(path):
            events.append(('enter', str(path)))
            try: yield
            finally: events.append(('exit', str(path)))
        pilot = Mock(spec=['operation_lock', 'validate', 'assert_idle'])
        pilot.operation_lock.side_effect = lock
        config = {'switch_lock': str(HERE / 'synthetic-switch.json')}
        context = (pilot, config)
        def observed(_context, _items):
            self.assertEqual([x[0] for x in events], ['enter', 'enter'])
            return {'prepared': 'mock-only'}
        with patch.object(m, 'source_context', return_value=context), patch.object(m, 'read_json', return_value=config), \
                patch.object(m, 'prepare_locked', side_effect=observed):
            self.assertEqual(m.prepare(True), {'prepared': 'mock-only'})
        self.assertEqual([x[0] for x in events], ['enter', 'enter', 'exit', 'exit'])
        pilot.assert_idle.assert_called_once_with(config, pilot.validate.return_value, confirmed_saved=True)

    def test_all_patient_identities_require_exact_reviewed_allowlist(self):
        policy = {'confirmed_synthetic': True, 'reviewed_by': 'reviewed', 'synthetic_patient_ids': ['SIM-TEST-A']}
        m.guard_patients(['SIM-TEST-A'], policy)
        for ids in ([], ['SIM-TEST-A', 'SIM-TEST-UNREVIEWED'], ['REAL-PRIVATE'], [None]):
            with self.subTest(ids=bool(ids)), self.assertRaises(m.GuardError):
                m.guard_patients(ids, policy)

    def test_copy_change_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix='guard-copy-') as tmp:
            root = Path(tmp); src = root / 'source'; dst = root / 'copy'; src.mkdir()
            (src / 'document.txt').write_text('synthetic file', encoding='utf8')
            before = m.file_manifest(src)
            m.copy_checked(src, dst, before)
            (src / 'document.txt').write_text('changed during copy', encoding='utf8')
            with self.assertRaises(m.GuardError):
                m.guard_equal_manifest(before, m.file_manifest(src))

    def test_credentials_and_reparse_are_not_copied_or_opened(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix='guard-secret-') as tmp:
            root = Path(tmp)
            (root / 'private.env').write_text('not-a-real-secret', encoding='utf8')
            with self.assertRaises(m.GuardError):
                m.file_manifest(root)
            self.assertTrue(m.forbidden_copy_name('admin-credentials.private.json'))
            self.assertTrue(m.forbidden_copy_name('doctor-browser-profile'))
            self.assertFalse(m.forbidden_copy_name('session.json'))
            with self.assertRaises(m.GuardError):
                m.guard_file_attributes(0x400, False)

    def test_session_removal_preserves_schema_and_other_tables(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix='guard-db-') as tmp:
            root = Path(tmp); raw = root / 'sealed.sqlite3'; dest = root / 'working.sqlite3'
            with closing(sqlite3.connect(raw)) as c:
                c.executescript("CREATE TABLE patient(id INTEGER PRIMARY KEY,deidentified_id TEXT);"
                    "INSERT INTO patient VALUES(1,'SIM-TEST-A');"
                    "CREATE TABLE auth_user(id INTEGER PRIMARY KEY,password_hash TEXT);"
                    "INSERT INTO auth_user VALUES(1,'synthetic-hash');"
                    "CREATE TABLE auth_session(id INTEGER PRIMARY KEY,token_hash TEXT);"
                    "INSERT INTO auth_session VALUES(1,'synthetic-token');")
                c.commit()
            policy = {'confirmed_synthetic': True, 'reviewed_by': 'reviewed', 'synthetic_patient_ids': ['SIM-TEST-A']}
            sealed_sha = m.sha(raw)
            result = m.prepare_database(raw, dest, policy)
            self.assertEqual(result['sessions_removed'], 1)
            self.assertEqual(m.sha(raw), sealed_sha)
            self.assertEqual(m.db_fingerprints(raw), m.db_fingerprints(dest))
            with closing(sqlite3.connect(dest)) as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM auth_session').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
