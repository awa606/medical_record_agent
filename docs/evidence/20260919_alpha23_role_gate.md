# WBS 2.3 真实医患角色门禁证据

> 日期：2026-09-19
> 环境：MRA-ALPHA-DEV-01 / Windows / CPU / offline
> 基线：`codex/alpha23-role-gate-validation@bfcd367af163905dec9aad787c814692a830d424`
> Provider：真实 FunASR + CAM++ / `speaker-role-policy-v1`
> Research：**PASS / ADAPT**
> Design Review：**PASS**

## 证据边界

本轮验证真实模型输出、严格角色策略、人工映射、审计事件和服务端生成门禁。未使用 Mock、固定文本或云端回退。原始音频、裁剪片段、RTTM、SQLite、完整转写、日志和运行数据库留在本地 Git 忽略目录；本文和 JSON 只包含匿名样本名、SHA256、聚合指标和状态。

生成任务在角色复核后使用本地 Ollama 配置被接受并进入 `CREATED` 队列，后台 LLM 任务被刻意保留未执行。本结果只证明角色门禁允许合法流程继续，不证明病历已生成，也不证明 LLM 内容质量。

## 匿名输入与哈希

| 样本 | 类型 | 音频 SHA256 | RTTM SHA256 | 真实结果 SHA256 |
|---|---|---|---|---|
| fever-dual | 约60秒双人片段 | `e0d16a3192b99ee99c74fc730facd22338cd4da2a3bb28da980d6d99375f74a4` | `3cb3a3cc9c9634b9b74e75a3abff039d944d11c92023ac9c4e8c6eecc0c057b` | `d7425b09008d846fc892c8bac9210d4122c4b71af8c25b83f65bc69a2fb9c271` |
| chest-dual | 约60秒双人困难片段 | `1d781c47fc4967cc85a734567f0d6fe81cbeff671b20968889c2fe2c9557edc91` | `c71698723c9e71e2e51d43b3a6b8aad3d8b8832ca453cfb02eac09efb03102fd` | `4482382a25533a56826905a43a4a8cacbe4992bf5d15e7e57d99e7cbb2b9fad0` |
| single-counterexample | 约13秒真实单人录音 | `c58c6ff5b5437a2152a2472d2cd8e10be64b42dc213bb3157611ee4333fa732c` | 不适用 | `66341cf2ace631f24fcf276deb18b6c68f7eef7ef2eaae698c7927e83f0fa75c` |

## 真实模型运行

| 样本 | Speaker数 | Segments / Turns | 模型加载 | 推理 | RTF | 峰值RSS |
|---|---:|---:|---:|---:|---:|---:|
| fever-dual | 2 | 21 / 21 | 66.516 s | 20.113 s | 0.3390 | 3,499.69 MiB |
| chest-dual | 2 | 16 / 16 | 55.507 s | 14.362 s | 0.2394 | 4,628.13 MiB |
| single-counterexample | 1 | 1 / 1 | 53.862 s | 1.812 s | 0.1462 | 4,414.10 MiB |

该表只描述 DEV-01 本次真实运行。它不替代2.2冷启动缺口、正式T09或目标硬件验收。

## Diarization实测

| 样本 | Speaker count error | Boundary F1 | Mixed utterance rate | Role consistency | 评测报告 SHA256 |
|---|---:|---:|---:|---:|---|
| fever-dual | 0 | 0.5294 | 0.2857 | 0.8838 | `8c34dca153c83eef705b499977d78aab62a46d6cc46410795b2e22e5b17b5cd8` |
| chest-dual | 0 | 0.3846 | 0.3750 | 0.8780 | `ca41600016e3f3274918f7ffea173970b379ff44480ad523cbffa06663a9bbbc` |

DER/JER 未在本次评测器输出中计算。Boundary F1 和 mixed utterance rate 明确揭示边界仍有误差，本轮未把这些结果包装成正式统计门槛通过。

## 严格门禁与人工恢复

### 模型角色提议与置信度

| 样本 | Speaker | 提议角色 | 置信度 | 来源 |
|---|---|---|---:|---|
| fever-dual | spk0 | patient | 0.8600 | `global_two_party_constraint` |
| fever-dual | spk1 | doctor | 0.8654 | `speaker_context_rules` |
| chest-dual | spk0 | doctor | 0.8443 | `speaker_context_rules` |
| chest-dual | spk1 | patient | 0.8600 | `global_two_party_constraint` |
| single-counterexample | spk0 | 未分配 | 0.0000 | `single_speaker` |

