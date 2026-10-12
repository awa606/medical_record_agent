# B01/I01/P01语义规则修复与事实选择验证

确定性缺陷已修复，模型候选未达到晋级门。真实18次提取：原契约0/9、候选6/9；I01三次现病史漏事实，按预注册停止条件不再扩测。当前只提交规则、隔离实验及证据，不部署、不改变生产模型契约或数据库。

## 代码与原始证据

- 实施基线：`381b747229a8d8fd53f31f2dfdec5ad9e32a9ced`，保留同树已提交的草稿/帮助功能。
- 活动分支：`codex/alpha51-demo-visual-e2e`。具体候选代码SHA-256及执行版本在[匿名指标](20261012_clinical_context_and_fact_selection.json)，不能用基线SHA代替未提交候选代码。
- 本地证据：`.artifacts/fact-selection-20261012-110022/`；initial-manifest、offline/、compare/protocol.json、18份新响应及各校验阶段均保留；原有18份SHA未变。原文、响应、SQLite和详细日志不提交Git。

## 规则修复与回归

修复角色继承、患儿主体、局部否定/不确定/恢复范围、词表外家属主体拦截及中文小数体温。原分句编号、原文引用、未确认音频角色和重复音频片段身份校验保持有效。

- 新上下文反例：修复前15失败/7通过，修复后22/22通过。
- 含既有生成/引用的定向回归131通过；候选契约单独8通过，不属于模型测试。
- 完整pytest：756通过、2跳过、2警告，546.74秒。保留Starlette弃用和Windows子进程UTF-8解码线程警告，不掩盖环境限制。
- 全量回归运行于共享工作树，另有前端/帮助测试并发变更，本批不纳入；本轮规则及实验源码哈希固定。该结果不作为最终同SHA发布验收，提交后的CI另行核对。
- 安全集：240/240句、206/206事实；危险翻转、主体、时序、确定性、数值单位、问句泄漏、遗漏及无依据事实均0。
- 18份历史回放：禁网、0真实模型调用；原始/历史流水线/修复后流水线整例均0/18。I01父亲病史新增conflicting为规则拦截，原值与原引文未改，不计作模型正确。

## 真实4B对照

三例各3次，两臂交替；固定模型摘要、temperature=0、num_ctx=8192、num_predict=2048、think=false，每次一次调用、无重试、无人工修订。18份完整响应均stop结束，未截断；模型与执行源码已锁定。

| 输入 | 原契约 | 候选 | 具体结果 |
| --- | ---: | ---: | --- |
| B01 | 0/3 | 3/3 | 症状、时长、体温、胸痛否定及过敏否定完整，原文绑定正确 |
| I01 | 0/3 | 0/3 | 候选避免父亲病史并正确引用；现病史只选体温和胸痛否定，漏发热、两天、咳嗽、咽痛 |
| P01 | 0/3 | 3/3 | 患儿症状与体温保留，家长自身病史不填，过敏不清楚保持partial |

候选9/9没有引用定位或主体错置错误，整例仍只有6/9。该数字是“模型选择+程序类型约束/绑定”的实验流水线成绩，不是纯模型文字生成准确率或临床指标。内部目录中的未识别表达仍需核实；患儿主体锚包含年龄原文，主诉显示形式尚未获得医生验收。

原契约/候选调用耗时中位数7.618秒/4.567秒（含本地Docker传输与离线校验），只描述本小样本，不作为性能承诺。

## 门禁、未执行与下一最小验证

候选REJECTED，Research NEEDS MORE EVIDENCE；9/9阈值不降低。6条边界真实调用、40开发/20冻结模型回归、生产候选集成、部署、三路径及恢复均未执行。5.1 VERIFY、5.3未启动，PR #113保持Draft；工程回归不能替代这些验收。

下一最小问题是I01跨字段覆盖：用单变量契约明确事实可同时用于主诉、现病史和伴随症状；在映射前独立判断现病史漏项。程序不得把未选中的症状补回后声明模型通过。

## 复核入口

```powershell
python -B -X utf8 -m pytest tests/test_clinical_context_regressions.py tests/test_clinical_fact_selection.py -q
python -B -X utf8 scripts/evaluate_semantic_safety.py data/semantic_safety/clinical_assertion_v1.jsonl
python -B -X utf8 -m scripts.experiments.run_clinical_fact_selection offline --archive .artifacts/stable-pilot-20261012/model --output .artifacts/new-offline-replay
```

真实compare模式要求独立输出目录和本地Ollama摘要一致，默认固定18次；本轮已完成，不为获得通过重复运行。详细约束及候选比较见[研究记录](../engineering/20261012_context_and_fact_selection_research.md)。
