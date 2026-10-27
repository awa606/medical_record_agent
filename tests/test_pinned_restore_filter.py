from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('filtered_restore', HERE.parent / 'scripts/experiments/filter_pinned_restore.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def fixture(root):
    source = root / 'sealed.sqlite3'; runtime = root / 'source-runtime'
    for name in m.COPY_DIRS: (runtime / name).mkdir(parents=True)
    for name in ('task_18_note.docx', 'task_18_extra.md', 'task_118_keep.docx'):
        (runtime / 'outputs' / name).write_text('fixture only', encoding='utf8')
    (runtime / 'uploads' / 'excluded.wav').write_bytes(b'synthetic-fixture')
    audio_id, session_id = 'a'*32, 'b'*32
    for suffix in ('.wav', '.record.json', '.transcript.json'):
        (runtime/'uploads'/(audio_id+suffix)).write_bytes(b'synthetic-sidecar')
    session_dir=runtime/'uploads/asr_sessions'/session_id;session_dir.mkdir(parents=True)
    (session_dir/'session.json').write_text(json.dumps({'audio_id':audio_id,'session_id':session_id}),encoding='utf8')
    with closing(sqlite3.connect(source)) as c:
        c.executescript('''
CREATE TABLE patient(id INTEGER PRIMARY KEY,deidentified_id TEXT);
CREATE TABLE encounter(id INTEGER PRIMARY KEY,patient_id INTEGER REFERENCES patient(id),task_id INTEGER REFERENCES agent_task(id),current_revision_id INTEGER);
CREATE TABLE agent_task(id INTEGER PRIMARY KEY,encounter_id INTEGER,current_record_revision_id INTEGER,result_json TEXT);
CREATE TABLE record_revision(id INTEGER PRIMARY KEY,encounter_id INTEGER REFERENCES encounter(id),task_id INTEGER REFERENCES agent_task(id),result_json TEXT);
CREATE TABLE approval(id INTEGER PRIMARY KEY,encounter_id INTEGER REFERENCES encounter(id),revision_id INTEGER REFERENCES record_revision(id),task_id INTEGER REFERENCES agent_task(id));
CREATE TABLE approval_item(id INTEGER PRIMARY KEY,approval_id INTEGER REFERENCES approval(id),revision_id INTEGER REFERENCES record_revision(id),task_id INTEGER REFERENCES agent_task(id));
CREATE TABLE export_event(id INTEGER PRIMARY KEY,encounter_id INTEGER REFERENCES encounter(id),revision_id INTEGER REFERENCES record_revision(id),approval_id INTEGER REFERENCES approval(id),task_id INTEGER REFERENCES agent_task(id),exports_json TEXT);
CREATE TABLE agent_task_step(id INTEGER PRIMARY KEY,task_id INTEGER REFERENCES agent_task(id),payload TEXT);
CREATE TABLE audit_log(id INTEGER PRIMARY KEY,task_id INTEGER REFERENCES agent_task(id),event_detail TEXT);
CREATE TABLE auth_user(id INTEGER PRIMARY KEY,password_hash TEXT);
CREATE TABLE auth_session(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES auth_user(id),token_hash TEXT);
CREATE TABLE knowledge_source(id INTEGER PRIMARY KEY,bytes BLOB);
INSERT INTO patient VALUES(1,'SIM-TEST-KEEP'),(17,'SIM-TEST-STOP17'),(18,'SIM-TEST-STOP18');
INSERT INTO encounter VALUES(1,1,1,1),(19,17,18,31),(20,18,NULL,NULL);
INSERT INTO agent_task VALUES(1,1,1,'{}'),(18,19,31,'{"exports":{"docx":"/app/runtime/outputs/task_18_note.docx"},"audio_path":"/app/runtime/uploads/excluded.wav"}');
INSERT INTO record_revision VALUES(1,1,1,'{}'),(31,19,18,'{}');
INSERT INTO approval VALUES(1,1,1,1),(12,19,31,18);
INSERT INTO approval_item VALUES(1,1,1,1),(2,12,31,18);
INSERT INTO export_event VALUES(1,1,1,1,1,'{"docx":"/app/runtime/outputs/task_118_keep.docx"}'),(2,19,31,12,18,'{"docx":"/app/runtime/outputs/task_18_note.docx"}');
INSERT INTO agent_task_step VALUES(1,1,'keep-byte-exact'),(2,18,'excluded');
INSERT INTO audit_log VALUES(1,1,'{}'),(2,18,'not-json-but-task18-owned'),(3,NULL,'{"encounter_id":19}'),(4,NULL,'{"patient_id":17}'),(5,NULL,'{"encounter_id":1}');
INSERT INTO auth_user VALUES(1,'private-fixture-hash');
INSERT INTO auth_session VALUES(1,1,'private-fixture-token');
INSERT INTO knowledge_source VALUES(1,X'000102ff');
''')
        c.commit()
        payload=json.loads(c.execute('SELECT result_json FROM agent_task WHERE id=18').fetchone()[0])
        payload['asr_source']={'audio_id':audio_id}
        c.execute('UPDATE agent_task SET result_json=? WHERE id=18',(json.dumps(payload),));c.commit()
    policy = {'confirmed_synthetic': True, 'reviewed_by': 'fixture', 'synthetic_patient_ids': ['SIM-TEST-KEEP']}
    supplement = {'sealed_backup': {'sha256': m.sha(source)}, 'eligible_exact_ids': [],
                  'entries': [{'patient_pk': p, 'exact_deidentified_id': f'SIM-TEST-STOP{p}', 'allow_in_supplement': False} for p in (17,18)]}
    return source, runtime, policy, supplement


class FilterPinnedRestore(unittest.TestCase):
    def test_precise_filter_retains_rows_and_excludes_only_owned_files(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix='filter-fixture-') as temp:
            root = Path(temp); source, runtime, policy, supplement = fixture(root)
            before = m.sha(source)
            result = m.filter_database(source, root / 'new/runtime/copy.sqlite3', policy, supplement, source_runtime=runtime)
            self.assertEqual(m.sha(source), before)
            self.assertEqual(result['remaining_patient_count'], 1)
            self.assertEqual(result['deleted_row_ids']['audit_log'], [2,3,4])
            self.assertEqual(result['excluded_file_paths'], ['outputs/task_18_note.docx','uploads/excluded.wav'])
            self.assertIn('outputs/task_18_extra.md', result['excluded_task18_prefix_file_paths'])
            self.assertNotIn('outputs/task_118_keep.docx', result['copy_excluded_paths'])
            self.assertEqual(len(result['excluded_resource_file_paths']),4)
            self.assertEqual(result['excluded_resource_ids']['audio_id'],['a'*32])
            self.assertIn('uploads/asr_sessions/'+'b'*32+'/session.json',result['copy_excluded_paths'])
            for name in ('auth_user','knowledge_source'):
                self.assertEqual(result['source_row_hashes'][name], result['retained_row_hashes'][name])
            with closing(sqlite3.connect(root/'new/runtime/copy.sqlite3')) as c:
                self.assertEqual(c.execute('SELECT id FROM patient').fetchall(), [(1,)])
                self.assertEqual(c.execute('SELECT id FROM record_revision').fetchall(), [(1,)])
                self.assertEqual(c.execute('SELECT COUNT(*) FROM auth_session').fetchone()[0], 0)
                self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())

    def test_shared_ids_and_ambiguous_audits_fail_before_output(self):
        changes = [
            "UPDATE encounter SET task_id=18 WHERE id=1",
            "UPDATE encounter SET current_revision_id=31 WHERE id=1",
            "UPDATE encounter SET current_revision_id=999 WHERE id=1",
            "UPDATE export_event SET approval_id=12 WHERE id=1",
            "UPDATE audit_log SET event_detail='unparseable' WHERE id=5",
            "UPDATE audit_log SET event_detail='{\"encounter_id\":[1,19]}' WHERE id=5",
            "UPDATE agent_task SET result_json='{\"docx\":\"/app/runtime/outputs/task_18_note.docx\"}' WHERE id=1",
            "CREATE TRIGGER reject_side_effect AFTER DELETE ON audit_log BEGIN UPDATE auth_user SET password_hash='must-not-persist' WHERE id=1; END",
            "UPDATE agent_task SET result_json='{\"asr_source\":{\"audio_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}}' WHERE id=1",
            "UPDATE agent_task SET result_json='{\"media_url\":\"/api/audio/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/stream\"}' WHERE id=1",
        ]
        for change in changes:
            with self.subTest(kind=changes.index(change)), tempfile.TemporaryDirectory(dir=HERE, prefix='filter-negative-') as temp:
                root = Path(temp); source, runtime, policy, supplement = fixture(root)
                with closing(sqlite3.connect(source)) as c: c.execute(change); c.commit()
                supplement['sealed_backup']['sha256'] = m.sha(source)
                destination = root / 'must-not-exist/copy.sqlite3'
                with self.assertRaises(m.GuardError): m.filter_database(source, destination, policy, supplement, source_runtime=runtime)
                self.assertFalse(destination.exists())
        for inconsistent in ('duplicate','eligible'):
            with self.subTest(policy=inconsistent), tempfile.TemporaryDirectory(dir=HERE,prefix='filter-policy-') as temp:
                root=Path(temp);source,runtime,policy,supplement=fixture(root)
                if inconsistent=='duplicate':supplement['entries'].append(dict(supplement['entries'][0]))
                else:supplement['eligible_exact_ids'].append('SIM-TEST-NOT-REVIEWED')
                with self.assertRaises(m.GuardError):m.filter_database(source,root/'absent/copy.sqlite3',policy,supplement,source_runtime=runtime)
                self.assertFalse((root/'absent/copy.sqlite3').exists())


if __name__ == '__main__': unittest.main(verbosity=2)
