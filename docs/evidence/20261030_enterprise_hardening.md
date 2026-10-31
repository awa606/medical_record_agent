# 2026-10-30 企业级加固第一批：授权边界、脱敏默认、科室维度、审计链、指标与恢复校验

## 结论与版本

- 开发分支：`codex/enterprise-hardening-20261030`（独立工作树 `病历/07_HARDENING_WORK/mra_enterprise_hardening`），基线 `baa06e5`（`codex/alpha51-demo-visual-e2e`）。
- 本轮**未部署、未提交、未推送**；8798 运行入口与镜像未启停，原前端 `13762490` / 后端 `1cafa2a` 不受影响。
- 变更性质：代码级加固，不新增医生页面、不改模型与提示词、不改 WBS 任务、日期或 Gate。

## 动机（2026-10-30 审计结论）

只读审计确认六个可代码修复的缺口：授权检查在缺少身份时静默放行；外部 Provider 脱敏默认关闭；`department_id` 只存在于用户表、资源侧无科室维度且 API 层从未回填；审计仅落普通表、无篡改检出；无指标端点；备份脚本无恢复校验。本轮逐项处理，并按独立复核意见修正了三处实现缺陷。

## 变更清单

| # | 变更 | 文件 | 行为 |
|---|---|---|---|
| 1 | 授权 fail-closed（HTTP 边界） | `app/api/auth.py`、`app/api/encounters.py` | `assert_owner_or_admin` 在 `request` 存在但无用户时返回 401，不再静默放行；`request is None` 仅表示直接函数调用（无 HTTP 边界），保持内部语义。encounter 访问对 `intake/frontdesk` 同科室放行，其余仍走属主/管理员校验 |
| 2 | 脱敏默认随外部通道 | `app/services/privacy.py`、`app/services/llm/factory.py` | `enabled()` 显式开关优先，否则 `LLM_PROVIDER=online` 默认开启、edge 模式开启；构造 `OnlineLLMProvider` 时校验，显式 `MRA_ANONYMIZE=0` 抛 `ONLINE_ANONYMIZATION_REQUIRED`，仅 `MRA_ALLOW_UNREDACTED_OUTBOUND=1` 可显式接受风险 |
| 3 | 科室维度落地 | `app/db/sqlite.py`、`app/api/encounters.py`、`app/api/auth.py` | `patient`/`encounter` 新增 `department_id`（迁移 + 索引）；建单继承用户科室并回填旧患者空科室；科室岗位列表按「本科室单据 + 本科室医生的历史 NULL 单据」过滤；历史 NULL 单据的详情同样按 owning doctor 的科室判定；`_public_user` 与 `list_users` 补齐 `department_id` |
| 4 | 审计哈希链 | `app/db/sqlite.py` | 新表 `audit_chain`（`prev_hash`/`entry_hash`/`key_id`）；**所有** `audit_log` 写入（含 `doctor_review_saved`、`failed_task_replaced`）在同一事务内追加链节；登录/登出写链；`verify_audit_chain()` 重算全链，区分 `prev_hash_mismatch` 与 `hash_mismatch`；支持 `MRA_AUDIT_HMAC_KEY`，密钥缺失时明确报 `missing_hmac_key` |
| 5 | 审计查询接口 | `app/api/security.py` | `GET /api/security/audit-chain`（校验结果 + 最近 N 条）、`GET /api/security/audit-chain/verify`，仅管理员 |
| 6 | 指标端点 | `app/api/runtime.py` | `GET /metrics`，Prometheus 文本格式，只输出聚合计数、库大小与链有效性；管理员会话或 `MRA_METRICS_TOKEN` Bearer 可访问；Bearer 比较改为字节常量时间比较，非 ASCII 头干净拒绝 |
| 7 | 恢复校验与治理文档 | `scripts/edge_sqlite_backup.py`、`docs/repository_governance.md` | `restore` 先校验备份完整性、可选 `--require-tables` 防止选错备份、保留 `.pre-restore-*`（微秒时间戳）回滚副本、恢复后比对逐表行数并清理 `-wal/-shm`；新增 `verify` 子命令与干净错误输出；治理文档从乱码重写为可执行规则 |
| 8 | 付费探测需登录 | `app/api/llm.py` | `POST /api/llm/test` 要求已登录用户；匿名请求不能触发外部 Provider 探测。`GET /status` 保持只读公开（前端状态展示依赖） |
| 9 | 预热接口限管理员 | `app/api/asr_prewarm.py` | `POST /api/asr/prewarm/start` 仅管理员；避免匿名触发模型加载导致 CPU/内存占满。`GET /status` 保持只读公开 |
| 10 | 前台写入边界 | `app/api/encounters.py` | `intake/frontdesk` 可 `check-in`/`cancel`，`start`/`complete` 仅属主医生或管理员，避免前台把就诊置为 completed 阻断医生出单 |

## 验证

