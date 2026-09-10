# Test Sources

## 自动化与工程测试

- [测试说明](../../README.md#测试)：当前测试命令和覆盖范围。
- `../tests/`：单元测试与 API 测试源代码。
- [能力证据追踪矩阵](../../docs/能力证据追踪矩阵.md)：功能和证据关系。
- [医生工作台验收](../../docs/doctor_workbench_acceptance_v1_0.md)：医生端验收材料。
- [Project OS 验证快照](../03_Project_Plan/Sources/Project_OS_Snapshot/08_Verification_Matrix.md)：当前阶段验证入口。

## 阶段验收边界

POC 的课程演示、历史 CI、固定样本或 Mock 结果不能替代 Alpha 的真实本地 ASR、断网、连续 5 次真实音频 E2E 和证据完整性验收。运行日志、音频、截图和导出结果保留在原始证据目录，不复制到本档案 Git。

## TODO

- 为 Alpha 每条 Exit 条件补齐可读的执行证据、代码 SHA、环境、输入标识、结果和实际核验人/时间。
- 为 Beta/DVT 定义独立的样本、指标、测试环境与验收报告来源。
