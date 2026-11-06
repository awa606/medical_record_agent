"""Prepare local recovery INPUTS only. Never build/create/start/stop containers.

dry-run validates pinned source, copy boundaries and external dependencies.
prepare additionally requires --idle-confirmed and copies a consistent backup.
Private outputs stay local: no upload, migration, model request or schema init.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import closing, ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANONICAL = ROOT / '.artifacts/online-demo-20261019/deploy-9af10d7/launcher-8798.json'
COMPOSE_SOURCE = ROOT / '.artifacts/doctor-negative-quality-20261027-r3/compose.production.private.json'
SOURCE_RUNTIME = ROOT / '.artifacts/online-demo-20261019/deploy-9af10d7/runtime'
ALLOWLIST = SOURCE_RUNTIME.parent / 'viewer-allowlist.json'
ONLINE_SOURCE = ROOT / '.artifacts/online-demo-20261019'
KEY_SOURCE = ONLINE_SOURCE / 'private.env'
TARGET = Path('D:/MediListen_离线归档/restore-inputs-d181aee6-20261027-r4')
IMAGE = 'sha256:ae4af4dd780e132edfbbb7d39f85c08a2b117d19097387596e0b2a407b4ddaed'
EXPECTED = {
    'project': 'mra51doctornegativequality879820261027', 'port': 8798,
    'provider_profile': 'online_deepseek',
    'backend_git_sha': 'd181aee61223f16efa0e88094d3b892077d0a97c',
    'app_git_sha': 'cd56f59d6c7bf6ff02a6e78c1367cd01768c98d9',
}
PROJECT = 'mra51restoreinputs20261027r4'
PORT = 18029
COOKIE = 'medilisten_restore_inputs_20261027_r4'
COPY_DIRS = ('uploads', 'outputs', 'speaker_profiles')
KEY_TARGETS = ('/run/secrets/deepseek.env', '/app/online-private/private.env')
CACHE_TARGETS = ('/app/model_cache/modelscope', '/app/model_cache/hf')
SUBNETS = {n: f'10.203.53.{i}/28' for n, i in [('internal', 0), ('online', 16), ('frontend', 32)]}


class GuardError(RuntimeError):
    pass


def check(value, code):
    if not value:
        raise GuardError(code)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save_json(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode('utf8')).hexdigest()


def guard_identity(config):
    check(all(config.get(k) == v for k, v in EXPECTED.items()), 'SOURCE_IDENTITY_CHANGED')
    check(set(config.get('containers', {})) == {'app', 'gateway'}, 'SOURCE_SERVICE_SET_CHANGED')
    check(all(v.get('image') == IMAGE for v in config['containers'].values()), 'SOURCE_IMAGE_CHANGED')


def guard_target_port(port):
    check(type(port) is int and port == PORT, 'TARGET_PORT_CHANGED')


def guard_file_attributes(attributes, symlink):
    check(not symlink and not attributes & 0x400, 'SYMLINK_OR_REPARSE_REFUSED')


def plain_path(path):
    path = Path(path).absolute()
    check(not str(path).startswith(('\\\\', '//')), 'UNC_PATH_REFUSED')
    for entry in (path, *path.parents):
        if entry.exists() or entry.is_symlink():
            info = entry.lstat()
            guard_file_attributes(getattr(info, 'st_file_attributes', 0), stat.S_ISLNK(info.st_mode))
    return path


def guard_target_paths():
    final = plain_path(TARGET).resolve()
    check(final == TARGET.absolute() and final.parent == Path('D:/MediListen_离线归档').resolve(),
          'RESTORE_FINAL_PATH_CHANGED')
    protected = (SOURCE_RUNTIME, ONLINE_SOURCE, CANONICAL.parent,
                 Path('D:/MediListen_离线归档/candidate-doctor-negative-quality-d181aee6-20261027-r1'),
                 ROOT / '.artifacts/alpha51-offline-restore-r6-20260924/models/modelscope',
                 ROOT / '.artifacts/alpha51-demo-sprint-20260927/knowledge-hf')
    for source in protected:
        original = plain_path(source).resolve()
        check(not final.is_relative_to(original) and not original.is_relative_to(final),
              'RESTORE_SOURCE_OR_OLD_CANDIDATE_OVERLAP')
    check(not TARGET.exists(), 'RESTORE_TARGET_ALREADY_EXISTS')


def forbidden_copy_name(name):
    value = name.lower()
    return (value == '.env' or value.endswith(('.env', '.pem', '.key'))
            or 'credentials' in value or value in {'doctor-browser-profile', 'browser-profile',
                                                  'login.private.json', 'cookies.sqlite'})


def file_manifest(root):
    root = plain_path(root)
    check(root.is_dir(), 'REQUIRED_COPY_DIRECTORY_MISSING')
    result = {'directories': [], 'files': {}}
    for current, directories, files in os.walk(root, followlinks=False):
        directories.sort(); files.sort()
        for name in (*directories, *files):
            check(not forbidden_copy_name(name), 'CREDENTIAL_OR_BROWSER_COPY_REFUSED')
            path = Path(current) / name
            info = path.lstat()
            guard_file_attributes(getattr(info, 'st_file_attributes', 0), stat.S_ISLNK(info.st_mode))
            rel = path.relative_to(root).as_posix()
            if stat.S_ISDIR(info.st_mode):
                result['directories'].append(rel)
            else:
                check(stat.S_ISREG(info.st_mode), 'NON_REGULAR_COPY_REFUSED')
                result['files'][rel] = {'bytes': info.st_size, 'sha256': sha(path)}
    return result


def guard_equal_manifest(expected, actual):
    check(expected == actual, 'COPY_CONTENT_CHANGED')


def copy_checked(source, destination, expected):
    check(not Path(destination).exists(), 'COPY_DESTINATION_EXISTS')
    plain_path(destination)
    guard_equal_manifest(expected, file_manifest(source))
    shutil.copytree(source, destination, symlinks=True)
    guard_equal_manifest(expected, file_manifest(source))
    guard_equal_manifest(expected, file_manifest(destination))


def guard_patients(markers, policy):
    allowed = policy.get('synthetic_patient_ids')
    check(policy.get('confirmed_synthetic') is True and bool(policy.get('reviewed_by'))
          and isinstance(allowed, list) and bool(allowed)
          and len(allowed) == len(set(allowed))
          and all(isinstance(x, str) and re.fullmatch(r'SIM-TEST-[A-Z0-9-]+', x) for x in allowed),
          'SYNTHETIC_ALLOWLIST_INVALID')
    check(bool(markers) and all(isinstance(x, str) and x in allowed for x in markers),
          'PATIENT_OUTSIDE_REVIEWED_SIM_TEST_ALLOWLIST')


def db_fingerprints(path):
    """Only closed local backup/copy files may enter this function."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        check(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'BACKUP_INTEGRITY_FAILED')
        check(not db.execute('PRAGMA foreign_key_check').fetchall(), 'BACKUP_FOREIGN_KEYS_FAILED')
        schema = [list(row) for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        result = {'schema_sha256': digest_json(schema), 'tables': {}}
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            if table == 'auth_session':
                continue
            quoted = '"' + table.replace('"', '""') + '"'
            rows = sorted(json.dumps(list(row), ensure_ascii=False, default=lambda v: {'bytes': v.hex()},
                                     separators=(',', ':')) for row in db.execute('SELECT * FROM ' + quoted))
            result['tables'][table] = {'rows': len(rows), 'sha256': digest_json(rows)}
        return result


def prepare_database(sealed, working, policy):
    check(not Path(working).exists(), 'WORKING_DATABASE_EXISTS')
    with closing(sqlite3.connect(Path(sealed).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as src:
        tables = {row[0] for row in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        check({'patient', 'auth_user', 'auth_session'}.issubset(tables), 'AUTH_OR_PATIENT_SCHEMA_MISMATCH')
        guard_patients([row[0] for row in src.execute('SELECT deidentified_id FROM patient')], policy)
        columns = {row[1] for row in src.execute('PRAGMA table_info(auth_session)')}
        check({'id', 'token_hash'}.issubset(columns), 'AUTH_SESSION_SCHEMA_MISMATCH')
        patient_count = src.execute('SELECT COUNT(*) FROM patient').fetchone()[0]
        session_count = src.execute('SELECT COUNT(*) FROM auth_session').fetchone()[0]
        with closing(sqlite3.connect(working)) as dst:
            src.backup(dst)
            dst.execute('PRAGMA journal_mode=DELETE')
            dst.execute('DELETE FROM auth_session')
            dst.commit()
            dst.execute('VACUUM')
            check(dst.execute('SELECT COUNT(*) FROM auth_session').fetchone()[0] == 0, 'SESSION_CLEAR_FAILED')
    before = db_fingerprints(sealed)
    check(before == db_fingerprints(working), 'BUSINESS_OR_SCHEMA_CHANGED')
    return {'patient_count': patient_count, 'all_patients_reviewed_sim_test': True,
            'sessions_removed': session_count, 'business_fingerprints': before,
            'account_password_hashes': 'preserved locally; never emitted', 'schema_unchanged': True}


def run(args, *, input_text=None):
    try:
        result = subprocess.run(args, input=input_text, capture_output=True, text=True,
                                encoding='utf8', errors='replace', timeout=120,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GuardError('READ_OR_COPY_COMMAND_UNAVAILABLE') from error
    check(result.returncode == 0, 'READ_OR_COPY_COMMAND_FAILED')
    return result.stdout.strip()


def pilot_module():
    spec = importlib.util.spec_from_file_location('restore_pilot', ROOT / 'scripts/doctor_pilot.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def ledger_summary(path):
    ledger = read_json(path)
    check(isinstance(ledger.get('calls'), list) and not ledger.get('requires_reconciliation'),
          'LEDGER_RECONCILIATION_REQUIRED')
    return {'calls': len(ledger['calls']), 'sha256': sha(path),
            'cumulative_cost_and_budget': 'inherited byte-for-byte; no schema assumptions', 'budget_reset': False}


def make_compose(source, target, descriptor_source):
    expected = copy.deepcopy(source); expected.pop('name', None)
    expected['name'] = PROJECT
    for name, service in expected['services'].items():
        check(service['image'] == IMAGE and service.get('restart') == 'no', 'COMPOSE_IMAGE_OR_RESTART_CHANGED')
        for mount in service.get('volumes', []):
            replacement = {'/app/runtime': target / 'runtime', '/app/online-private': target / 'online-private',
                           '/app/static/deployment.json': target / 'deployment.json'}.get(mount['target'])
            if replacement is not None:
                mount['source'] = str(replacement)
        if name == 'app':
            service['environment']['MEDICAL_RECORD_AGENT_SESSION_COOKIE_NAME'] = COOKIE
        if name == 'gateway':
            check(len(service['ports']) == 1 and service['ports'][0]['host_ip'] == '127.0.0.1'
                  and service['ports'][0]['published'] == '8798', 'SOURCE_COMPOSE_PORT_CHANGED')
            service['ports'][0]['published'] = str(PORT)
    expected['networks'] = {n: {'internal': n == 'internal', 'ipam': {'config': [{'subnet': subnet}]}}
                            for n, subnet in SUBNETS.items()}
    descriptor = copy.deepcopy(read_json(descriptor_source))
    check(descriptor['version'] == EXPECTED['app_git_sha'], 'SOURCE_DESCRIPTOR_VERSION_CHANGED')
    descriptor['label'] = '同版恢复输入副本（未启动、未验收；DeepSeek生成需联网）'
    return expected, descriptor


def source_context():
    for path in (CANONICAL, COMPOSE_SOURCE, SOURCE_RUNTIME, ALLOWLIST, ONLINE_SOURCE, TARGET.parent):
        plain_path(path)
    guard_target_paths()
    config = read_json(CANONICAL); guard_identity(config)
    check(Path(config['runtime']).resolve() == SOURCE_RUNTIME.resolve(), 'SOURCE_RUNTIME_CHANGED')
    check(Path(config.get('viewer_allowlist', '')).resolve() == ALLOWLIST.resolve(), 'ALLOWLIST_SOURCE_CHANGED')
    policy = read_json(ALLOWLIST)
    guard_patients(policy.get('synthetic_patient_ids', []), policy)
    p = pilot_module(); items = p.validate(config)
    check(all(item['State']['Running'] for item in items.values()), 'SOURCE_NOT_RUNNING')
    check(all(item['Image'] == IMAGE for item in items.values()), 'SOURCE_IMAGE_CHANGED')
    environment = p.env(items['app'])
    for key, value in {'LLM_PROVIDER': 'online', 'ONLINE_LLM_MODEL': 'deepseek-flash',
                       'ONLINE_LLM_FIELD_CONTRACT': 'legacy', 'ONLINE_LLM_PROXY_URL': '',
                       'ONLINE_LLM_API_BASE': 'https://api.deepseek.com', 'LLM_MAX_RETRIES': '0'}.items():
        check(environment.get(key) == value, 'ONLINE_PROVIDER_CONTRACT_CHANGED')
    check(not environment.get('ONLINE_LLM_API_KEY'), 'INLINE_PROVIDER_CREDENTIAL_REFUSED')
    source = read_json(COMPOSE_SOURCE)
    check(set(source['services']) == {'app', 'gateway'}, 'COMPOSE_SERVICE_SET_CHANGED')
    for name, service in source['services'].items():
        check(service['image'] == IMAGE, 'SOURCE_COMPOSE_IMAGE_CHANGED')
        real = {m['Destination']: m for m in items[name]['Mounts']}
        mounts = {m['target']: m for m in service.get('volumes', [])}
        check(len(mounts) == len(service.get('volumes', [])) and set(mounts) == set(real), 'COMPOSE_MOUNT_SET_CHANGED')
        for destination, mount in mounts.items():
            check(mount['type'] == 'bind' and Path(mount['source']).resolve() == Path(real[destination]['Source']).resolve()
                  and (not mount.get('read_only', False)) == real[destination]['RW'], 'COMPOSE_MOUNT_CHANGED')
        if name == 'app':
            check(all(environment.get(k) == str(v) for k, v in service['environment'].items()), 'COMPOSE_ENVIRONMENT_CHANGED')
            for destination in (*KEY_TARGETS, *CACHE_TARGETS):
                mount = mounts[destination]
                check(mount.get('read_only') is True, 'KEY_OR_CACHE_NOT_READONLY')
                if destination in KEY_TARGETS:
                    check(Path(mount['source']).resolve() == KEY_SOURCE.resolve(), 'CREDENTIAL_PATH_CHANGED')
                else:
                    plain_path(mount['source'])
            check(Path(mounts['/app/online-private']['source']).resolve() == ONLINE_SOURCE.resolve(), 'ONLINE_PRIVATE_SOURCE_CHANGED')
    guard_target_port(PORT)
    with socket.socket() as probe:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'): probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind(('127.0.0.1', PORT))
    network_ids = run(['docker', 'network', 'ls', '-q']).split()
    nets = json.loads(run(['docker', 'network', 'inspect', *network_ids])) if network_ids else []
    allocated = [ipaddress.ip_network(v['Subnet']) for net in nets for v in (net.get('IPAM', {}).get('Config') or []) if v.get('Subnet')]
    check(not any(ipaddress.ip_network(s).version == n.version and ipaddress.ip_network(s).overlaps(n)
                  for s in SUBNETS.values() for n in allocated), 'RESTORE_SUBNET_OVERLAP')
    descriptor_path = next(Path(m['source']) for m in source['services']['app']['volumes'] if m['target'] == '/app/static/deployment.json')
    manifests = {name: file_manifest(SOURCE_RUNTIME / name) for name in COPY_DIRS}
    ledger = ledger_summary(ONLINE_SOURCE / 'cost-ledger.json')
    new_compose, descriptor = make_compose(source, TARGET, descriptor_path)
    fingerprints = {'canonical': sha(CANONICAL), 'compose': sha(COMPOSE_SOURCE), 'allowlist': sha(ALLOWLIST),
                    'descriptor': sha(descriptor_path)}
    return p, config, items, policy, manifests, ledger, fingerprints, new_compose, descriptor


# This code runs only in the source Linux writer's kernel. It emits hashes/counts,
# never rows. The same helper generates both sides of the sealed backup check.
DB_REMOTE = '''import sqlite3,json,hashlib,sys
from contextlib import closing
def dj(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def fp(db):
 assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
 assert not db.execute('PRAGMA foreign_key_check').fetchall()
 result={'schema_sha256':dj([list(r) for r in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]),'tables':{}}
 for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
  if t=='auth_session':continue
  rows=sorted(json.dumps(list(r),ensure_ascii=False,default=lambda v:{'bytes':v.hex()},separators=(',',':')) for r in db.execute('SELECT * FROM "'+t.replace('"','""')+'"'))
  result['tables'][t]={'rows':len(rows),'sha256':dj(rows)}
 return result
'''


def source_db_fingerprint(container):
    code = DB_REMOTE + "\nwith closing(sqlite3.connect('file:/app/runtime/medical_record_agent.sqlite3?mode=ro',uri=True)) as s:\n s.execute('BEGIN');print(json.dumps(fp(s)))\n"
    return json.loads(run(['docker', 'exec', '-i', container, 'python', '-'], input_text=code))


def prepare(idle_confirmed=False):
    check(idle_confirmed, 'IDLE_CONFIRMATION_REQUIRED')
    context = source_context()
    p, config = context[:2]
    with ExitStack() as locks:
        locks.enter_context(p.operation_lock(Path(config['switch_lock'])))
        locks.enter_context(p.operation_lock(CANONICAL))
        check(read_json(CANONICAL) == config, 'SOURCE_CHANGED_BEFORE_SNAPSHOT_LOCK')
        actual = p.validate(config)
        # This flag authorizes the server task/recording-session idle query.
        # It is not evidence of browser exit or saved client-side edits.
        p.assert_idle(config, actual, confirmed_saved=True)
        return prepare_locked(context, actual)


def prepare_locked(context, items):
    p, config, _, policy, manifests, ledger, inputs, compose, descriptor = context
    source_before = source_db_fingerprint(items['app']['Id'])
    guard_target_paths()
    TARGET.mkdir()  # Exclusive: existing or partially failed attempts are retained.
    (TARGET / 'sealed-private').mkdir(); (TARGET / 'runtime').mkdir()
    remote = '/tmp/mra-restore-inputs-' + uuid.uuid4().hex + '.sqlite3'
    code = DB_REMOTE + '''
import os
name=sys.argv[1]
fd=os.open(name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
with closing(sqlite3.connect('file:/app/runtime/medical_record_agent.sqlite3?mode=ro',uri=True)) as s:
 s.execute('BEGIN')
 source_snapshot=fp(s)
 with closing(sqlite3.connect(name)) as d:
  s.backup(d);assert d.execute('PRAGMA journal_mode=DELETE').fetchone()[0]=='delete'
  copied_snapshot=fp(d);assert source_snapshot==copied_snapshot;print(json.dumps(copied_snapshot))
'''
    backup_fp = json.loads(run(['docker', 'exec', '-i', items['app']['Id'], 'python', '-', remote], input_text=code))
    sealed = TARGET / 'sealed-private/source-backup.private.sqlite3'
    run(['docker', 'cp', items['app']['Id'] + ':' + remote, str(sealed)])
    check(source_before == backup_fp == db_fingerprints(sealed), 'SOURCE_CHANGED_DURING_BACKUP')
    database = prepare_database(sealed, TARGET / 'runtime/medical_record_agent.sqlite3', policy)
    for name, before in manifests.items(): copy_checked(SOURCE_RUNTIME / name, TARGET / 'runtime' / name, before)
    online = TARGET / 'online-private'; online.mkdir(); (online / 'business-diagnostics').mkdir()
    shutil.copy2(ONLINE_SOURCE / 'cost-ledger.json', online / 'cost-ledger.json')
    check(ledger_summary(online / 'cost-ledger.json') == ledger, 'LEDGER_COPY_CHANGED')
    save_json(TARGET / 'compose.private.json', compose)
    save_json(TARGET / 'deployment.json', descriptor)
    save_json(TARGET / 'file-manifest.private.json', manifests)
    p.validate(config)
    check(read_json(CANONICAL) == config and sha(CANONICAL) == inputs['canonical'], 'SOURCE_REGISTRATION_CHANGED')
    check(source_db_fingerprint(items['app']['Id']) == source_before, 'SOURCE_DATABASE_CHANGED')
    check(ledger_summary(ONLINE_SOURCE / 'cost-ledger.json') == ledger, 'ORIGINAL_LEDGER_CHANGED')
    for name, before in manifests.items(): guard_equal_manifest(before, file_manifest(SOURCE_RUNTIME / name))
    descriptor_source = next(Path(m['source']) for m in read_json(COMPOSE_SOURCE)['services']['app']['volumes']
                             if m['target'] == '/app/static/deployment.json')
    check(sha(COMPOSE_SOURCE) == inputs['compose'] and sha(ALLOWLIST) == inputs['allowlist']
          and sha(descriptor_source) == inputs['descriptor'], 'SOURCE_INPUT_CHANGED')
    summary = summarize('PREPARED_INPUTS_NOT_STARTED', config, manifests, ledger, inputs)
    summary.update(database=database, sealed_backup_sha256=sha(sealed),
                   source_business_and_schema_unchanged_excluding_auth_session=True,
                   fingerprint_excluded_tables=['auth_session'], original_ledger_unchanged=True,
                   source_container_tmp_backup_retained=remote, working_login_sessions_cleared=True,
                   server_task_and_recording_session_idle_observed=True,
                   browser_exit_and_unsaved_client_edits='NOT_OBSERVED',
                   canonical_and_environment_switch_locks_held=True)
    save_json(TARGET / 'prepare-summary.json', summary)
    return summary


def summarize(status, config, manifests, ledger, inputs):
    return {'status': status, 'source_environment': EXPECTED, 'image': IMAGE,
            'target': str(TARGET), 'target_project': PROJECT, 'target_port': PORT,
            'copy_allowlist': list(COPY_DIRS), 'patient_allowlist_source': str(ALLOWLIST),
            'file_groups': {name: {'files': len(value['files']), 'directories': len(value['directories']),
                                  'bytes': sum(v['bytes'] for v in value['files'].values()),
                                  'manifest_sha256': digest_json(value)} for name, value in manifests.items()},
            'source_fingerprints': inputs, 'ledger': ledger, 'new_model_calls': 0, 'new_asr_calls': 0,
            'container_create_start_stop_build_calls': 0, 'models_copied': False,
            'credential_contents_opened_or_hashed': False,
            'external_dependencies': ['Existing exact Docker image', 'Existing read-only ModelScope/HF caches',
                                      'Existing exact read-only credential file mounts',
                                      'Docker Desktop and Python; DeepSeek generation requires internet'],
            'boundaries': ['Inputs only; no service, readiness, UI or workflow acceptance',
                           'Private database/files/config must remain local; no upload',
                           'Shared read-only cache recovery is not self-contained offline delivery',
                           'Prepare retains source login/session and account originals in sealed local backup',
                           'Idle plus before/after DB and file equality covers this copy window; not an atomic filesystem snapshot',
                           'No database schema initialization/migration; working copy session removal only']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('dry-run', 'prepare'))
    parser.add_argument('--idle-confirmed', action='store_true',
                        help='Authorize server task/recording-session idle check only; does not assert browser exit or saved edits.')
    args = parser.parse_args()
    try:
        if args.action == 'prepare': result = prepare(args.idle_confirmed)
        else:
            _, config, _, _, manifests, ledger, inputs, _, _ = source_context()
            result = summarize('DRY_RUN_READ_ONLY_NO_BACKUP_OR_COPY', config, manifests, ledger, inputs)
            result['patient_database_gate'] = 'DEFERRED: all IDs checked only in sealed backup before working copy'
            result['original_ledger_unchanged'] = ledger_summary(ONLINE_SOURCE / 'cost-ledger.json') == ledger
            check(result['original_ledger_unchanged'], 'ORIGINAL_LEDGER_CHANGED')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except BaseException as error:
        code = str(error) if isinstance(error, GuardError) else type(error).__name__
        print(json.dumps({'status': 'FAIL_CLOSED', 'error_code': code, 'action': args.action,
                          'new_model_calls': 0, 'new_asr_calls': 0,
                          'failed_target_retained_if_created': True}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__': main()
