# DESIGN REVIEW · Knowledge Base V1 Completion

## 1. Goal

在既有 SQLite + FTS5 + BGE 检索底座上完成管理员导入、元数据维护、启停、健康、测试搜索和最小管理 UI，使医生只能读取当前已启用资料，所有结果保持来源追踪和人工审核边界。

## 2. Deliverables

- 兼容旧数据库的增量 schema 与迁移测试。
- 管理领域函数、审计记录和 8 个管理员 API。
- UTF-8 TXT/Markdown 事务性导入、SHA 去重和版本切换。
- 医生、管理员、匿名角色权限矩阵。
- 管理后台 Knowledge V1 面板。
- Development 20 条与 Frozen Check 20 条的分离评测及报告。
- Research、Design、Issue #71 开发日志和可重算证据。

## 3. Inputs / Outputs

输入包括结构化元数据、UTF-8 文本内容、管理员身份、检索查询和现有 SQLite。输出包括版本化 source/document/chunk、管理审计、医生参考结果、健康摘要和评测报告。原始身份、医疗音频、数据库、模型权重和原始资料不进入 Git。

## 4. Constraints

- WBS 4.1 现有 6h 估算保持；超时记录 R11，不静默扩范围。
- 不新增 4.3，不改变 16 项/99h。
- 不修改生产 ASR/LLM Provider、医生审核门禁或公共病历接口。
- 不主动下载远程 URL；上传上限 2 MiB；只接受 UTF-8 `.txt`/`.md`。
- 知识结果只作为医生参考，不是患者事实证据。

## 5. Assumptions / Largest Uncertainty

| Assumption | 依据 | 影响 | 验证 |
| --- | --- | --- | --- |
| A01 现有数据库由应用启动时执行 schema 初始化 | `get_connection` 与现有 init 流程 | 可用增列迁移保持兼容 | 旧 schema fixture |
| A02 20 条开发集已执行且未作为本轮冻结集 | 2026-09-14 报告 | 可复用为 Research Spike | 保留 split 元数据 |
| A03 管理 UI 使用浏览器 FileReader 后提交 JSON | Issue #71 | 不依赖 multipart 解析库 | 浏览器/静态测试 |
| A04 记录规范原文由本地受控导入获取 | Git 不保存原文 | 冻结集运行依赖本地包 | manifest + SHA |

最大未知是停用/版本切换能否在词法、向量、来源列表、任务证据和医生检索上保持一致。

## 6. PBS

1. Data：兼容 schema、source/document/chunk/embedding/audit。
2. Domain：导入、列表、读取、PATCH、启用、停用、健康、测试搜索。
3. API：管理员路由和现有医生路由兼容。
4. UI：管理列表、导入、启停、健康、测试搜索。
5. Verification：迁移、权限、泄漏、冻结集和全量回归。

## 7. Architecture

```text
Admin Browser FileReader
        │ JSON metadata + UTF-8 content
        ▼
FastAPI knowledge admin routes ── require_admin
        │
        ▼
Knowledge Store transaction
        ├─ SQLite source/document/chunk/audit
        ├─ FTS5 lexical index
        └─ optional local BGE derived index

Doctor routes ── require_current_user
        │ active + current only
        ▼
Traceable reference result
```

## 8. Module Boundaries

- `knowledge_store.py` 拥有 schema、事务、版本、状态、检索与健康事实。
- `knowledge.py` 拥有 HTTP 验证、认证依赖和响应映射，不复制 SQL。
- `doctor.html/js/css` 只调用真实 API，不保存知识事实。
- `scripts/` 负责可重算评测，不参与在线请求。
- `config/knowledge` 与 `data/knowledge/eval` 只保存清单和标注，不保存原始资料。

## 9. Interfaces

保留现有读取接口。新增管理员接口：

