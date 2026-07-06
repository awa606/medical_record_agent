# 2026-06-08 Issue #31 决策系统、Prompt 链与伦理合规

## 修改日期 / 时间

2026-06-08，时区：Asia/Shanghai

## 修改目标

完成 GitHub Issue #31：补齐决策系统设计、Prompt 链代码示例和伦理合规文档，支撑课程评分中的“决策系统设计 10 分”和“伦理合规设计 5 分”。

## 修改前问题

- 项目已有 MockLLM、Orchestrator、安全校验和医生审核边界，但缺少集中展示 Prompt 链的文档。
- 现有 prompt 文件已用于工程流程，但不适合直接作为汇报中的标准 Prompt 示例。
- 决策系统和伦理合规措施分散在 README、代码和前端行为中，没有形成评分材料。

## 输入

- GitHub Issue #31：课程评分冲刺 P2：补全决策系统、Prompt 链与安全合规文档。
- `app/agents/medical_record_orchestrator.py`
- `app/services/mock_llm.py`
- `app/schemas/medical_record.py`
- `app/db/sqlite.py`
- 当前 ASR role_strategy 和医生端工作台行为。

## 输出

- 新增 `app/prompts/medical_record_prompts.py`，作为课程展示和未来真实 LLM 接入的 Prompt 示例。
- 新增 `docs/scoring/prompt_chain_design.md`。
- 新增 `docs/scoring/decision_system.md`。
- 新增 `docs/scoring/ethics_compliance.md`。
- 新增本次 Issue #31 开发日志。

## 修改文件

- `app/prompts/medical_record_prompts.py`
- `docs/scoring/prompt_chain_design.md`
- `docs/scoring/decision_system.md`
- `docs/scoring/ethics_compliance.md`
- `docs/dev_logs/2026-06-08_issue_31_decision_prompt_ethics.md`

## 关键设计决策

- Prompt 示例文件不接入现有 MockLLM，避免改变业务流程和测试基线。
- 文档强调 JSON Schema、Pydantic Schema、医生审核和安全校验共同构成决策系统。
- 伦理合规按隐私保护、医疗安全、防 Prompt 注入、审计追踪、公平性和局限性展开，直接对应评分细则。

## 验证步骤

1. 使用 `python -m py_compile app/prompts/medical_record_prompts.py` 检查 Prompt 示例代码语法。
2. 使用 `rg "MEDICAL_RECORD_SYSTEM_PROMPT|FIELD_EXTRACTION_PROMPT|DRAFT_GENERATION_PROMPT|SAFETY_CHECK_PROMPT" app/prompts/medical_record_prompts.py` 检查必需常量。
3. 使用 `rg "隐私保护|Prompt 注入|审计追踪|公平性" docs/scoring/ethics_compliance.md` 检查合规要点。
4. 使用 `python -m pytest` 确认不影响现有程序运行。

## 验证结果

- `python -m py_compile app/prompts/medical_record_prompts.py` 通过。
- `rg "MEDICAL_RECORD_SYSTEM_PROMPT|FIELD_EXTRACTION_PROMPT|DRAFT_GENERATION_PROMPT|SAFETY_CHECK_PROMPT" app/prompts/medical_record_prompts.py` 可检出必需 Prompt 常量。
- `rg "隐私保护|Prompt 注入|审计追踪|公平性" docs/scoring/ethics_compliance.md` 可检出合规要点。
- `python -m pytest` 通过，结果：56 passed。

## 未解决问题

- 当前仍不接真实 LLM；Prompt 文件作为课程展示和未来接入契约。
- 未新增 Prompt 注入自动化测试，因为本 issue 要求只补文档和必要 Prompt 示例代码。

## 下一步计划

- 汇报前补充截图：医生端三栏、调试台 Steps JSON、Prompt 代码片段和架构图。
