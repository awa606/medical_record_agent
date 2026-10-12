"""Self-contained v2 delivery; v1 archives remain handled by the legacy tool."""
from __future__ import annotations

import argparse
import base64
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
TABLES = ('patient', 'encounter', 'agent_task', 'record_revision', 'approval',
          'approval_item', 'export_event', 'knowledge_source', 'knowledge_document',
          'knowledge_chunk', 'knowledge_embedding')
MODEL_MANIFEST = Path('manifests/registry.ollama.ai/library/qwen3/4b')


def run(*args, cwd=None):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if p.returncode:
        raise RuntimeError(f'{args[0]} failed ({p.returncode}): {p.stderr[-800:]}')
    return p.stdout.strip()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def file_inventory(root):
    return {p.relative_to(root).as_posix(): {'sha256': sha(p), 'bytes': p.stat().st_size}
            for p in sorted(root.rglob('*')) if p.is_file()
            and p.relative_to(root).as_posix() not in {'manifest.json', 'sha256sums.txt'}}


def verify(package):
    package = Path(package).resolve(strict=True)
    m = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    if m.get('schema_version') != 'mra-offline-pilot-v2':
        raise ValueError('unsupported package version; use legacy tool for v1')
    for name in m['files']:
        p = (package / name).resolve()
        if not p.is_relative_to(package) or Path(name).is_absolute():
            raise ValueError('archive path escapes package')
    actual = file_inventory(package)
    if actual != m['files']:
        raise ValueError('archive file set / SHA256 / size mismatch')
    return m


def fingerprints(db):
    with closing(sqlite3.connect(f'file:{Path(db).as_posix()}?mode=ro', uri=True)) as c:
        return {t: {'rows': len(rows), 'sha256': hashlib.sha256(
                    json.dumps(rows, ensure_ascii=False, default=str).encode()).hexdigest()}
                for t in TABLES
                for rows in [[list(r) for r in c.execute(f'SELECT * FROM {t} ORDER BY rowid')]]}


def sanitize_database(source, target, allowlist):
    """Backup WAL consistently, preserve business IDs, remove all source credentials."""
    policy = json.loads(Path(allowlist).read_text(encoding='utf-8'))
    if policy.get('confirmed_synthetic') is not True or not policy.get('reviewed_by'):
        raise ValueError('reviewed synthetic allowlist required')
    with closing(sqlite3.connect(f'file:{Path(source).as_posix()}?mode=ro', uri=True)) as src:
        markers = {r[0] for r in src.execute('SELECT deidentified_id FROM patient')}
        if not markers or not markers.issubset(set(policy['synthetic_patient_ids'])):
            raise ValueError('source includes patients outside reviewed allowlist')
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
    before = fingerprints(target)
    with closing(sqlite3.connect(target)) as c:
        c.execute('DELETE FROM auth_session')
        users = list(c.execute('SELECT id,role FROM auth_user ORDER BY id'))
        for uid, role in users:
            c.execute('UPDATE auth_user SET username=?,display_name=?,password_hash=?,is_active=0,last_login_at=NULL WHERE id=?',
                      (f'pilot-{role}-{uid}', '试用管理员' if role == 'admin' else '试用医生',
                       'ARCHIVE_CREDENTIAL_DISABLED', uid))
        # Runtime probes and operational audit are not clinical history.
        for table in ('audit_log', 'knowledge_admin_audit', 'runtime_readiness_probe'):
            if c.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                c.execute(f'DELETE FROM {table}')
        c.commit()
        c.execute('VACUUM')  # removed login data must not remain in free pages
        if c.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or c.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('sanitized database integrity failed')
        if c.execute('SELECT COUNT(*) FROM auth_session').fetchone()[0]:
            raise ValueError('sessions remain')
    if fingerprints(target) != before:
        raise ValueError('business or knowledge history changed during sanitization')
    return before


