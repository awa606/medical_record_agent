# Medical Record Agent Edge Pilot RC1 验收记录

定位：单机 SQLite、受控局域网、门诊试点候选版。

## 运行门禁

- `/live`：进程存活检查。
- `/ready`：检查 SQLite 可写、WAL、上传目录、导出目录、声纹目录、磁盘空间和 Provider 配置。
- Docker healthcheck 使用 `/ready`。
- Docker 容器内应用进程使用非 root 用户运行。

## 安全限制

- 音频上传大小由 `MEDICAL_RECORD_AGENT_MAX_UPLOAD_BYTES` 控制。
- 浏览器录音 chunk 大小由 `MEDICAL_RECORD_AGENT_MAX_RECORDING_CHUNK_BYTES` 控制。
- 浏览器录音总时长由 `MEDICAL_RECORD_AGENT_MAX_RECORDING_SECONDS` 控制，默认 1800 秒。
- Live/Edge 模式下 `/ready` 会阻断 Mock Provider 或不可用 Provider。

## 数据保护

- SQLite 启用 WAL。
- 备份：`python scripts/edge_sqlite_backup.py backup --db data/medical_record_agent.sqlite3 --output backup.sqlite3`
- 恢复：`python scripts/edge_sqlite_backup.py restore --backup backup.sqlite3 --db data/medical_record_agent.sqlite3 --force`

## RC1 验收命令

```bash
pytest -q
node --check static/doctor.js
git diff --check
```

本 PR 不创建正式 Release；需等待认证/RBAC、审批版本、工作列表、录音 V2、运行加固全部合并且临床 E2E hard gate 仍通过后，再进入 RC1 发布候选。
