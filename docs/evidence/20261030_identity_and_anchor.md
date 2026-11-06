# 2026-10-30 企业级加固第二批：登录限速、账号生命周期、审计锚定

## 结论与版本

- 分支：`codex/enterprise-hardening-20261030`（同一工作树），基线 `baa06e5`。
- 本批延续第一批（授权边界、脱敏默认、科室维度、审计链、指标、恢复校验），新增身份与审计锚定能力，并修复独立复核发现的一处阻断缺陷。**未部署、未提交、未推送**，8798 未动。
- 不改模型、提示词、WBS 任务或 Gate。

## 变更清单

| # | 变更 | 文件 | 行为 |
|---|---|---|---|
| 1 | 登录失败限速 | `app/db/sqlite.py`、`app/api/auth.py` | 新表 `auth_login_attempt`（`username + client_ip` 主键）；15 分钟窗口 5 次失败后，**错误口令**返回 429 + `Retry-After`；**正确口令仍可登录**并清零计数，避免攻击者把医生锁在门外；失败记录保留 1 天后自动清理 |
| 2 | 登录时序对齐 | `app/api/auth.py` | 未知用户名也执行一次 PBKDF2（固定假哈希），401 文案统一，避免按响应时延枚举账号 |
| 3 | 账号生命周期 | `app/api/auth.py`、`app/schemas/auth.py`、`app/db/sqlite.py` | 新增 `PATCH /api/auth/users/{id}`（仅管理员）：显示名、角色、科室、启用状态；**`null` 显式拒绝**（`is_active`/`role`/`display_name`），避免绕过禁用逻辑；禁用或改角色吊销该用户全部会话；不可自我禁用；**任何操作必须保留至少一个启用管理员**；写审计事件 `auth_user_updated` |
| 4 | 审计锚定 | `app/services/audit_anchor.py`、`scripts/audit_anchor.py`、`app/api/security.py`、`app/api/runtime.py` | 链头快照写库外 JSONL（`MRA_AUDIT_ANCHOR_FILE`）；条目数低于锚点 → `anchor_truncated`，前缀哈希不符 → `anchor_mismatch`；`entries<=0` 判 `anchor_invalid`；设置 `MRA_AUDIT_ANCHOR_KEY` 后锚点行带 HMAC 签名，伪造/改数 → `anchor_signature_invalid`；`MRA_REQUIRE_AUDIT_ANCHOR=1` 时缺失锚点 → `anchor_missing`；`/metrics` 增加 `mra_audit_anchor_checked`，`mra_audit_chain_valid` 随截断变 0 |
| 5 | 前端错误提示 | `static/doctor.js` | 登录失败 detail 为对象时读取 `detail.message`，429 显示限速提示，不再是 `[object Object]` |
| 6 | 连接泄漏修复（复核发现） | `app/db/sqlite.py` | `get_connection()` 在 PRAGMA/初始化失败时关闭半配置句柄；此前 PRAGMA 抛错会泄漏文件句柄，Windows 上导致临时库无法删除、备份/恢复被占用 |
| 7 | 建库重试 | `app/db/sqlite.py` | `init_db()` 对瞬时 `database is locked` 做 3 次短退避重试；`_ensure_column` 把并发 `duplicate column name` 视为成功 |

## 验证

| 项目 | 结果 | 说明 |
|---|---|---|
| 新增 `tests/test_identity_hardening.py` | **19 passed** | 限速：5 次错误 429、正确口令仍 200、按用户名隔离、成功后清零、未知用户不泄漏；账号：禁用吊销会话并阻止登录、改角色吊销、科室更新可见、空值拒绝、最后一个管理员不可降级、第二个管理员可降级、医生不可改用户、管理员不可自我禁用；锚定：尾截断、中间断链、`entries=0`、签名伪造、严格模式缺锚点、CLI 往返与退出码、`/metrics` 随截断翻转 |
| 定向回归（9 个模块） | **100 passed** | auth / encounters / encounter_workflow / tasks / runtime / asr_prewarm / llm / 企业加固 / 新增 |
| 并发建库稳定性 | 10/10 通过 | 6 线程并发首次建库，修复句柄泄漏后不再出现临时库删除失败 |
| JS 语法 | `node --check static/doctor.js` 通过 | CI 同步检查项 |
| 全量 `pytest -m "not browser"` | **1554 passed, 50 failed, 5 skipped, 31 errors** | 基线 1507 passed / 50 failed / 31 errors；失败集合逐条一致（浏览器未安装），本轮无新增失败 |

## 设计取舍

- **限速不锁死账号**：错误口令被 429 拦住，正确口令放行。好处是攻击者无法用 5 个请求把医生挡在系统外；代价是锁定期间仍会执行一次 PBKDF2（CPU 成本），正式部署需在网关叠加 per-IP 限流。
- **粒度用 (username, client_ip)**：单个出口 IP 连错只影响该账号在该 IP 上的尝试；共享 NAT/容器反代下退化为账号级限速，已在文档标注。
- **锚点签名可选**：设置 `MRA_AUDIT_ANCHOR_KEY` 后锚点行不可伪造；未设置时只能防误删/截断，防不住同时改库与改锚点文件。锚点文件必须放库外只追加存储。
- **改角色即吊销会话**：权限变化后不延续旧令牌；部门变更不吊销，因为每次请求都从 `auth_user` 读最新科室。

## 边界与未完成

1. 无 OIDC/SAML/LDAP、MFA、密码过期与复杂度策略（当前仅长度 ≥8 + 引导管理员弱口令拦截）。
2. 无网关级限流；应用层只覆盖登录接口。
3. 锚定需运维按时执行 `python scripts/audit_anchor.py anchor`；仓库提供命令与校验，不含定时任务。锚点缺失时默认判"有效"，严格模式需显式开启。
4. 审计链仍是单机 SQLite；无 WORM、无异地汇聚、无签名证书。
5. 未做真实浏览器 E2E；本轮只改登录错误提示取值。
6. 未部署验证。

## 独立复核与处置

| 复核发现 | 处置 |
|---|---|
| **阻断**：`{"is_active": null}` 返回 200，绕过自我禁用/最后管理员/吊销会话三条保证，可把系统打到 0 个管理员 | 已修：路由显式拒绝 `null`，DB 层再做类型校验；新增 3 条空值用例 |
| 锁定先于口令校验，攻击者可锁医生 5 分钟 | 已改为"错误口令 429、正确口令放行"，并写清共享代理下的边界 |
| 锚点可被 `{"entries":0}` 行或自洽回滚静默失效 | 已修：`entries<=0` 判 `anchor_invalid`；新增可选 HMAC 签名与严格模式 |
| `display_name: null` 触发 500 | 已修：400 |
| 并发建库偶发临时库无法删除 | 已修：`get_connection` 句柄泄漏 + 建库锁重试 |
| 测试缺口：时序、IP 轴、指标翻转无用例 | 已补：`/metrics` 翻转与签名/严格模式用例；时序与 IP 轴由复核脚本实测，未固化为单测 |

## 回滚

- 本批新增表 `auth_login_attempt`、新增锚点文件（可为空）、接口与行为收紧。
- 回滚：`git checkout baa06e5 -- <文件>`；如需保留新表，可只回退 `app/api/auth.py` 与 `app/services/audit_anchor.py`。