def restore_credentials(db, private_file):
    # Keep original owner IDs; never reuse the original password hash or session.
    credentials = []
    with closing(sqlite3.connect(db)) as c:
        c.execute('DELETE FROM auth_session')
        for uid, username, role in c.execute('SELECT id,username,role FROM auth_user ORDER BY id').fetchall():
            password = secrets.token_urlsafe(20)
            salt = secrets.token_bytes(16)
            digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 120000)
            encoded = '$'.join(('pbkdf2_sha256', '120000', base64.b64encode(salt).decode(), base64.b64encode(digest).decode()))
            c.execute('UPDATE auth_user SET password_hash=?,is_active=1 WHERE id=?', (encoded, uid))
            credentials.append({'id': uid, 'username': username, 'password': password, 'role': role})
        c.commit()
    write_json(private_file, credentials)
    return credentials


def free_port(port):
    if not 1024 <= port <= 65535:
        raise ValueError('invalid port')
    with socket.socket() as s:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(('127.0.0.1', port))


def choose_port(candidates):
    for port in candidates:
        try:
            free_port(port)
            return port
        except OSError:
            pass
    raise ValueError('ports unavailable; other services retained')


def assert_models_idle(project):
    items = [json.loads(line) for line in run('docker', 'ps', '--format', '{{json .}}').splitlines()]
    for item in items:
        if 'ollama' in item['Names'].lower() and not item['Names'].startswith(project + '-'):
            raise ValueError('another model environment is running; save/exit and switch explicitly')


def merge_runtime_environment(compose, values):
    """Replace existing fixed keys instead of creating duplicate YAML mappings."""
    extra = '      MEDICAL_RECORD_AGENT_AUTH_COOKIE_NAME: mra_offline_pilot\n'
    for key, value in sorted(values.items()):
        pattern = re.compile(r'^      ' + re.escape(key) + r':.*$', re.MULTILINE)
        line = f'      {key}: {json.dumps(str(value))}'
        if pattern.search(compose):
            compose = pattern.sub(lambda _: line, compose)
        else:
            extra += line + '\n'
    return compose.replace('      PYTHONPATH: /app\n', '      PYTHONPATH: /app\n' + extra)


