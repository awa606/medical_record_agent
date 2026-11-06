# 2026-10-19 数据查看器审核状态中文修复

## 问题与原因

8796 查看器中的审核记录 `status=active` 显示“未配置中文释义”。读取 `app/db/sqlite.py` 确认：创建审核时写入 `active`，当前审核查询及导出要求该状态且 `invalidated_at` 为空；新版本或新审核可使旧审核失效。因此它表示有效审核记录，不是模型准确率或临床质量评价。

## 修改与验证

仅为已知枚举增加“有效审核（active）”显示。保留“已失效（invalidated）”及未知值的“未配置中文释义（原码）”，不修改表名、枚举值、查询参数或快照内容。

新增真实 Datasette 路由回归，覆盖审核详情页、失效和未知状态、JSON 原值及读取前后快照字节一致。修复前定向测试因缺少“有效审核”失败；修复后在现有 Datasette 0.65.5 独立环境运行 `python -m unittest tests.test_data_browser`，11 项通过。这里验证的是工具展示与访问行为，不替代业务批准和导出门禁验收。本次未重启或部署查看器。

## 本轮源码差异复核

以审查时 HEAD `4c2d7cc` 为基线，已跟踪的修改集中于在线接入与就绪、启动器、家属代述校验、导出、音频历史状态及查看器文案。Git blob 核对确认以下源文件未改变：

- `app/prompts/medical_record_prompts.py`
- `app/services/llm/ollama_provider.py`，包括 `numbered_source` 与 `extraction_schema`
- `app/services/llm/llm_record_generator.py`
- `app/services/llm/online_provider.py`

新 DeepSeek 适配复用既有提示词、分句和字段 Schema，并使用已执行 Spike 的 JSON 模式 Schema 说明及输出上限；这些在线协议适配不应被表述为只换模型的公平质量实验。技术接入通过与模型事实覆盖未达标分别保留。

已核对 live 在线 profile 缺失或未知时的就绪拒绝分支。在线缓存只复用短期模型列表连通性结果，不调用收费生成，不代表病历质量通过。新增实时转写脚本属于隔离实验，未接入生产调用链。

本记录是代码和定向测试审查，不提前确认候选部署、全量回归、物理录音、显示及稳定发布通过。