当前 `ASRResult` 只提供单一角色置信度字段，没有可分别读取的 raw/calibrated 置信度；本证据不补造两套数值。双人提议与 RTTM 真值一致，报告字段 `role_accuracy=1.0`，但严格 edge 策略仍把两位 speaker 全部置为待确认，自动接受覆盖率为 0、自动接受准确率为 `null`、高置信度错误为 0。因此该结果不能解释为自动角色判定已经满足正式门槛。

### 双人正路径

两个双人样本均得到相同的门禁闭环：

1. 严格策略初态：`needs_review`，speaker 2，pending 2，自动接受覆盖率 0，高置信度错误 0。
2. 第一次直接生成：`409`。
3. 第二次直接生成：`409`，证明重复调用不能绕过。
4. 通过现有 session PATCH 保存全局 doctor/patient 映射：HTTP `200`。
5. 复核后：`passed`，pending 0，来源全部为 `manual_speaker_map`，置信度 `0.99`。
6. 每个样本新增 `role_reviewed` 审计事件 1 条。
7. 生成入口接受任务，状态 `CREATED`，排入后台任务 1 个；后台 LLM 未执行。

复核后报告中的角色准确率、接受覆盖率和接受准确率均为 1.0，但所有来源均为人工映射；这些数值只证明人工闭环一致，不能作为自动接受能力指标。

### 单人负路径

单人样本为 speaker 1，严格策略状态 `blocked`，reason code 为 `single_speaker_counterexample`，pending 1。连续两次直接生成均返回 `409`；没有 PATCH 成功路径，也没有生成任务。

### API防绕过结论

正例人工确认前和单人负例均在服务端再次检查角色质量。结果不依赖前端按钮状态，因此简单绕过页面、重复请求或直接调用 API 均不能生成替代成功结果。

## 证据哈希

| 文件类别 | SHA256 |
|---|---|
| 角色/API Spike结构化报告 | `7eee941121235e6ff4af27f0d9215c5cfefafaad42dd752f473d6f1237e481ef` |
| fever diarization评测 | `8c34dca153c83eef705b499977d78aab62a46d6cc46410795b2e22e5b17b5cd8` |
| chest diarization评测 | `ca41600016e3f3274918f7ffea173970b379ff44480ad523cbffa06663a9bbbc` |

本地报告可由上述输入、结果和评测 SHA 交叉核对。Git 不保存本地目录路径、原始 ID、原文或身份映射。

## Gate解释

- **Research Gate：PASS / ADAPT**。后端契约成立；普通医生页面需要条件式恢复入口。
- **Design Review Gate：PASS**。接口、失败行为、最小改动和回退明确。
- **Alpha 角色门禁闭环：PASS**。真实双人正路径、真实单人负路径、重复直接 API 防绕过和审计均成立。
- **V02边界**：本证据只支持 V02 的 Alpha 正/负/不可绕过闭环判定。
- **Issue #41：OPEN**。正式样本量、角色准确率 ≥95%、高置信度错误 0 和自动接受覆盖率阈值尚未完成。
- **后台病历生成：NOT EXECUTED**。队列接受不能解释为 LLM 或病历质量通过。

## 回归验证

```text
角色策略、门禁、diarization、session PATCH、audio/record及医生端定向回归：109 passed, 4 subtests passed in 31.03s
新增医生端恢复浏览器测试：2 passed in 12.16s
全量 pytest：514 passed, 8 subtests passed in 231.38s
node --check static/doctor.js：PASS
node --check static/main.js：PASS
隔离服务 /health：200 / ok
隔离服务 /ready：200 / ready（Mock回归环境，不作为真实ASR/LLM证据）
git diff --check：PASS
候选提交敏感文件与密钥扫描：PASS（0个禁止二进制文件，0个密钥命中）
```

全量 pytest 保留了一条 Windows 子进程输出的 UTF-8 解码警告，但没有测试失败。警告发生在既有 clinical E2E CLI 测试的 reader thread，本轮没有为隐藏它而跳过测试。

## 实现边界

Research证据支持的生产改动仅限普通医生页面的条件式角色确认恢复：用真实 `role_quality` 与 pending speaker 判断是否显示入口，复用现有 PATCH，并在 pending 归零且质量通过后继续。模型、策略阈值、API、数据库结构、五步流程和Provider保持不变；实现回归结果由同分支测试记录另行证明。