def create(args):
    from alpha51_release_archive import COMPOSE
    package = args.package.resolve()
    if package.exists():
        raise ValueError('refusing to overwrite archive')
    if run('git', 'status', '--porcelain', cwd=ROOT):
        raise ValueError('commit delivery tooling before packaging')
    source_sha = run('git', 'rev-parse', args.source_ref, cwd=ROOT)
    tool_sha = run('git', 'rev-parse', 'HEAD', cwd=ROOT)
    for path in (args.runtime, args.modelscope, args.ollama_models, args.hf_cache, args.wheelhouse):
        if package.is_relative_to(path.resolve()) or not path.is_dir():
            raise ValueError('invalid or nested source directory')
    model_manifest = args.ollama_models / MODEL_MANIFEST
    model = json.loads(model_manifest.read_text(encoding='utf-8'))
    for layer in [model['config'], *model['layers']]:
        p = args.ollama_models / 'blobs' / layer['digest'].replace(':', '-')
        if p.stat().st_size != layer['size'] or sha(p) != layer['digest'].split(':')[1]:
            raise ValueError('model blob corrupt')
    if not list(args.hf_cache.rglob('*.safetensors')):
        raise ValueError('knowledge model cache missing')
    if not list(args.wheelhouse.glob('datasette-0.65.5-*.whl')):
        raise ValueError('offline viewer dependency missing')
    package.mkdir(parents=True)
    for name, source in [('ollama', args.ollama_models), ('modelscope', args.modelscope), ('hf', args.hf_cache)]:
        print('复制独立缓存：' + name, flush=True)
        shutil.copytree(source, package / 'models' / name, symlinks=False)
    data = package / 'runtime-template'
    data.mkdir()
    history = sanitize_database(args.database, data / 'medical_record_agent.sqlite3', args.allowlist)
    shutil.copy2(args.allowlist, package / 'synthetic-allowlist.json')
    approved_audio = sha(args.authorized_audio)
    copied = []
    audio_ids = set()
    # Only audio whose pixels/samples exactly match the authorized input is copied.
    for audio in sorted((args.runtime / 'uploads').glob('*.wav')):
        if sha(audio) != approved_audio:
            continue
        audio_ids.add(audio.stem)
        for related in (audio, audio.with_suffix('.record.json'), audio.with_suffix('.transcript.json')):
            if related.is_file():
                dest = data / 'uploads' / related.name
                dest.parent.mkdir(exist_ok=True)
                shutil.copy2(related, dest)
                copied.append(dest.relative_to(data).as_posix())
    for session in (args.runtime / 'uploads' / 'asr_sessions').glob('*/session.json'):
        info = json.loads(session.read_text(encoding='utf-8'))
        if info.get('audio_id') not in audio_ids:
            continue
        for name in ('session.json', 'result.json', 'events.jsonl'):
            p = session.parent / name
            if p.is_file():
                dest = data / 'uploads' / 'asr_sessions' / session.parent.name / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
                copied.append(dest.relative_to(data).as_posix())
    # Historical approved exports are retained for selected synthetic tasks.
    with closing(sqlite3.connect(data / 'medical_record_agent.sqlite3')) as c:
        task_ids = {r[0] for r in c.execute('SELECT id FROM agent_task')}
    for p in (args.runtime / 'outputs').glob('task_*_medical_record.*'):
        if int(p.name.split('_')[1]) in task_ids:
            dest = data / 'outputs' / p.name
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(p, dest)
            copied.append(dest.relative_to(data).as_posix())
    (package / 'inputs').mkdir()
    shutil.copy2(args.authorized_audio, package / 'inputs' / 'authorized_fever_60s.wav')
    (package / 'source').mkdir()
    source_zip = package / 'source' / 'application.zip'
    run('git', 'archive', '--format=zip', '-o', str(source_zip), source_sha, cwd=ROOT)
    run('git', 'bundle', 'create', str(package / 'source' / 'history.bundle'), '--all', cwd=ROOT)
    for name in ('offline_pilot_archive.py', 'alpha51_release_archive.py', 'alpha51_gateway.py', 'data_browser.py', 'Start-MRADataBrowser.ps1'):
        dest = package / 'scripts' / name
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(ROOT / 'scripts' / name, dest)
    shutil.copytree(ROOT / 'tools' / 'data-browser', package / 'tools' / 'data-browser')
    shutil.copytree(args.wheelhouse, package / 'wheelhouse')
    shutil.copytree(args.handbook, package / 'handbook')
    license_inventory = []
    for card in sorted((package / 'models').rglob('*')):
        if card.is_file() and (card.name.lower().startswith('license') or card.name.lower() == 'readme.md'):
            body = card.read_text(encoding='utf-8', errors='replace')
            declared = next((line.split(':', 1)[1].strip() for line in body.splitlines()
                             if line.lower().startswith('license:')), 'see full card/license')
            license_inventory.append({'path': card.relative_to(package).as_posix(), 'sha256': sha(card), 'declaration': declared})
    # Ollama's model license is a content-addressed layer, not a named LICENSE file.
    for layer in model['layers']:
        if 'license' in layer.get('mediaType', '').lower():
            license_inventory.append({'path': 'models/ollama/blobs/' + layer['digest'].replace(':', '-'),
                                      'sha256': layer['digest'].split(':')[1], 'declaration': 'complete Ollama license layer'})
    write_json(package / 'model-licenses.json', license_inventory)
    evidence = package / 'evidence'
    evidence.mkdir()
    for p in args.evidence:
        shutil.copy2(p, evidence / p.name)
    env = json.loads(args.environment.read_text(encoding='utf-8'))
    # Explicit runtime-only whitelist; no passwords, host URLs or host paths accepted.
    permitted = {'KNOWLEDGE_STORE_MODE', 'KNOWLEDGE_RETRIEVAL_MODE', 'KNOWLEDGE_EMBEDDING_MODEL',
                 'KNOWLEDGE_ALLOW_DOWNLOAD', 'OLLAMA_MODEL_DIGEST', 'LLM_TEMPERATURE',
                 'LLM_NUM_CTX', 'LLM_NUM_PREDICT', 'OLLAMA_KEEP_ALIVE', 'FUNASR_DEVICE'}
    safe_env = {k: str(v) for k, v in env.items() if k in permitted}
    compose = COMPOSE.replace('mra-alpha-demo-m4-rc1:candidate', args.app_image).replace('ollama/ollama:0.34.0', args.ollama_image)
    compose = compose.replace('./tools/gateway.py', './scripts/alpha51_gateway.py')
    compose = compose.replace('./models/ollama:/root/.ollama/models', './models/ollama:/root/.ollama/models:ro')
    compose = compose.replace('./models/modelscope:/app/model_cache/modelscope', './models/modelscope:/app/model_cache/modelscope:ro')
    compose = compose.replace('./models/hf:/app/model_cache/hf', './models/hf:/app/model_cache/hf:ro')
    compose = compose.replace('    depends_on: [ollama]', '    pull_policy: never\n    depends_on: [ollama]')
    compose = compose.replace('    gpus: all', '    pull_policy: never\n    gpus: all')
    compose = compose.replace('    depends_on: [app]', '    pull_policy: never\n    depends_on: [app]')
    compose = merge_runtime_environment(compose, safe_env)
    (package / 'compose.offline.yml').write_text(compose, encoding='utf-8')
    for action in ('start', 'stop', 'open', 'help', 'viewer'):
        (package / f'{action}.cmd').write_text(
            f'@echo off\r\ncd /d "%~dp0"\r\npython -X utf8 scripts\\offline_pilot_archive.py {action} --target "%~dp0"\r\nif errorlevel 1 pause\r\n', encoding='ascii')
    (package / 'restore.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\npython -X utf8 scripts\\offline_pilot_archive.py restore --package "%~dp0" --target "%~dp0..\\MediListen_restore_%RANDOM%"\r\npause\r\n', encoding='ascii')
    (package / '使用与恢复说明.md').write_text(RUNBOOK, encoding='utf-8')
    images = {}
    (package / 'images').mkdir()
    for label, name in [('app', args.app_image), ('ollama', args.ollama_image)]:
        images[label] = {'name': name, 'id': run('docker', 'image', 'inspect', name, '--format', '{{.Id}}')}
        print('导出固定镜像：' + label, flush=True)
        run('docker', 'image', 'save', '-o', str(package / 'images' / f'{label}.tar'), name)
    files = file_inventory(package)
    manifest = {'schema_version': 'mra-offline-pilot-v2', 'release_id': package.name,
                'status': 'CANDIDATE_NOT_RELEASED', 'created_at': datetime.now(timezone.utc).isoformat(),
                'application_sha': source_sha, 'delivery_tool_sha': tool_sha, 'images': images,
                'ollama_model': 'qwen3:4b', 'ollama_manifest_sha256': sha(model_manifest),
                'history_fingerprints': history, 'files': files,
                'runtime_files': copied, 'authorized_audio_sha256': approved_audio,
                'credentials': 'removed; disabled owner placeholders; fresh credentials at restore',
                'cache_policy': 'independent full copies; no source host paths',
                'remaining_gates': ['physical microphone', 'actual display zoom', '5.3 continuous 5 audio flows']}
    write_json(package / 'manifest.json', manifest)
    (package / 'sha256sums.txt').write_text(''.join(f'{v["sha256"]}  {k}\n' for k, v in files.items()), encoding='utf-8')
    verify(package)
    print(json.dumps({'package': str(package), 'files': len(files), 'bytes': sum(v['bytes'] for v in files.values()), 'app_sha': source_sha}, ensure_ascii=False))


