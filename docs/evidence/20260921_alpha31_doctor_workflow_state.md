# WBS 3.1 医生工作台状态流整合证据

## 结论

**PASS**。现有五步医生工作台已通过内部状态规范化层完成整合。同一后端任务在工作列表、主状态、步骤条和“下一步”区域使用同一规范状态；公共HTTP API、数据库、Provider、角色阈值和五步结构均未改变。

## Before / After

| 场景 | 修改前 | 修改后 |
|---|---|---|
| `TRANSCRIBING / transcribing`，Encounter仍为`draft` | 主状态`input`、列表“待录入”、下一步“AI处理中” | 四处统一为`transcribing / 智能转写中 / AI处理` |
| `EXTRACTING_FIELDS / extract_fields` | 大小写及字段优先级分散 | 统一为`generating / 病历生成中 / AI处理` |
| `doctor_review`且已有字段 | Encounter的`pending_review`会遮蔽草稿状态 | 统一为`draft_generated / 草稿已生成 / 病历审核` |
| `waiting_doctor_review` | 多处自行判断 | 统一为`pending_review / 等待医生审核` |
| `approved` | 依赖本地审批派生，恢复时可能延迟 | 持久化状态优先，统一进入“导出完成”步骤 |
| `FAILED / failed` | 使用独立`transcription_failed`显示键 | 统一为`failed / 流程中断 / AI处理` |

## 真实API浏览器证据

`tests/test_doctor_workflow_state_contract_playwright.py`使用真实本地API和测试SQLite创建匿名就诊`SIM-WORKFLOW-STATE`，逐态恢复同一个Task并读取页面四个区域。修复前首个转写状态即失败；修复后六种状态全部一致。既有`test_local_patient_encounter_browser_playwright.py`继续证明匿名就诊可完成选择、任务生成、保存、审核、恢复和医生权限隔离；3.1只把该链路显示到“已批准”，导出完整验收仍归3.3。

角色质量409仍优先显示“确认说话人身份”，确认前无法继续；未审核导出保护未被放宽。

## 验证

| 检查 | 结果 |
|---|---:|
| 新增真实API状态契约 | 1 passed |
| 状态流、Encounter、角色恢复及权限定向回归 | 34 passed |
| 完整pytest | 515 passed，8 subtests passed |
| 前端语法 | PASS |
| `/health`与`/ready`回归Smoke | PASS（demo/mock回归配置，不代表真实Provider验收） |
| `git diff --check` | PASS |

完整pytest保留一条既有子进程输出编码warning，没有测试失败。

## 数据与边界

- 未使用真实患者或身份信息。
- 未提交音频、SQLite、模型、缓存或密钥。
- 未修改公共API、数据库Schema或生产Provider。
- 3.2未启动；完整修改、审核、导出仍属于3.3；跨刷新完整恢复仍属于Alpha+。

结构化结果见`docs/evidence/20260921_alpha31_doctor_workflow_state.json`。
