# 本地事实ID约束诊断：资源检查阻断，尚未推理

## 结论

**2026年10月24日21:26（北京时间），本次隔离诊断被既有内存启动线阻断，模型调用为0。** 执行状态为 `BLOCKED_RESOURCE`，Research Gate保持 **NEEDS MORE EVIDENCE**。这不是本地模型质量失败，也没有产生新的抽取成绩。

本批准备了协议和独立执行脚本，完成了JSON Schema静态校验；没有执行三次非空约束请求或后续复制对照，没有改生产Provider、提示词、模型参数或业务库。资源条件不足时未降低门槛、关闭无关程序或循环重启。

## 要诊断的问题与隔离边界

沿用上一轮已冻结的“既往处理定义”候选请求及三份全空原始响应。原始失败发生在选择结果中，映射前就已返回七个空数组；不能归因于后续引用映射。

本轮唯一首阶段变量为：在 `format.properties.previous_treatment` 增加 `minItems=1`。其余提示、事实目录、Schema、Qwen3:4b摘要、温度0、上下文8192、输出上限2048及非思考设置均保持不变。

- `present_illness`仍允许空数组；同一事实ID可以分别出现在现病史与既往处理两个字段。
- 先运行3次；3/3合法则停止，只记录“本请求可输出受约束非空ID”，不能计为理解正确、现病史覆盖或候选放行。
- 若未达到3/3，才用固定ID复制提示比较JSON模式与单字段enum Schema，各3次，总计最多9次；两臂只改变 `format`。
- 零自动重试，总实验窗口不超过60分钟。资源、网络传输、模型摘要、运行版本或时限失败立即停止，不进入病例质量集。
- 沿用已缓存Qwen3:4b；固定模型摘要为 `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`，执行前须核对Ollama `0.40.9`。本次在启动前停止，尚未完成运行中版本与摘要核验。

背景与上一轮失败见[字段定义实验](20261024_local_definition_probe.md)、[跨字段覆盖实验](../evidence/20261016_cross_field_coverage.md)。本轮没有重复调用旧对照组。

## 本次资源记录与无启动证据

| 项目 | 本轮实际记录 | 判断 |
|---|---|---|
| 初始可用内存 | 7,158,755,328 bytes，约6.67GiB | 低于沿用的8GiB启动线；脚本要求严格大于8GiB |
| 初始可用显存 | 4,892MiB | 高于沿用的4,500MiB启动线 |
| 脚本结果 | `STOPPED / RESOURCE_PREFLIGHT_FAILED` | 内存前置检查阻断 |
| Ollama／诊断子进程PID | 审计文件中均未登记 | 资源检查位于两个 `Start-Process` 之前，未启动这些进程 |
| 11435端口 | 结束检查 `port_11435_listening=false` | 没有本次隔离监听 |
| 输出文件 | `host-run-r1`仅有 `runtime-audit.json`；`results-r1`不存在 | 未进入预热及病例请求阶段 |
| 模型请求 | 预热0、病例0、复制控制0 | 无模型效果可评分 |

这些是启动前后的资源采样，不是运行峰值，也不能据此断言内存泄漏、OOM或Qwen的绝对最低硬件需求。

`runtime-audit.json`中的 `production_services_changed=false`仅描述隔离脚本自身。主线程为资源互斥暂时停止本项目应用／网关，恢复原8798版本由外层负责；该生产恢复结果须以主线程运行证据为准，本记录不把隔离脚本的标志解释成“全程未停过8798”。

## 已完成的静态检查

通过本地JSON Schema校验确认：

1. 原Schema同时接受全空结果与同一ID填入两个允许字段的结果。
2. 加入 `previous_treatment.minItems=1` 后，全空结果不合法；仅既往处理有ID、现病史为空仍合法。
3. 错误ID、数组内重复ID被现有约束拒绝。
4. 首阶段仅增加指定 `minItems`；两个复制对照请求仅 `format` 不同。
5. PowerShell语法检查通过；诊断准备没有执行模型调用。

以上只能证明冻结协议及本地Schema验证器的行为，**不能证明Ollama实际约束解码兼容，更不能代替模型事实召回评价**。本例 `maxItems≤1` 时，`uniqueItems`没有额外作用，不将上游对它的支持情况直接判作全空根因。

## 后续唯一启动前提

**后续实际进展（2026-10-25）：** 经用户批准的旧POC资源互斥后，固定协议已执行3次并按分支停止，限定非空约束兼容3/3；自主选择及现病史覆盖仍未通过，未部署。详见[本次执行记录](../evidence/20261025_local_constraint_execution.md)。以下10月24日未执行事实与原资源失败记录继续保留。

待自然可用资源达到原预检线，并完成同样的生产资源互斥后，再依据已冻结协议另行执行。当前不降低启动线，不关闭其他应用，不重新下载模型，不重跑旧病例；失败目录保留，后续执行应使用新的运行目录并登记本轮未执行事实。

资源阻断不影响主线程继续8798音频闭环验收。正式WBS状态不变，模型研究仍未晋级；本记录不提交模型部署结论。

## 证据索引

原始文件仅保存在本地 `.artifacts/local-diagnostic-20261024-r1/`：

| 文件 | 内容／SHA256 |
|---|---|
| `protocol.private.json` | 冻结协议及旧响应；`7ee5f38c992e5cf7c339fe25bf764559cdffdf68293a2798960eb2c0c4d3758f` |
| `diagnostic.py` | 独立诊断脚本；`c23cfeed665ebc5059ae851ad8fb20919feb9222ffc9b7003a37f3eb79d422d5` |
| `run_isolated.ps1` | 资源与自有进程控制；`89ca27490b1917d49dc540f9c2aa2be928e7aa0c91fe10f0ad9c00acc61b2fbb` |
| `static-validation.json` | Schema与单变量离线检查，模型调用0 |
| `host-run-r1/runtime-audit.json` | 资源阻断原始审计；`0c3e15170c79f82d0811be015e67cedc60de8ff3c13953533933642821bcd4a0` |

## 参考资料

- [Ollama结构化输出](https://docs.ollama.com/capabilities/structured-outputs)：Schema限制输出形式，仍需独立验证内容。
- [llama.cpp语法约束说明](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)：支持的Schema子集与提示之间的区别；当前上游说明不能代替本机特定版本实测。