def compose_command(target, state):
    return ('docker', 'compose', '-p', state['project'], '-f', str(target / 'compose.offline.yml'))


def start(target):
    state = json.loads((target / 'restore.private.json').read_text(encoding='utf-8'))
    project = state['project']
    assert_models_idle(project)
    running = run('docker', 'ps', '--filter', f'label=com.docker.compose.project={project}', '--format', '{{.Names}}')
    if not running:
        free_port(state['port'])
    run(*compose_command(target, state), 'up', '-d', '--no-build', '--pull', 'never', cwd=target)
    print(f'医生入口：http://127.0.0.1:{state["port"]}/static/doctor.html（模型预热期间禁止生成）')


def restore(args):
    m = verify(args.package)
    target = args.target.resolve()
    if target.exists() or target.is_relative_to(args.package.resolve()):
        raise ValueError('restore needs a NEW directory outside package')
    port = args.port or choose_port((18999, 19000))
    free_port(port)
    viewer_port = args.viewer_port or choose_port((18997, 19001))
    free_port(viewer_port)
    assert_models_idle(f'mraoffline{port}')
    shutil.copytree(args.package, target)
    shutil.copytree(target / 'runtime-template', target / 'runtime')
    credentials = restore_credentials(target / 'runtime' / 'medical_record_agent.sqlite3', target / 'credentials.private.json')
    state = {'project': f'mraoffline{port}', 'port': port, 'viewer_port': viewer_port,
             'app_sha': m['application_sha'], 'package': str(args.package.resolve())}
    write_json(target / 'restore.private.json', state)
    admin = next(u for u in credentials if u['role'] == 'admin')
    (target / '.env').write_text(f'MRA_PORT={port}\nMRA_BOOTSTRAP_PASSWORD={admin["password"]}\n', encoding='utf-8')
    for label in ('app', 'ollama'):
        run('docker', 'image', 'load', '-i', str(target / 'images' / f'{label}.tar'))
        if run('docker', 'image', 'inspect', m['images'][label]['name'], '--format', '{{.Id}}') != m['images'][label]['id']:
            raise ValueError('loaded image ID mismatch')
    run(sys.executable, '-m', 'venv', str(target / 'viewer-venv'))
    py = target / 'viewer-venv' / 'Scripts' / 'python.exe'
    if not py.exists():
        py = target / 'viewer-venv' / 'bin' / 'python'
    installed = run(str(py), '-m', 'pip', 'install', '--no-index', '--find-links', str(target / 'wheelhouse'),
                    '-r', str(target / 'tools' / 'data-browser' / 'requirements-lock.txt'))
    (target / 'viewer-install.log').write_text(installed, encoding='utf-8')
    run('docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'chown', '-u', '0:0',
        '-v', f'{target / "runtime"}:/data', m['images']['app']['name'], '-R', '999:999', '/data')
    start(target)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(f'http://127.0.0.1:{port}/ready', timeout=10) as r:
                if r.status == 200:
                    print('离线恢复依赖就绪；须继续执行真实工作流验收。')
                    return
        except OSError:
            pass
        time.sleep(5)
    raise ValueError('readiness timed out; keep failed replica and inspect logs')


