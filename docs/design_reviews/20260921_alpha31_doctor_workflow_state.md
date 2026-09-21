# WBS 3.1 医生工作台状态流整合 · Engineering Design Review

## 1. Goal

让医生在工作列表、五步步骤条、主状态和“下一步”区域看到同一个任务状态及可执行动作，降低R04前后端状态不同步风险。

## 2. Deliverables

- 统一状态别名和优先级的纯前端派生层。
- 真实API驱动的浏览器状态契约测试。
- Research、Design和匿名验收证据。

## 3. Input / Output

- **Input**：现有`encounter.status`、`task.status`、`task.current_stage`、结果字段及录音/ASR运行态。
- **Output**：规范状态键、医生可读标签、五步位置、下一步动作和处理阶段展示。

## 4. Constraints

不改变公共API、数据库Schema、Provider、角色阈值、五步结构、工时、日期、依赖或M1–M4。3.2和3.3不并行实施。

## 5. Largest Uncertainty

状态优先级错误可能把失败、角色待确认或未审核任务误显示为可继续。通过状态表、409回归和未审核导出回归控制。

## 6. PBS

1. 状态规范化函数。
2. 工作列表状态标记和标签。
3. 当前任务主状态、步骤条、下一步及处理阶段。
4. 自动化契约和验收证据。

## 7. Architecture

```text
Encounter API / Task API / SSE / Browser runtime
                    ↓
       Workflow State Normalizer
                    ↓
Worklist | Main state | Five steps | Next action | Stage detail
```

后端继续拥有业务状态；前端规范化层只解释，不持久化新状态。

## 8. Module Boundaries

- `app/api/encounters.py`与`app/api/tasks.py`：保持现有响应契约。
- `static/doctor.js`：拥有UI状态别名、优先级和展示映射。
- 浏览器测试：拥有跨API与页面的一致性证明，不成为生产逻辑。

## 9. Interfaces

内部派生函数接收`encounterStatus/taskStatus/currentStage/hasTask/hasFields`，返回规范状态键。运行态包装器再处理录音、ASR结果、角色门禁和错误。未知值安全退回待采集或处理中，不生成可审核/可导出状态。

## 10. WBS

1. 复现当前不一致并冻结契约。
2. 实现状态规范化和展示复用。
3. 运行浏览器、API和全量回归。
4. 归档证据并完成Project OS受控状态流转。

## 11. Dependencies

2.1、2.2、2.3均为有效DONE。保持现有三条前置关系，不新增依赖。

## 12. Critical Path

同轮Project Planner快照显示3.1浮动3个工作日，项目预测结束仍为2026-10-07；本轮不改排期。

## 13. Risks

- **R04**：多处状态映射再次分叉。缓解：所有区域消费同一规范状态。
- **角色门禁回归**：保留409恢复测试。
- **审核边界回归**：保留未审核不可导出测试，3.1只显示状态。
- **范围扩张**：不处理新手黑盒、跨刷新完整恢复或3.2/3.3能力。

## 14. Minimal Validation

真实Test DB创建匿名Encounter，通过现有API恢复任务，逐项验证转写、生成、草稿、待审核、已批准和失败状态。四个页面区域必须共享相同规范键；角色待确认必须优先阻断。

## 15. Milestones / Acceptance

- 五类核心业务状态均有清晰界面和下一步。
- 同一后端任务在工作列表、主状态、步骤条和下一步保持一致。
- 角色门禁、Encounter恢复和未审核导出保护无回归。
- 完整审核导出仍由3.3和M3验收。

## Fixed Five Questions

1. **为什么这样拆？** 状态解释集中、业务动作复用，可单独验证且不触及后端。
2. **替代方案？** 原样复用已失败；新状态机框架成本过高。
3. **最可能失败？** 状态优先级错误放行角色或审核门禁。
4. **最低成本验证？** 真实API加浏览器的表驱动状态契约。
5. **怎样证明完成？** 契约、角色、Encounter、审核保护及全量回归全部通过，并保存匿名证据。

## Assumptions

- **A01**：现有后端状态字段继续保持兼容；本轮不新增状态。
- **A02**：导出按钮仍可在批准后显示，但导出闭环不计入3.1验收。

## Design Review Gate

**PASS**。边界、接口、失败行为、验证和回退均已明确；该结论不代表3.1已经实现或验收通过。