- `GET /api/knowledge/admin/documents`
- `GET /api/knowledge/admin/documents/{document_id}`
- `POST /api/knowledge/admin/import`
- `PATCH /api/knowledge/admin/documents/{document_id}`
- `POST /api/knowledge/admin/documents/{document_id}/enable`
- `POST /api/knowledge/admin/documents/{document_id}/disable`
- `GET /api/knowledge/admin/health`
- `POST /api/knowledge/admin/test-search`

错误语义：未认证 401；非管理员变更 403；不存在 404；无效格式/编码/元数据 422 或 400；重复 SHA 返回现有文档并标记 `created=false`；事务失败不产生部分 chunk。

## 10. Data Model / Version Rules

- `knowledge_source` 新增 `document_type`、`disease_scope`。
- `knowledge_document` 新增 `effective_date`、`is_active`、`original_filename`、`content_format`。
- 旧记录迁移后默认有效。
- 新导入默认停用；若同来源存在启用的 current 版本，导入不会提前下线它。
- 启用目标版本时，在同一事务中将同来源其他版本设为非 current，并启用目标。
- 停用不删除任何历史事实。
- PATCH 不接受内容、版本、SHA 或 document/source ID。

## 11. WBS / Dependencies

本工作归入 4.1。先完成 Research PASS 和 Design PASS，再执行 backend → import → state filtering → permissions → traceability → UI → capabilities → evaluation。Knowledge V1 完成后 4.1 进入 VERIFY；3.1、3.2、4.2 保持 BACKLOG，只登记可复用证据。

## 12. Critical Path / Schedule

软件支线关键顺序为 `4.1 → 2.1 → 2.2 → 2.3 → 3.1 → 3.2 → 4.2 → 3.3 → 5.1 → 5.3`。4.1 计划 2026-09-18，Software Lane Ready 预测 2026-10-07；完整 M4 仍为 TBD/HARDWARE DEPENDENT。

## 13. Risks / Failure Behavior

- 迁移失败：事务回滚，保留旧数据库备份，不启动管理操作。
- 非 UTF-8、超限或后缀不符：拒绝导入，不写数据。
- 停用泄漏：任何路径检测到即阻止 VERIFY。
- embedding 缺失：允许明确的 FTS5 降级；不能伪装 hybrid。
- 管理审计失败：管理变更与审计同事务回滚。

## 14. Validation Plan

- 旧 schema 无损迁移；重复 SHA 幂等；新版本保留历史。
- 停用文档从词法、向量、来源列表、医生检索和任务证据排除。
- 管理员成功；医生 mutation=0；匿名访问成功=0。
- Development 与 Frozen 分离；Frozen Recall@5 ≥90%，引用完整率 100%，无来源引用 0。
- `pytest`、前端语法、health/readiness smoke、`git diff --check`、敏感文件扫描。

## 15. Milestones / Acceptance

V09 Knowledge Base V1 满足管理闭环、权限、可追踪检索、固定测试集和回归后，4.1 进入 VERIFY。代码合入不等于 T11 或 Alpha Gate 通过；T11 保持 PARTIAL，Issue #71 只在对应 PR 合入 main 后关闭。

## 固定五问

1. **为什么这样拆？** 数据事实、HTTP 边界、UI 和验收各有单一责任，能独立定位迁移、权限或检索问题。
2. **还有什么替代方案？** 原样复用缺管理闭环；新向量库增加无证据的运维成本；现有 store 有限适配最符合范围。
3. **最可能失败在哪里？** 停用和版本切换在不同检索路径不一致。
4. **怎么以最小成本验证？** 旧库 fixture、一个停用文档、管理员/医生/匿名三角色和 20 条冻结集。
5. **怎样证明完成？** 可重算 JSON/Markdown 指标、API/UI 自动测试、来源 SHA、Git SHA、V09 和 4.1 VERIFY 证据。

## DESIGN REVIEW GATE

**PASS**。

Research Decision 已明确为 ADAPT；15 项设计内容、固定五问、数据与接口边界、失败行为、回滚和验收均已覆盖。残余未知由本轮已授权实现中的自动测试回答。

下一步：按上述顺序补齐 Knowledge V1；每个切片测试后提交，完成后停在 4.1 VERIFY。
