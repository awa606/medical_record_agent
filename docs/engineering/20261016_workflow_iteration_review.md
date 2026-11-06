# 2026-10-16 工作区与事实来源迭代评审

## 已批准范围与事实输入

用户批准：仅异常时集中确认、发热/呼吸做深、保留当前候选分批升级。基线开发提交 e95b96b405541abfb2c4ef36df6f742726cecee6，运行 a5c480bc。本轮实际查看工作台、E-9空态、E-6已导出及E-8历史空结果；截图仅在本地 `.artifacts/ui-audit-20261016`。临时事实纯函数反例已经复现，无角色问句及家属自身事实进入临时结果。未把临时错误称为正式批准病历污染。

## Research 决策（按交付拆开）

| 交付 | 内部与外部依据 | 决策/门禁 |
|---|---|---|
| 工作台与历史显示 | 现有HTML/CSS、历史任务读取、Review/Revision接口及浏览器实查；Refactoring UI层级与Carbon空态规范 | ADAPT / PASS；无需新依赖，读取旧任务已经证明数据可恢复；视觉候选仍待用户认可 |
| 临时主体过滤 | 已有clinical_facts上下文规则及本轮可重复反例 | 明确局部Bug，Research不适用；反例→修复→正反例回归 |
| 实时2秒分块/角色校准 | FunASR现有流式引擎、Issue #41及历史低覆盖结果 | NEEDS MORE EVIDENCE；只运行隔离Spike，不修改生产默认 |
| I01跨字段覆盖 | 20261012细粒度事实选择候选6/9、I01 0/3 | NEEDS MORE EVIDENCE；仅一项契约变量，首次失败保留，不生产接入 |
| 流感2025页码 | 已有候选、10查询及旧40查询；原PDF定位 | NEEDS MORE EVIDENCE；不修改启用组合或历史引用 |

比较：重建前端会扩大回归范围；继续追加覆盖难以维持统一间距；复用组件并集中整理受影响规则最小。框架、模型与数据库重构本批排除。官方来源：[Refactoring UI](https://www.refactoringui.com/)、[Carbon空态](https://www.carbondesignsystem.com/building-blocks/core/patterns/empty-states)、[FunASR](https://github.com/modelscope/FunASR)、[Issue41](https://github.com/awa606/medical_record_agent/issues/41)。视频仅核实主题与部分可见示例，未声称完整观看。

## 增量设计评审

| 项目 | 本批确定内容 |
|---|---|
| Goal / Deliverables | 患者列表优先、可读空态与审核摘要；历史内容不误导；问句和家属自身事实不进入患者临时字段。交付代码、回归、候选截图和逐项结果 |
| Input / Output | 已有任务/Revision/转写→纯显示派生；已知角色片段→经过主体过滤的临时预览。缺失和错误明确显示，不生成新患者事实 |
| Constraints | 不新增API/DB字段、框架、模型或临床能力；保留三栏、角色409、批准/导出门禁；不更改旧快照 |
| Largest uncertainty | 复杂家属句的主体范围与前端集中确认可能误接受缺失；通过正反例及现有后端接口约束验证 |
| Assumptions | A01现有模板和安全接口可复用，已通过读取及历史恢复核实；A02候选视觉需用户认可，不自动更新截图基线 |
| PBS / Architecture | 前端：工作台、连续病历、摘要/详情；后端：临时事实过滤；实验：分块/字段候选独立，不导入生产Provider |
| Ownership | 前端不拥有患者真值；显示适配不改currentRecordFields/持久字段。临时过滤不修改正式Revision；研究脚本保存原始响应与映射分别评分 |
| Interfaces | 保持现有GET恢复、Review/Revision/PATCH输入输出；批量确认仅生成现有合法字段决策，并再次校验Revision；缺失/冲突/候选诊断不得自动纳入 |
| Failure handling | 全空历史草稿显示不完整；已批准事实保留并加质量提示。加载失败保留重试；未知角色留转写但不生成患者推断 |
| WBS / Dependencies | 5.1既有缺陷修复，16项99h不变；新实时研究单列额外投入，不启动Alpha+或5.3；UI/主体修复可并行，测试先于候选演示 |
| Critical path | 同轮Planner未取得前不重算或改期；沿用已核验历史快照，正式Gate仍未齐 |
| Risks / rollback | 显示误改数据、主体过度过滤、审核绕过、CSS影响其他页；分别纯函数/数据不变/接口安全/浏览器回归。逐提交回退，8795及离线包不变 |
| Minimal validation | 历史全空/部分/批准/角色前缀；患者/问句/家属自身/家属代述；正常确认与冲突拒绝；空态/长内容/审核/录音截图 |
| Acceptance | 定向及完整测试、语法、差异、实际候选检查；仅工程通过不等于视觉认可、模型质量或医院放行 |

为何这样拆：确定性修复不等待模型研究。替代方案：框架重写或阈值下调均扩大风险。最大失败点：家属代述过度过滤与批量确认误收。最低成本：复用反例、旧结果及现有浏览器测试。完成证明：逐项结果与可运行候选，而非测试总数。

**Design Gate：上述UI/历史适配与临时事实修复 PASS，视觉验收待验证。实时、角色模型、字段模型及知识版本晋级仍为 NEEDS VALIDATION/NEEDS MORE EVIDENCE，不因本评审进入生产。**
