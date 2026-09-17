# Knowledge Base V1

Knowledge Base V1在现有SQLite、FTS5和可选BGE混合检索上补齐资料管理闭环。它只向医生提供可追踪参考，不把知识片段当作患者事实，不参与自动批准、诊断或处方。

## 正式范围

- 发热/呼吸资料：流感、新型冠状病毒感染、儿童肺炎支原体肺炎三份官方资料。
- 病历规范：《病历书写基本规范》（卫医政发〔2010〕11号）。
- 管理员：UTF-8 TXT/Markdown导入、版本列表、元数据更新、启用/停用、健康摘要和测试搜索。
- 医生：只检索当前启用版本，并查看来源、版本、章节、逻辑页、片段ID和内容SHA。
- 权限：匿名访问返回401，医生修改返回403。

来源清单见[`config/knowledge/knowledge_v1.json`](../../config/knowledge/knowledge_v1.json)。原始文件、SQLite和embedding保存在本地受控目录，不提交Git。

## 导入规则

1. 管理员在管理后台选择最大2 MiB的UTF-8 `.txt`、`.md`或`.markdown`文件。
2. 相同内容SHA重复导入返回既有文档，不创建副本。
3. 新内容必须使用新版本导入；`PATCH`不能覆盖版本、内容或内容SHA。
4. 新版本默认停用。管理员可以先对指定停用版本运行测试搜索，再显式启用。
5. 启用一个版本会使它成为该来源的当前版本；停用保留文档、片段、embedding、审计与历史引用。

Markdown按标题切节；没有物理分页的文本使用逻辑页1。文件内容不会主动从远程URL下载。

## API

既有读取接口保持兼容：

- `GET /api/knowledge/sources`
- `GET /api/knowledge/sources/{source_id}`
- `POST /api/knowledge/retrieve`
- `GET /api/tasks/{task_id}/evidence`

管理员接口：

- `GET /api/knowledge/admin/documents`
- `GET /api/knowledge/admin/documents/{document_id}`
- `POST /api/knowledge/admin/import`
- `PATCH /api/knowledge/admin/documents/{document_id}`
- `POST /api/knowledge/admin/documents/{document_id}/enable`
- `POST /api/knowledge/admin/documents/{document_id}/disable`
- `GET /api/knowledge/admin/health`
- `POST /api/knowledge/admin/test-search`

## 评测边界

- Development Set：[`fever_respiratory_queries_v1.json`](../../data/knowledge/eval/fever_respiratory_queries_v1.json)，20条，保留用于开发。
- Frozen Check Set：[`knowledge_v1_frozen_check_v1.json`](../../data/knowledge/eval/knowledge_v1_frozen_check_v1.json)，20条，冻结后不调参。
- 工程门槛：Recall@5不低于90%，引用完整率100%，无来源引用0，停用来源泄漏0，未授权修改0。
- T11仍为PARTIAL：最终要求120条复核查询与40条片段级冻结测试，本轮20条来源级检查集不能替代。

执行方式：

```powershell
python scripts/evaluate_knowledge_retrieval.py `
  --db .artifacts/knowledge/knowledge_v1.sqlite3 `
  --dataset data/knowledge/eval/knowledge_v1_frozen_check_v1.json `
  --output-json .artifacts/knowledge/knowledge_v1_frozen_check.json `
  --output-markdown .artifacts/knowledge/knowledge_v1_frozen_check.md
```

## Issue #71开发记录

| 缺口 | 状态 | 证据 |
|---|---|---|
| 兼容迁移与版本事实 | 已实现 | 旧库迁移、相同SHA幂等、新版本保留测试 |
| 管理员API | 已实现 | 列表、详情、导入、PATCH、启停、健康、测试搜索 |
| 权限与审计 | 已实现 | 管理员/医生/匿名回归及`knowledge_admin_audit` |
| 停用来源排除 | 已实现 | 来源列表、词法/向量候选、医生检索与任务证据共用当前启用过滤 |
| 管理后台 | 已实现 | 浏览器真实API导入、测试搜索、启停测试 |
| 正式小型知识包 | 已实现 | 四份来源清单、SHA与本地重建记录 |
| 最终T11数据规模 | 未完成 | 继续保持PARTIAL，不在本PR扩展 |

Issue #71在本PR合入`main`前保持打开。
