"""Filter a NEW local recovery clone only; never touch a service or source DB.

Pinned scope: patients17/18, encounters19/20, task18, their related rows and
login sessions. Missing/ambiguous/shared relations fail closed. Files are not
copied: a private exact exclusion manifest is returned for the next copy step.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('restore_input_guards', HERE / 'prepare_restore.py')
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
GuardError = G.GuardError
check = G.check
sha = G.sha
PATIENTS = {17, 18}
ENCOUNTERS = {19, 20}
TASKS = {18}
COPY_DIRS = ('uploads', 'outputs', 'speaker_profiles')
DELETE_ORDER = ('approval_item', 'export_event', 'approval', 'agent_task_step',
                'audit_log', 'record_revision', 'agent_task', 'encounter', 'patient', 'auth_session')
TARGET = Path('D:/MediListen_离线归档/restore-inputs-d181aee6-20261027-r5')
SOURCE_RUNTIME = G.SOURCE_RUNTIME


def q(name): return '"' + name.replace('"', '""') + '"'


def encoded(row):
    return json.dumps(list(row), ensure_ascii=False, separators=(',', ':'),
                      default=lambda v: {'blob_hex': v.hex()})


def row_hash(row): return hashlib.sha256(encoded(row).encode('utf8')).hexdigest()


def schema_hash(db):
    return G.digest_json([list(r) for r in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')])


def inventory(db):
    result = {}
    for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        columns = [r[1] for r in db.execute('PRAGMA table_info(' + q(table) + ')')]
        rows = [dict(zip(columns, row)) for row in db.execute('SELECT * FROM ' + q(table))]
        result[table] = {'columns': columns, 'rows': rows}
    return result


def hashes(table, rows=None):
    return sorted(row_hash([r[c] for c in table['columns']]) for r in (table['rows'] if rows is None else rows))


def parse_json(value, code):
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError) as error:
        raise GuardError(code) from error


def relation_ids(value, key):
    found = set()
    if isinstance(value, dict):
        for name, child in value.items():
            if name == key:
                values = child if isinstance(child, list) else [child]
                for item in values:
                    if item is None: continue
                    check(type(item) is int or (isinstance(item, str) and re.fullmatch(r'[0-9]+', item)),
                          'AMBIGUOUS_AUDIT_ID_SHAPE')
                    found.add(int(item))
            elif isinstance(child, (dict, list)):
                found.update(relation_ids(child, key))
    elif isinstance(value, list):
        for child in value: found.update(relation_ids(child, key))
    return found


PATH_KEYS = {'path', 'file_path', 'output_path', 'audio_path', 'audio_file_path',
             'docx', 'markdown', 'md', 'pdf', 'txt', 'json', 'download_path'}


def referenced_paths(value, runtime, key=''):
    found = set()
    if isinstance(value, dict):
        for name, child in value.items(): found.update(referenced_paths(child, runtime, name.lower()))
    elif isinstance(value, list):
        for child in value: found.update(referenced_paths(child, runtime, key))
    elif isinstance(value, str) and key in PATH_KEYS:
        text = value.replace('\\', '/')
        if text.startswith('/app/runtime/'):
            rel = text[len('/app/runtime/'):]
        elif text.startswith(tuple(d + '/' for d in COPY_DIRS)):
            rel = text
        elif Path(value).is_absolute():
            try: rel = Path(value).resolve().relative_to(runtime.resolve()).as_posix()
            except ValueError:
                # A path-valued output outside this runtime cannot safely be copied.
                raise GuardError('REFERENCED_FILE_OUTSIDE_SOURCE_RUNTIME')
        elif re.fullmatch(r'task_18_[^/]+', text):
            rel = 'outputs/' + text
        else:
            return found
        parts = PurePosixPath(rel).parts
        check(parts and parts[0] in COPY_DIRS and '..' not in parts, 'UNSAFE_REFERENCED_FILE_PATH')
        found.add(PurePosixPath(*parts).as_posix())
    return found


def resource_ids(value):
    result = {'audio_id': set(), 'session_id': set()}
    if isinstance(value, dict):
        for key, child in value.items():
            if key in result and child:
                check(isinstance(child, str) and re.fullmatch(r'[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', child),
                      'UNSAFE_AUDIO_SESSION_RESOURCE_ID')
                result[key].add(child)
            if key in {'media_url', 'audio_url', 'events_url', 'result_url'} and isinstance(child, str):
                for resource, route in [('audio_id', '/api/audio/'), ('session_id', '/api/asr/sessions/')]:
                    match = re.search(re.escape(route) + r'([0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})(?:/|[?#]|$)', child)
                    if match: result[resource].add(match.group(1))
            if isinstance(child, (dict, list)):
                nested = resource_ids(child)
                for name in result: result[name].update(nested[name])
    elif isinstance(value, list):
        for child in value:
            nested = resource_ids(child)
            for name in result: result[name].update(nested[name])
    return result


def build_plan(source, supplement, old_policy, runtime):
    source = G.plain_path(source).resolve(); runtime = G.plain_path(runtime).resolve()
    source_sha = sha(source)
    check(source_sha == supplement.get('filter_input_sha256', supplement['sealed_backup']['sha256']), 'SEALED_SHA_CHANGED')
    check(old_policy.get('confirmed_synthetic') is True and bool(old_policy.get('reviewed_by')), 'OLD_POLICY_NOT_REVIEWED')
    entries = {e['patient_pk']: e for e in supplement['entries']}
    check(len(entries) == len(supplement['entries']), 'DUPLICATE_SUPPLEMENT_PATIENT_PK')
    eligible = supplement['eligible_exact_ids']
    check(len(eligible) == len(set(eligible)) and set(eligible) ==
          {e['exact_deidentified_id'] for e in supplement['entries'] if e['allow_in_supplement'] is True},
          'SUPPLEMENT_ELIGIBLE_SET_INCONSISTENT')
    check(PATIENTS.issubset(entries) and all(entries[p]['allow_in_supplement'] is False for p in PATIENTS),
          'PINNED_STOP_PATIENTS_NOT_PRESERVED')
    allowed = set(old_policy['synthetic_patient_ids']) | set(supplement['eligible_exact_ids'])
    check(not allowed.intersection(entries[p]['exact_deidentified_id'] for p in PATIENTS), 'STOP_IDS_IN_ALLOWED_POLICY')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        check(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'SEALED_INTEGRITY_FAILED')
        check(not db.execute('PRAGMA foreign_key_check').fetchall(), 'SEALED_FOREIGN_KEYS_FAILED')
        tables = inventory(db); original_schema = schema_hash(db)
    check(set(DELETE_ORDER).issubset(tables), 'PINNED_SCHEMA_MISSING_TABLE')
    for name in DELETE_ORDER: check('id' in tables[name]['columns'], 'PINNED_SCHEMA_ID_MISSING')
    rows = {name: table['rows'] for name, table in tables.items()}
    patient_rows = {r['id']: r for r in rows['patient']}
    check(PATIENTS.issubset(patient_rows) and all(patient_rows[p]['deidentified_id'] == entries[p]['exact_deidentified_id'] for p in PATIENTS),
          'STOP_PATIENT_EXACT_ID_CHANGED')
    check(all(r['deidentified_id'] in allowed for r in rows['patient'] if r['id'] not in PATIENTS),
          'REMAINING_PATIENT_NOT_EXACTLY_REVIEWED')
    check({r['id'] for r in rows['encounter'] if r['patient_id'] in PATIENTS} == ENCOUNTERS, 'EXCLUDED_ENCOUNTER_SET_CHANGED')
    excluded_enc = [r for r in rows['encounter'] if r['id'] in ENCOUNTERS]
    check({r['id'] for r in rows['agent_task'] if r.get('encounter_id') in ENCOUNTERS} |
          {r['task_id'] for r in excluded_enc if r.get('task_id') is not None} == TASKS, 'EXCLUDED_TASK_SET_CHANGED')
    excluded_tasks = [r for r in rows['agent_task'] if r['id'] in TASKS]
    check(len(excluded_tasks) == 1 and excluded_tasks[0].get('encounter_id') == 19, 'PINNED_TASK18_BINDING_CHANGED')
    revision_ids = {r['id'] for r in rows['record_revision'] if r.get('encounter_id') in ENCOUNTERS or r.get('task_id') in TASKS}
    revision_ids.update(r['current_revision_id'] for r in excluded_enc if r.get('current_revision_id') is not None)
    revision_ids.update(r['current_record_revision_id'] for r in excluded_tasks if r.get('current_record_revision_id') is not None)
    check(revision_ids.issubset({r['id'] for r in rows['record_revision']}), 'MISSING_EXCLUDED_REVISION')
    revisions = {r['id']: r for r in rows['record_revision']}
    for r in rows['encounter']:
        if r['id'] not in ENCOUNTERS:
            check(r.get('task_id') not in TASKS and r.get('current_revision_id') not in revision_ids, 'SHARED_TASK_OR_REVISION_WITH_RETAINED_ENCOUNTER')
            rid = r.get('current_revision_id')
            check(rid is None or (rid in revisions and revisions[rid].get('encounter_id') == r['id']),
                  'RETAINED_CURRENT_REVISION_MISSING_OR_WRONG_ENCOUNTER')
    for r in rows['agent_task']:
        if r['id'] not in TASKS:
            check(r.get('encounter_id') not in ENCOUNTERS and r.get('current_record_revision_id') not in revision_ids, 'SHARED_REVISION_WITH_RETAINED_TASK')
            rid = r.get('current_record_revision_id')
            check(rid is None or (rid in revisions and revisions[rid].get('task_id') == r['id']
                                  and revisions[rid].get('encounter_id') == r.get('encounter_id')),
                  'RETAINED_TASK_REVISION_MISSING_OR_WRONG_OWNER')
    for r in rows['record_revision']:
        if r['id'] in revision_ids:
            check(r.get('encounter_id') in ENCOUNTERS and (r.get('task_id') is None or r['task_id'] in TASKS), 'SHARED_REVISION_ID')
    approval_ids = {r['id'] for r in rows['approval'] if r.get('encounter_id') in ENCOUNTERS or r.get('task_id') in TASKS or r.get('revision_id') in revision_ids}
    groups = {'patient': PATIENTS, 'encounter': ENCOUNTERS, 'agent_task': TASKS, 'record_revision': revision_ids,
              'approval': approval_ids, 'auth_session': {r['id'] for r in rows['auth_session']},
              'agent_task_step': {r['id'] for r in rows['agent_task_step'] if r.get('task_id') in TASKS}}
    for table in ('approval', 'approval_item', 'export_event'):
        selected = set()
        for r in rows[table]:
            hit = (r.get('encounter_id') in ENCOUNTERS or r.get('task_id') in TASKS or
                   r.get('revision_id') in revision_ids or r.get('approval_id') in approval_ids or
                   (table == 'approval' and r['id'] in approval_ids))
            if not hit: continue
            for key, identifiers in [('encounter_id', ENCOUNTERS), ('task_id', TASKS),
                                     ('revision_id', revision_ids), ('approval_id', approval_ids)]:
                if key in r and r[key] is not None: check(r[key] in identifiers, 'SHARED_APPROVAL_OR_EXPORT_RELATION')
            selected.add(r['id'])
        groups[table] = selected
    audit_ids = set()
    for r in rows['audit_log']:
        if r.get('task_id') in TASKS:
            audit_ids.add(r['id']); continue
        if r.get('task_id') is not None: continue
        # Invalid NULL-task detail has no reliable owning relationship: STOP.
        detail = parse_json(r.get('event_detail') or '{}', 'UNPARSEABLE_NULL_TASK_AUDIT_STOP')
        eids, pids = relation_ids(detail, 'encounter_id'), relation_ids(detail, 'patient_id')
        if eids & ENCOUNTERS or pids & PATIENTS:
            check(not eids - ENCOUNTERS and not pids - PATIENTS, 'SHARED_NULL_TASK_AUDIT_RELATION')
            audit_ids.add(r['id'])
    groups['audit_log'] = audit_ids
    expected = {}
    for name, table in tables.items():
        drop = groups.get(name, set())
        expected[name] = hashes(table, [r for r in table['rows'] if r.get('id') not in drop])
    excluded_paths, kept_paths = set(), set()
    excluded_resources = {'audio_id': set(), 'session_id': set()}
    retained_resources = {'audio_id': set(), 'session_id': set()}
    for name, column in [('export_event', 'exports_json'), ('agent_task', 'result_json'), ('record_revision', 'result_json')]:
        check(column in tables[name]['columns'], 'PINNED_FILE_JSON_COLUMN_MISSING')
        for r in rows[name]:
            if not r.get(column): continue
            value = parse_json(r[column], 'UNPARSEABLE_FILE_REFERENCE_JSON')
            found = referenced_paths(value, runtime)
            (excluded_paths if r['id'] in groups[name] else kept_paths).update(found)
            resources = resource_ids(value)
            destination = excluded_resources if r['id'] in groups[name] else retained_resources
            for key in destination: destination[key].update(resources[key])
    manifests = {name: G.file_manifest(runtime / name) for name in COPY_DIRS}
    all_files = {name + '/' + rel for name, manifest in manifests.items() for rel in manifest['files']}
    resource_files, session_directories = set(), set()
    # Audio generators persist a text task plus asr_source.audio_id; therefore
    # input_type=text never proves the absence of audio/ASR-session assets.
    for rel in all_files:
        if rel.startswith('uploads/') and PurePosixPath(rel).name == 'session.json':
            metadata = G.read_json(runtime / rel)
            resources = resource_ids(metadata)
            if resources['audio_id'] & excluded_resources['audio_id'] or resources['session_id'] & excluded_resources['session_id']:
                check(not resources['audio_id'] & retained_resources['audio_id'], 'SHARED_ASR_SESSION_WITH_RETAINED_AUDIO')
                session_ids = resources['session_id']
                check(len(session_ids) == 1 and PurePosixPath(rel).parent.name in session_ids, 'ASR_SESSION_DIRECTORY_ID_MISMATCH')
                excluded_resources['session_id'].update(session_ids)
                session_directories.add(PurePosixPath(rel).parent.as_posix())
    for key in excluded_resources:
        check(not excluded_resources[key] & retained_resources[key], 'SHARED_AUDIO_OR_SESSION_WITH_RETAINED_ROW')
    for rel in all_files:
        name = PurePosixPath(rel).name
        if rel.startswith('uploads/') and (any(name == aid or name.startswith(aid + '.') for aid in excluded_resources['audio_id'])
                or any(rel.startswith(directory + '/') for directory in session_directories)):
            resource_files.add(rel)
    prefix_files = {rel for rel in all_files if PurePosixPath(rel).name.startswith('task_18_')}
    check(not (excluded_paths | prefix_files | resource_files) & kept_paths, 'SHARED_EXCLUDED_FILE_WITH_RETAINED_ROW')
    # Only actually existing referenced files appear as path exclusions. Missing
    # references are separately recorded; no invented paths or substring scans.
    existing_references = excluded_paths & all_files
    check(sha(source) == source_sha, 'SEALED_CHANGED_DURING_PLAN')
    return {'source_sha256': source_sha, 'schema_sha256': original_schema, 'delete_ids': groups,
            'expected_row_hashes': expected, 'source_row_hashes': {n: hashes(t) for n, t in tables.items()},
            'excluded_file_paths': sorted(existing_references),
            'missing_excluded_file_references': sorted(excluded_paths - all_files),
            'excluded_task18_prefix_file_paths': sorted(prefix_files),
            'excluded_resource_file_paths': sorted(resource_files),
            'copy_excluded_directory_paths': sorted(session_directories),
            'excluded_resource_ids': {k: sorted(v) for k, v in excluded_resources.items()},
            'copy_excluded_paths': sorted(existing_references | prefix_files | resource_files),
            'source_file_manifests': manifests, 'remaining_patient_count': len(rows['patient']) - len(PATIENTS)}


def filter_database(sealed: Path, working: Path, base_policy: dict, supplement: dict, *, source_runtime=None) -> dict:
    source, output = Path(sealed), Path(working)
    runtime = Path(source_runtime) if source_runtime is not None else SOURCE_RUNTIME
    G.plain_path(output)
    check(not output.exists() and not output.resolve().is_relative_to(runtime.resolve())
          and output.resolve() != source.resolve(), 'OUTPUT_EXISTS_OR_OVERLAPS_SOURCE')
    plan = build_plan(source, supplement, base_policy, runtime)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.' + uuid.uuid4().hex + '.unverified.private')
    # The runnable database name is published only after all exclusion and
    # preservation checks pass. Failed full clones remain explicitly private.
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as src, \
            closing(sqlite3.connect(temporary)) as dst:
        src.backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')
        dst.execute('PRAGMA foreign_keys=ON')
        check(dst.execute('PRAGMA foreign_keys').fetchone()[0] == 1, 'FOREIGN_KEYS_NOT_ENABLED')
        dst.execute('BEGIN IMMEDIATE'); dst.execute('PRAGMA defer_foreign_keys=ON')
        for table in DELETE_ORDER:
            ids = sorted(plan['delete_ids'][table])
            if ids:
                dst.execute('DELETE FROM ' + q(table) + ' WHERE id IN (' + ','.join('?' for _ in ids) + ')', ids)
        check(not dst.execute('PRAGMA foreign_key_check').fetchall(), 'FILTER_FOREIGN_KEYS_FAILED')
        check(schema_hash(dst) == plan['schema_sha256'], 'SCHEMA_CHANGED')
        actual = {name: hashes(table) for name, table in inventory(dst).items()}
        check(actual == plan['expected_row_hashes'], 'RETAINED_ROW_SEMANTICS_CHANGED')
        dst.commit()
        dst.execute('VACUUM')  # Erase excluded rows and old session tokens from free pages.
        check(not dst.execute('PRAGMA foreign_key_check').fetchall(), 'FINAL_FOREIGN_KEYS_FAILED')
        check(dst.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'FINAL_INTEGRITY_FAILED')
        check(schema_hash(dst) == plan['schema_sha256'], 'FINAL_SCHEMA_CHANGED')
        check({name: hashes(table) for name, table in inventory(dst).items()} == plan['expected_row_hashes'],
              'FINAL_RETAINED_ROW_SEMANTICS_CHANGED')
    check(sha(source) == plan['source_sha256'], 'SEALED_SOURCE_CHANGED')
    for name, manifest in plan['source_file_manifests'].items():
        G.guard_equal_manifest(manifest, G.file_manifest(runtime / name))
    business_fingerprints = G.db_fingerprints(temporary)
    check(not output.exists(), 'WORKING_FILE_APPEARED_DURING_FILTER')
    temporary.rename(output)
    return {'status': 'FILTERED_DATABASE_ONLY_NOT_RUNNING', 'at': datetime.now(timezone.utc).isoformat(),
            'source_sha256_before_and_after': plan['source_sha256'], 'source_unchanged': True,
            'sealed_sha256': plan['source_sha256'], 'provenance_r4_sealed_sha256': supplement['sealed_backup']['sha256'],
            'schema_sha256_before_and_after': plan['schema_sha256'],
            'excluded_patient_ids': sorted(PATIENTS), 'excluded_encounter_ids': sorted(ENCOUNTERS),
            'excluded_task_ids': sorted(TASKS), 'remaining_patient_count': plan['remaining_patient_count'],
            'deleted_row_ids': {n: sorted(v) for n, v in plan['delete_ids'].items()},
            'source_row_hashes': plan['source_row_hashes'], 'retained_row_hashes': plan['expected_row_hashes'],
            'retained_table_fingerprints': {n: {'rows': len(v), 'sha256': G.digest_json(v)} for n, v in plan['expected_row_hashes'].items()},
            'business_fingerprints': business_fingerprints,
            'retainedcounts': {n: len(v) for n, v in plan['expected_row_hashes'].items()},
            'excluded_ids': {'patient': sorted(PATIENTS), 'encounter': sorted(ENCOUNTERS), 'task': sorted(TASKS)},
            'excluded_file_paths': plan['excluded_file_paths'],
            'excluded_task18_prefix_file_paths': plan['excluded_task18_prefix_file_paths'],
            'copy_excluded_paths': plan['copy_excluded_paths'],
            'excluded_resource_file_paths': plan['excluded_resource_file_paths'],
            'copy_excluded_directory_paths': plan['copy_excluded_directory_paths'],
            'excluded_resource_ids': plan['excluded_resource_ids'],
            'copy_exclusion_prefix': 'task_18_', 'copy_exclusion_regex': '^task_18_',
            'missing_excluded_file_references': plan['missing_excluded_file_references'],
            'auth_user_and_knowledge_rows_unchanged': True, 'model_asr_service_git_operations': 0,
            'file_copy_operations': 0, 'boundary': 'Filtered subset only; not a complete23-patient recovery or runtime/workflow acceptance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sealed', type=Path, required=True)
    parser.add_argument('--supplement', type=Path, required=True)
    parser.add_argument('--old-allowlist', type=Path, required=True)
    parser.add_argument('--source-runtime', type=Path, required=True)
    parser.add_argument('--target', type=Path, default=TARGET)
    args = parser.parse_args()
    try:
        for p in (args.sealed, args.supplement, args.old_allowlist, args.source_runtime, args.target): G.plain_path(p)
        check(args.target.resolve() == TARGET.resolve() and not args.target.exists(), 'NEW_R5_TARGET_REQUIRED')
        supplement = G.read_json(args.supplement); policy = G.read_json(args.old_allowlist)
        check(sha(args.old_allowlist) == supplement['original_allowlist']['sha256'], 'ORIGINAL_ALLOWLIST_CHANGED')
        check(len(policy['synthetic_patient_ids']) == 16, 'ORIGINAL16_ALLOWLIST_REQUIRED')
        # No target is created until all source relationships and audit details pass.
        build_plan(args.sealed, supplement, policy, args.source_runtime)
        args.target.mkdir()
        receipt = filter_database(args.sealed, args.target / 'runtime/medical_record_agent.sqlite3', policy, supplement,
                                  source_runtime=args.source_runtime)
        G.save_json(args.target / 'filter-receipt.private.json', receipt)
        print(json.dumps({'status': receipt['status'], 'remaining_patient_count': receipt['remaining_patient_count'],
                          'excluded_patient_ids': sorted(PATIENTS), 'source_unchanged': True,
                          'schema_unchanged': True, 'receipt': str(args.target / 'filter-receipt.private.json'),
                          'model_asr_service_git_operations': 0}))
    except BaseException as error:
        print(json.dumps({'status': 'STOP', 'error_code': str(error) if isinstance(error, GuardError) else type(error).__name__,
                          'source_not_written': True, 'failed_new_copy_retained_if_created': True,
                          'model_asr_service_git_operations': 0}))
        raise SystemExit(1)


if __name__ == '__main__': main()