def viewer(target):
    state = json.loads((target / 'restore.private.json').read_text(encoding='utf-8'))
    py = target / 'viewer-venv' / 'Scripts' / 'python.exe'
    run('powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(target / 'scripts' / 'Start-MRADataBrowser.ps1'),
        '-Action', 'Start', '-SourceDb', str(target / 'runtime' / 'medical_record_agent.sqlite3'),
        '-SourceLabel', f'离线恢复 {state["app_sha"][:8]}', '-PythonPath', str(py),
        '-StateDirectory', str(target / 'viewer-state'), '-AllowlistPath', str(target / 'synthetic-allowlist.json'),
        '-Port', str(state['viewer_port']))
    print(f'数据与知识查看器：http://127.0.0.1:{state["viewer_port"]}/（从本包授权入口打开）')


def stop(target):
    state = json.loads((target / 'restore.private.json').read_text(encoding='utf-8'))
    with closing(sqlite3.connect(f'file:{(target / "runtime" / "medical_record_agent.sqlite3").as_posix()}?mode=ro', uri=True)) as c:
        active = c.execute("SELECT COUNT(*) FROM agent_task WHERE status IN ('CREATED','ASR_RUNNING','LLM_RUNNING','GENERATING','PROCESSING')").fetchone()[0]
        if active:
            raise ValueError('generation is active; stop refused, finish it in the page first')
    if (target / 'viewer-state' / 'state.private.json').exists():
        run('powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(target / 'scripts' / 'Start-MRADataBrowser.ps1'),
            '-Action', 'Stop', '-PythonPath', str(target / 'viewer-venv' / 'Scripts' / 'python.exe'), '-StateDirectory', str(target / 'viewer-state'))
    run(*compose_command(target, state), 'stop', cwd=target)
    print('本恢复副本已停止，数据及镜像保留。')