| 项目 | 结果 | 说明 |
|---|---|---|
| 新增测试 `tests/test_enterprise_hardening.py` | **28 passed** | 覆盖 HTTP 边界 401、属主/管理员/越权 403、科室存储与过滤、历史 NULL 单据的跨科室隔离、前台写入边界、审计链篡改与断链检出、HMAC 缺钥、低层审计写入入链、指标鉴权与非 ASCII 头、恢复回滚副本/损坏备份/必需表校验、并发首次建库 |
| `tests/test_asr_prewarm.py` | **4 passed** | 新增匿名启动预热 401；管理员通过依赖覆盖验证原行为不变 |
| 定向回归（9 个受影响模块） | **100 passed** | encounters / encounter_workflow / tasks / records / review_revision_transaction / partial_draft_review / asr_prewarm / auth / 新增 |
| 全量 `pytest -m "not browser"` | **1534 passed, 51 failed, 5 skipped, 31 errors** | 与同基线干净工作树对比：基线 1507 passed / 50 failed / 31 errors。失败集合逐条一致（50 项环境性浏览器缺失）；另 1 项 `test_deepseek_demo_spike::test_over_budget_is_rejected_before_http_and_exact_20_cny` 为既有 Windows 临时账本抖动，单跑 **1 passed** |
| 失败原因 | 环境 | 全部为 Playwright 浏览器未安装（宿主机无浏览器运行时），不是本轮回归 |
| 静态检查 | 通过 | `compileall` + `import app.main` 成功 |

复现：

```powershell
$py = "...\medical_record_agent\.venv\Scripts\python.exe"
$env:PYTHONPATH = "...\07_HARDENING_WORK\mra_enterprise_hardening"
& $py -m pytest tests/test_enterprise_hardening.py -q
& $py -m pytest -q -m "not browser"
```

## 独立复核与处置

复核由未参与实现的检查者执行（框架 + 功能两角色，只读并实际跑测试），结论与处置：

| 复核发现 | 处置 |
|---|---|
| 历史 NULL 科室单据对所有科室前台可见（含患者显示名） | 已修：列表与详情都按 owning doctor 的科室判定，新增跨科室断言 |
| `doctor_review_saved`、`failed_task_replaced` 未入链 | 已修：`_insert_audit_log_row` 统一写链，原始直插改为该函数 |
| 并发首次 `init_db` 可能 `duplicate column name` 500 | 已修：`_ensure_column` 把该错误视为迁移成功；新增 6 线程并发建库测试 |
| 前台可 `start/complete` 他人就诊 | 已修：`start/complete` 仅属主/管理员，前台保留 `check-in/cancel` |
| `/metrics` 非 ASCII Bearer 触发 500 | 已修：改字节比较，新增 ASGI 层断言 |
| 链断裂诊断 `expected_hash == stored_hash` 自相矛盾 | 已修：新增 `prev_hash_mismatch` 并输出 `expected_prev_hash`/`stored_prev_hash` |
| `restore` 行数比对无法发现选错备份；回滚副本同秒覆盖 | 已修：新增 `--require-tables`；回滚副本时间戳到微秒 |
| 复核指出的证据文档数字与口径错误 | 已订正：28 项新增、失败集合逐条一致、NULL 语义与链截断限制如实描述 |

## 边界与未完成

1. **未接医院身份**：无 OIDC/SAML/LDAP、无 MFA、无账号生命周期和登录限流；本轮只把授权边界改成 fail-closed 并补科室维度。
2. **科室语义是兼容式**：历史 `department_id IS NULL` 的行按 owning doctor 的科室归属判定；跨科室不可见，但这不是完整多租户隔离，需在 E2 设计里定稿。
3. **审计链为单机链式校验**：中间行被改/删可检出；**尾部截断或整表清空不可检出**（链头无外部锚定）。无 WORM、无异地汇聚、无签名证书；「定期记录链头哈希」目前只是运维约定，仓库未提供锚定命令或锚定表。
4. **指标只覆盖聚合计数**，无请求时延、错误率、模型调用成本与告警规则。
5. **未做真实浏览器 E2E**：本轮为后端与接口级验证，界面未改，视觉基线可复用。
6. **未部署**：需要构建候选镜像，在隔离端口跑通审批→导出→恢复，再决定是否推广到 8798。
7. **迁移竞态的兜底不等于无锁迁移**：并发首次建库不再报错，但迁移仍不是版本化迁移链（无 Alembic）。

## 风险与回滚

- 脱敏默认变更会改变响应文本（别名化），对依赖原文的脚本有影响；显式 `MRA_ANONYMIZE=0` 可恢复旧行为，但会触发在线 Provider 拒绝，需再用 `MRA_ALLOW_UNREDACTED_OUTBOUND=1`。
- 审计链写入与业务写入同库同事务；链表增长按业务量线性，当前规模可忽略。
- 前台写权限收窄可能改变现有演示脚本（若脚本用前台账号 start/complete）；本轮测试已覆盖医生路径。
- 回滚：`git checkout baa06e5 -- <文件>` 或弃用本工作树；数据库仅新增表与可空列，无需回滚。

## 复用与未重跑

- V02 角色门禁、V03 医生审核、V04 未审核导出保护、V11 证据版本链未受影响，沿用原证据（2026-09-19 至 2026-09-22，源码 SHA 见各 Verification 笔记），本轮未重跑真实按钮流程。
- 模型首次质量、ASR 角色准确性、5.3 连续五次均不在本轮范围。
