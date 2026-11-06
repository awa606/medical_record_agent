# 仓库治理与变更控制

本文定义 `awa606/medical_record_agent` 的分支、评审、证据与发布规则。它描述**当前真实的单人维护模式**，不是通用开源流程模板，也不代表医院级发布控制已经建立。

## 1. 角色与仓库边界

- 维护者：李国毅（单人维护），GitHub 账号 `awa606`。
- `main`：已验证的发布线。只接受通过 CI 的合并，不直接提交业务代码。
- `codex/*`：工作分支。一个分支对应一个可说明的交付主题，例如 `codex/alpha51-demo-visual-e2e`。
- 多工作树：同一仓库通过 `git worktree` 并行隔离实验、候选构建与历史核查；分支与工作树一一对应，不共享未提交改动。
- 运行版本与应用版本分离：文档提交 SHA 不等于运行镜像 SHA；报告中必须分别标注。

## 2. 分支与合并

1. 从当前发布基线切出 `codex/<topic>` 分支。
2. 小改动按 `假设 → 最小验证 → 修改 → 验证` 执行；新模块、接口或跨模块重构先完成工程设计评审。
3. 提交前必须本地跑通受影响测试；提交信息使用 `type: summary`（`feat` / `fix` / `docs` / `test` / `build` / `refactor`）。
4. 推送后开 PR，CI `verify` 必须通过（pytest、`git diff --check`、`node --check static/doctor.js`、`/health` 冒烟）。
5. 单人维护模式下不要求同账号自审；涉及安全门禁、导出、审批、权限的改动，必须至少有一名未参与实现的复核者（见 `docs/engineering/agents/mra-review-roles.md`）。
6. 合并方式：squash 或 rebase 保持线性历史；禁止对 `main` 强推。
7. 分支合并后删除远端分支；保留本地工作树至证据归档完成。

## 3. 版本与发布

- 版本号 `vMAJOR.MINOR.PATCH`，当前正式版本 `v1.4.0`；`v1.5.0` 需评测集与 Provider 基线合并后再打 tag。
- 每个版本必须回答三个问题：代码实现了什么、数据证明了什么、还有什么没完成。
- 发布产物：镜像（本地 tag + 记录 digest）、`static/deployment.json` 版本字段、证据文档、回滚说明。
- 发布前检查：`/live` 与 `/ready`、数据库 `integrity_check`、审批→导出链路、角色门禁 409、备份可用。
- 回滚：保留上一版本镜像与升级前数据库备份；回滚顺序为「停服务 → 恢复备份 → 切换镜像 → 冒烟」。

## 4. 证据与报告

- 证据目录：`docs/evidence/YYYYMMDD_<topic>.md`；工程分析：`docs/engineering/`；运行手册：`docs/runbooks/`。
- 本地原件（截图、录音、模型原始响应、数据库副本）放 `.artifacts/`，不入库，不上传患者数据、凭据、密钥、浏览器配置。
- 证据必须写明：版本 SHA（前端/后端/镜像）、环境、输入、实际结果、核验人与时间。
- 代码存在、测试文件存在、CI 通过都不等于验收完成；首次模型输出与人工修订分别记录。
- 复用旧证据必须注明原版本、时间与校验值，不把跨版本单项成功拼成同版本全流程通过。

## 5. 安全与数据

- 凭据只经环境变量注入（`ONLINE_LLM_API_KEY`、`MRA_AUDIT_HMAC_KEY`、`MRA_METRICS_TOKEN` 等），不写入仓库、镜像层或日志。
- 登录失败按 `(username, client_ip)` 计次：15 分钟内 5 次失败锁定 5 分钟；审计锚定文件 `MRA_AUDIT_ANCHOR_FILE` 指向库外只追加存储，由运维定期执行 `python scripts/audit_anchor.py anchor`，`verify` 用于交付前核验。
- 外部 LLM 调用必须开启脱敏（`MRA_ANONYMIZE=1`）；显式关闭需同时设置 `MRA_ALLOW_UNREDACTED_OUTBOUND=1` 并在证据中记录理由。
- 数据库、`uploads/`、`outputs/`、`speaker_profiles/` 为运行数据，不提交 Git；备份与恢复使用 `scripts/edge_sqlite_backup.py`（`backup` / `verify` / `restore`）。
- 审计链密钥 `MRA_AUDIT_HMAC_KEY` 变更后，历史条目只能以下线密钥验证，不得删除旧条目。

## 6. 变更控制边界

- 需要事先给出变更摘要并等待确认：删除正式任务、阶段迁移、修改里程碑验收标准、大规模 WBS 调整、阶段范围或路线图变化、删除证据。
- 不需要确认：文字修订、单点缺陷修复、测试补充、文档与配置的局部修正。
- 任何改动都不得降低既有安全门禁（角色质量 409、未审核导出 400、旧 Revision 409、审批失效链）。

## 7. 已知限制

- 无 SSO/OIDC/LDAP 接入、无 MFA、无科室级资源隔离的完整实现（当前为按 `department_id` 的渐进实现，历史空科室单据按 owning doctor 的科室判定）。
- 无独立覆盖率门槛、无 SAST/依赖漏洞扫描、无真实浏览器 E2E。
- 审计哈希链为单机 SQLite 内的链式校验：中间行篡改或删除可检出；**尾部截断或整表清空只有在存在外部锚点时才能检出**（`scripts/audit_anchor.py` 已提供锚定与校验命令，但锚点必须存放在库外只追加存储，且需运维按时执行）。尚未接入 WORM 存储、异地汇聚或签名证书。
- 这些限制在 `docs/enterprise/ENTERPRISE_CDS_ROADMAP.md` 的 E2/E6 中另行处理，不在本文宣称已满足。