RUNBOOK = '''# MediListen完整离线恢复候选

这是固定审核流程的交付候选，不是已完成临床验证的医院产品。模型错误仍需医生核对；物理麦克风、实际缩放、连续五次真实流程未完成前不得称稳定发布。

## 恢复

适用当前Windows开发机，已安装Docker Desktop、Python 3.11、Edge及可用NVIDIA驱动。无需联网下载，不在其他平台作通过声明。先保存并退出原应用，停止原模型环境；脚本拒绝同时运行另一Ollama。

双击 `restore.cmd`，或指定一个新的空目录：

```powershell
python -X utf8 scripts/offline_pilot_archive.py restore --package . --target D:/MediListen_恢复副本/新目录
```

默认医生端18999（占用改19000），查看器18997（占用改19001）。脚本不会停止其他占用端口的程序。核对完成后复制文件、加载固定镜像、从本包wheel安装全新查看器，并预热真实模型；没有构建或拉取镜像。

## 使用与停止

在恢复目录双击 `start.cmd` 启动、`open.cmd` 打开医生网页、`viewer.cmd` 启动数据查看器、`help.cmd` 查看帮助、`stop.cmd` 停止本副本。登录信息只在恢复时生成，保存在该目录的 `credentials.private.json`，请勿分享此文件。查看器授权入口保存在 `viewer-state` 对应快照中的 `login.private.json`；这是本机一次性授权，不是病历质量认证。

医生主线：登记报到→开始接诊→录音/上传/文本→原文与指南核对→医生修正→保存新版本→分项审核→批准导出→历史重开。帮助内嵌入口和 `handbook/manual.html` 均属于本版本；历史截图保留其原版本标识。

## 验证与回退

`manifest.json`记录应用SHA、交付工具SHA、镜像ID、模型摘要及文件大小；`sha256sums.txt`为完整校验清单。恢复前脚本校验实际文件集合；篡改、缺模型、端口占用会拒绝。恢复结果写在副本内，不能改包内原始清单。

恢复副本停止后，按原8798启动入口恢复原环境。此包不修改原库、原模型或8795展示版，不删除旧归档。

若出现错误：保留副本和日志，记录失败模块、输入编号、预期/实际、影响、证据和下一最小验证。/health只证明网页进程，/ready才表示真实依赖通过就绪检查，均不等于模型医学判断正确。
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    c = sub.add_parser('create-current')
    for name in ('package', 'database', 'runtime', 'allowlist', 'modelscope', 'ollama-models', 'hf-cache', 'wheelhouse', 'handbook', 'authorized-audio', 'environment'):
        c.add_argument('--' + name, type=Path, required=True)
    c.add_argument('--source-ref', required=True)
    c.add_argument('--app-image', required=True)
    c.add_argument('--ollama-image', required=True)
    c.add_argument('--evidence', type=Path, nargs='+', default=[])
    r = sub.add_parser('restore')
    r.add_argument('--package', type=Path, required=True)
    r.add_argument('--target', type=Path, required=True)
    r.add_argument('--port', type=int, default=0)
    r.add_argument('--viewer-port', type=int, default=0)
    r.add_argument('--timeout', type=int, default=600)
    v = sub.add_parser('verify')
    v.add_argument('--package', type=Path, required=True)
    for name in ('start', 'stop', 'open', 'help', 'viewer'):
        sub.add_parser(name).add_argument('--target', type=Path, required=True)
    a = p.parse_args()
    if a.action == 'create-current':
        create(a)
    elif a.action == 'restore':
        restore(a)
    elif a.action == 'verify':
        verify(a.package)
        print('完整校验通过')
    elif a.action in ('start', 'stop', 'viewer'):
        globals()[a.action](a.target.resolve())
    else:
        import webbrowser
        state = json.loads((a.target / 'restore.private.json').read_text(encoding='utf-8'))
        page = '/static/help/index.html' if a.action == 'help' else '/static/doctor.html'
        webbrowser.open(f'http://127.0.0.1:{state["port"]}{page}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('交付操作失败：' + str(exc), file=sys.stderr)
        sys.exit(1)
