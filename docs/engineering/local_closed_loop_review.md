# 本地闭环与安全 DESIGN REVIEW

日期：2026-09-14；基线：main 16d35e1；工作分支：codex/alpha-local-closed-loop-safety。

| 评审项 | 本次决定 |
|---|---|
| Goal | 真实本地模型产生可核验、匿名且受审核门禁保护的病历草稿 |
| Deliverables / PBS | CI及合并证据、真实模型运行配置、证据和隐私组件、回归报告 |
| Input / Output | 规范化真实音频→ASR片段→匿名文本→结构字段及引用→受控草稿 |
| Constraints | 保留API和原脏工作树；不改15任务/87h/Gate；Jetson未到货 |
| Largest uncertainty | 运行兼容性和模型无依据输出；分别用实机Smoke与失败封闭的字段证据检查验证 |
| Architecture | 复用FunASR/Ollama/FastAPI/SQLite；模板渲染与安全检查成为正式确定性组件 |
| Module boundaries | 模型只抽取；证据组件校验；隐私组件持有本地映射；审核组件拥有批准事实 |
| Interfaces | 现有业务API保持；/ready绑定真实模型；trace补充实际组件与证据冲突 |
| WBS | 1.2/1.3环境；2.2/2.3音频和角色；3.2/3.3生成审核；4.2/5.x证据回归 |
| Dependencies | CI→main合并→本地模型Smoke→实现→实际回归 |
| Critical Path | 本次实现依赖如上；正式工程CPM待Obsidian共享API连接核验，不另算 |
| Risks | 技术：模型兼容；集成：Schema/Revision；性能：冷启动；数据：标注不足；安全：隐私/幻觉；工期/范围/人员：单人串行、无自动改期 |
| Validation | 干净环境455 tests+8 subtests；Linux verify通过；FunASR三录音；Qwen3-4B真实发热转写输出Schema合法 |
| Milestones / Acceptance | 代码回归、20例匿名测试、20例字段评测、5次离线流程；产品未通过项如实保留 |

固定五问：按数据与审核责任拆分；替代为继续Mock或全量训练，本轮不采用；主要失败点是无依据字段及身份泄漏；最小验证为一段真实音频与本地LLM；以Git SHA、冻结集指标、日志及受控导出证明结果。

ASSUMPTION A01：现有课程录音仅作开发机测试，不代表冻结音频集或真实麦克风复验。
ASSUMPTION A02：将确定性渲染和规则检查作为正式组件，不能隐藏或重命名模型回退来制造零Mock指标。

DESIGN REVIEW GATE：PASS（限定本轮实现；真实模型链路可运行）。EVT/Alpha Gate仍未通过。关键实测：ASR三段耗时59.930/35.955/14.158秒；发热转写前1000字→Qwen3-4B为15.747秒，Schema合法，尚非内容验收。
