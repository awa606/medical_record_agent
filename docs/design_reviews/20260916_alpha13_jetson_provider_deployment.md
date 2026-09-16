# Alpha 1.3 Jetson Provider Deployment — Engineering Design Review

- Review date: 2026-09-16
- Project: Medical Record Agent
- WBS: 1.3 本地 ASR / LLM Provider 核对与整合
- Owner: 李国毅
- Repository baseline: `main@feb4c7126d63914b7ced8a3a157b8e80f54e7fa5`
- Research input: `R-1.3-Jetson-Provider-Deployment` — **PASS / ADAPT**
- Gate: **PASS**

## 1. Goal

冻结 Jetson Orin Nano Super 8GB 的目标运行栈、服务边界、模型生命周期、存储、健康语义、失败行为和两小时实机验收方法。设备到手后直接按 Runbook 做分层 Bring-up，不再重新讨论模型或平台选型。

本评审服务于首次目标设备 Bring-up、后续 Provider 适配实现和项目验收。它不证明 Jetson、WBS 1.2、WBS 1.3 或 Alpha 已通过。

本轮不实施生产 Provider、不修改 Compose、不拉取模型、不运行 Benchmark、不训练模型、不扩展知识库或 UI。

## 2. Deliverables

1. 冻结的 JetPack、CUDA、PyTorch、FunASR、Ollama 与 Qwen 版本组合。
2. FastAPI、ASR、Ollama 与 Gateway 的部署边界。
3. ASR 与 LLM 严格串行的生命周期状态机。
4. 模型缓存、SQLite、音频、输出和证据的目录所有权。
5. 保持现有 Provider 接口和 HTTP 路由兼容的适配边界。
6. `/health`、`/ready`、Fail-closed 和错误证据规则。
7. 两小时 Bring-up 的 PASS / PARTIAL / FAIL 判定。
8. 单层回退方案及后续 4–8 小时、24–48 小时验证入口。

## 3. Inputs and Outputs

### Inputs

- Jetson Orin Nano Super 8GB、512GB NVMe、19V 原装电源及局域网。
- 一段脱敏、16kHz、单声道 PCM 医疗音频和对应人工真值。
- 已冻结的模型、容器和配置摘要清单。
- 现有 `ASREngine`、`ASRResult`、`LLMProvider`、`LLMProviderResponse`、字段 Schema、安全门禁及SQLite数据结构。

### Outputs

- ASR 阶段输出真实转写、分段、模型摘要、RTF、峰值内存与温度证据。
- LLM 阶段输出符合现有 `MedicalRecordFields` Schema 的结构化 JSON、模型摘要、时延与卸载证据。
- Bring-up 输出机器可读 JSON、命令日志、容器/模型摘要、内存/温度采样及 Gate 结论。
- 失败输出首个失败层、明确错误类别和可复现命令，不生成替代成功记录。

## 4. Constraints and Assumptions

- **ASSUMPTION A01**：目标板当前不可用。依据是 WBS 1.2 的显式硬件阻塞；影响是 ARM64、统一内存、温度和持续运行保持未验证；通过借用实机执行两小时 Smoke 验证。
- **ASSUMPTION A02**：设备使用 JetPack 6.2.3，而不是 JetPack 7。依据是 Research Gate 选择、NVIDIA 25.06 iGPU 容器和 Ollama `JETSON_JETPACK=6`支持边界；如果设备镜像版本不同，先重刷或停止，不静默换栈。
- **ASSUMPTION A03**：8GB 统一内存不足以支持当前 ASR 与 Qwen3:4b 共驻留。依据是开发机资源 Spike 的 OOM；因此串行生命周期是强制约束。
- **ASSUMPTION A04**：首次 Smoke 可以手工按层启停容器；生产生命周期协调器属于后续实现，不是本设计PR的交付物。
- **ASSUMPTION A05**：局域网、麦克风和浏览器端继续作为外部既有资产；本评审不重新打开硬件、BOM或外壳研究。

其它约束：离线运行、单用户工程原型、禁止 Mock/云端回退、模型权重不进 Git、原始音频与身份数据不上传、部署后 NVMe 至少保留 100GB 可用空间。

## 5. Largest Uncertainty

最大未知是固定版本 FunASR 与 Qwen3:4b 在真实 Orin 8GB 统一内存中的安装兼容、阶段峰值、释放行为和时延。继续在 x86 开发机模拟不能关闭该未知；最低成本且具有决策价值的验证是两小时真实板卡 Smoke。

该未知阻塞 WBS 1.2 的运行验收，但不阻止本设计 Gate 通过，因为部署顺序、接口、阈值、失败分支和回退均已明确。

## 6. PBS

| Deliverable | 内容 | 验收入口 |
| --- | --- | --- |
| D1 Target stack lock | Host、容器、ASR、LLM版本和摘要 | 设备/镜像/模型清单 |
| D2 Runtime topology | Gateway、FastAPI、ASR、Ollama边界 | Docker与网络检查 |
| D3 Lifecycle contract | 串行状态机、内存释放、单飞约束 | 阶段日志与采样 |
| D4 Persistent layout | Runtime、cache、evidence目录 | 目录/空间/权限检查 |
| D5 Readiness contract | health、ready、fail-closed | HTTP响应和探测证据 |
| D6 Bring-up evidence | 两小时Smoke与Gate结论 | Runbook和JSON证据包 |

## 7. Architecture

```text
Doctor PC / Browser / USB Audio
               |
          controlled LAN
               |
        Gateway :2780
               |
      lightweight FastAPI
       |               |
  SQLite/runtime   lifecycle state
       |               |
       +------ one heavy stage at a time ------+
                       |                       |
                on-demand ASR            on-demand Ollama
                FunASR upload             Qwen3:4b
                       |                       |
                 stop + release        keep_alive=0 + unload
```

### Frozen stack

| Layer | Frozen value |
| --- | --- |
| Board | Jetson Orin Nano Super 8GB |
| Host | JetPack 6.2.3 / L4T 36.5.2 / Ubuntu 22.04 |
| CUDA | 12.6.10 |
| Container runtime | Docker Engine + NVIDIA Container Toolkit |
| ASR base | `nvcr.io/nvidia/pytorch:25.06-py3-igpu`；实机拉取后记录 ARM64 RepoDigest |
| ASR | `funasr==1.3.29`，upload四组件：Paraformer、VAD、标点、CAM++ |
| ASR fallback | FunASR ARM64 ONNX Runtime 0.4.6，仅独立文件转写 Smoke |
| LLM runtime | `ollama/ollama:0.34.0@sha256:684d8674b4315fa18f4f0e973a118ec2652ed96f67563277839985175858e0ba` |
| LLM | `qwen3:4b@359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7` |
| Generation | `num_ctx=2048`、`num_predict=512`、`temperature=0`、`think=false`、`keep_alive=0`、并行度1 |

Gateway只暴露至受控私有局域网。ASR和Ollama仅在内部网络或本机回环可达，不开放公网端口。完整离线验证前关闭云端访问，并核对所有必需缓存已存在。

## 8. Module Responsibilities

| Module | Responsibility | Owned data | Boundary |
| --- | --- | --- | --- |
| Gateway | 私有LAN入口和反向代理 | 无业务数据 | 不感知模型状态 |
| FastAPI | HTTP业务、SQLite、任务与证据状态 | 记录、Revision、运行状态 | 不常驻重模型 |
| Runtime lifecycle | 单飞锁、阶段切换、探测凭据和失败分类 | 当前阶段、配置摘要、最近探测 | 后续实现；本轮只冻结契约 |
| ASR worker | 单段真实音频转写和ASR指标 | 临时模型进程、ASR结果文件 | 完成持久化后必须退出 |
| Ollama | 固定摘要模型结构化生成 | 模型驻留状态 | 不读取原始身份数据；生成后卸载 |
| Evidence writer | 原子保存配置、日志、指标和Gate | 本轮证据包 | 不修改历史证据 |

## 9. Interfaces

### Existing public and application interfaces

- 保持 `ASREngine.transcribe(audio_id, audio_path) -> ASRResult`。
- 保持 `LLMProvider.generate_fields_json(conversation_text, timeout_seconds) -> LLMProviderResponse`。
- 保持现有业务 HTTP 路由、字段 Schema、审核和导出门禁。
- 本设计不新增公共 API，不改变现有响应字段。

### Future internal lifecycle contract

| Operation | Input | Output | Error / fail-closed | Dependency |
| --- | --- | --- | --- | --- |
| `probe_runtime()` | 配置摘要和目录 | 分层状态、摘要、时间 | 任何必需项无效即not-ready | Host、NVMe、Docker |
| `run_asr(job_id, audio_path)` | 已登记音频路径 | `ASRResult`及指标 | 缓存缺失、OOM、空文本、超时即失败 | ASR worker |
| `release_asr(job_id)` | 当前ASR阶段 | 进程退出与内存采样 | 进程残留或内存不回落即停止 | Docker/tegrastats |
| `run_llm(job_id, transcript)` | 已持久化脱敏转写 | `LLMProviderResponse` | 摘要不符、非法Schema、超时即失败 | Ollama/Qwen |
| `release_llm(job_id)` | 当前LLM阶段 | `/api/ps`无目标模型 | 30秒仍驻留即失败 | Ollama |

内部状态机固定为：

```text
IDLE
-> ASR_STARTING -> TRANSCRIBING -> TRANSCRIPT_PERSISTED
-> ASR_RELEASING -> MEMORY_RELEASED
-> LLM_STARTING -> GENERATING -> RESULT_PERSISTED
-> LLM_UNLOADING -> IDLE
```

任一阶段失败进入 `FAILED_<STAGE>`，保存证据并停止；不自动跳过、并行或换模型。

## 10. WBS

本设计不新增正式任务：

- WBS 1.2：真实Jetson的容器、目录、网络和两小时Bring-up Smoke。
- WBS 1.3：设备验证通过后实现Provider适配和生命周期协调，仍为6h既有任务。
- WBS 2.2及后续：消费1.3已验证的真实ASR结果，不承担目标运行栈选型。

1.3继续保持 `BACKLOG`；Research PASS和Design PASS只表示可在前置满足后进入实施设计，不绕过1.2。

## 11. Dependencies

- 技术链保持 `1.4 -> 1.2 -> 1.3 -> 2.1`。
- 当前显式阻塞为缺少真实Jetson；六麦型号、外壳或采购报价不重新成为Provider设计依赖。
- 首选FunASR失败时只执行ONNX备用Smoke；若要把备用接入现有 `ASRResult`、分段和角色链路，必须重新做范围明确的Design Review。
- Qwen3:4b失败时只记录失败；1.7B在冻结病例41–60回归前不能替换4B。

## 12. Critical Path

2026-09-16 09:44 +08:00 的 Project Planner Engineering 同轮快照显示：16项、99h、无排程/容量问题，项目结束预测为2026-10-07。1.2、1.3及其后续2.1、4.1、2.2、2.3、3.x、4.2、5.x均为零浮动关键任务。

因此当前关键阻塞只有：取得真实Jetson并完成1.2两小时Smoke。设计文档不能替代该实机证据。

## 13. Risks

| Risk | Trigger | Mitigation | Rollback / owner |
| --- | --- | --- | --- |
| Python/FunASR依赖冲突 | iGPU容器无法安装锁定依赖 | 先做pip dry-run和独立导入 | 停止首选层，运行ONNX独立Smoke；李国毅 |
| 统一内存不足 | OOM、Exit 137或持续swap增长 | 禁止共驻留、单飞、缩短上下文 | 停止失败容器并保存采样；李国毅 |
| 模型无法及时释放 | ASR进程残留或Qwen 30秒后仍驻留 | 容器级隔离、`keep_alive=0` | 强制停止当前容器，不进入下一层 |
| 就绪状态误报 | 真实模型未探测却返回ready | 配置摘要和顺序探测凭据 | `/ready=503`，不得降级Mock |
| 模型摘要漂移 | tag相同但digest变化 | digest白名单和缓存清单 | 拒绝启动，恢复已验证摘要 |
| 数据/隐私泄漏 | 日志、模型输入含身份信息 | 统一脱敏输入和敏感扫描 | 删除本轮临时未归档副本，保留脱敏失败记录 |
| 时间不足 | 两小时内某层无法关闭 | 第一处失败即停止 | 判PARTIAL，只重测失败层 |

## 14. Minimal Validation

### 0–30分钟：平台

记录板卡、ARM64、NVMe、LAN、JetPack、L4T、CUDA和可用内存。任一目标版本不符则停止。

### 30–60分钟：容器与FastAPI

确认Docker、NVIDIA runtime、iGPU容器CUDA；启动轻量FastAPI。`/health=200`必须成立；完整生命周期未接通时`/ready=503`为正确结果。

### 60–90分钟：ASR

用固定脱敏音频完成真实转写，记录加载时间、RTF、峰值、温度和摘要。停止ASR，确认进程退出且内存回落，再进入LLM。

### 90–120分钟：LLM

核对固定Qwen摘要，完成一次合法Schema输出，随后`keep_alive=0`并在30秒内确认卸载。

### Gate判定

- **PASS**：平台、CUDA、Docker、真实ASR、ASR释放、固定Qwen结构化输出和LLM卸载全部成功；无OOM、未披露fallback或身份泄漏。
- **PARTIAL**：基础环境成立，但一个可隔离层失败；保留成功层证据，只修失败层。
- **FAIL**：串行后仍持续OOM、目标栈根本不兼容、主路线与正式备用均不可运行，或发生数据损坏；此时才重新打开Research。

PASS后进入4–8小时功能验证；只有功能验证通过才安排24–48小时稳定性、热和恢复验证。

## 15. Milestones and Acceptance Criteria

### Design Review完成

- 版本、摘要、边界、接口、目录、状态机、失败行为、两小时Gate和回退均明确。
- 不存在需要在设备到手后再次选型的开放设计决定。
- 设计文档、Research和Runbook可以互相追溯。

### WBS 1.2两小时Smoke

- 使用真实Jetson完成分层验证并输出PASS/PARTIAL/FAIL。
- 任何PASS都能从原始命令、摘要、日志和指标重算。
- 两小时Smoke PASS不自动使1.2 DONE，也不替代4–8小时及稳定性验证。

### WBS 1.3实施入口

- 只有1.2前置满足且Project Planner门禁允许后，1.3才能从BACKLOG进入READY/IN PROGRESS。
- 实施必须保持本评审的接口兼容和Fail-closed边界；需要换ASR或LLM路线时返回Research。

## Health, Readiness and Failure Semantics

- `/health=200`只表示FastAPI进程存活。
- `/ready=200`要求SQLite和目录可写、配置与模型摘要一致、ASR与LLM顺序真实探测仍在有效期内、生命周期状态一致、无Mock/云端回退。
- 首次两小时Smoke中，在完整协调器尚未实现时`/ready=503`不构成失败；不得临时放宽探测制造200。
- 缓存缺失、模型摘要不符、非法Schema、超时、OOM、内存未释放或fallback均为显式失败，不生成替代病历。

## Storage and Evidence

- `/srv/mra-alpha/runtime:/app/runtime`保存SQLite、uploads、outputs、speaker profiles、转写和运行证据。
- `/srv/mra-alpha/model-cache/{modelscope,hf,torch,ollama}`保存离线模型；推理容器只读挂载，更新由受控导入步骤完成。
- 证据目录按运行时间创建，保存Git SHA、配置摘要、镜像RepoDigest、模型SHA、命令输出、内存、温度、时延和首个失败层。
- 历史证据和模型缓存不得在回退时清空。

## Rollback Strategy

1. 停止当前失败阶段容器。
2. 保存运行目录、日志、摘要和采样。
3. 恢复上一个已验证镜像、模型摘要或配置文件。
4. 只重跑失败层；禁止同时更换JetPack、基础镜像、ASR与LLM。
5. 若新证据否定串行ADAPT路线，Design Gate退回NEEDS VALIDATION并重新打开Research。

## Fixed Five Questions

1. **为什么这样拆？** FastAPI持久化和重模型生命周期需要不同资源与失败边界；容器隔离能在8GB统一内存下证明释放，并避免一层失败污染其它层。
2. **还有什么替代方案？** 共驻留已被资源Spike否定；ONNX CPU只作ASR备用Smoke；JetPack 7与Qwen 1.7B均缺少当前决策所需证据，不进入主路线。
3. **最可能失败在哪里？** iGPU容器中的FunASR依赖、统一内存阶段峰值、Qwen时延和模型释放。
4. **怎么以最小成本验证？** 借用一块8GB Jetson，按四个30分钟窗口验证平台、容器、ASR和LLM，第一处失败即停止。
5. **怎样证明已经完成？** 以固定SHA、模型/镜像摘要、真实音频转写、合法Schema、内存/温度采样、卸载证据和可重算Gate JSON证明。

## DESIGN REVIEW GATE

**PASS**。

15项设计问题、固定五问、模块与接口、失败分支、两小时阈值和回退均已明确。剩余ARM64、统一内存、温度和持续运行属于已定义的真实硬件验证，不是未决设计选择。

下一步不是业务编码，而是借用Jetson并执行WBS 1.2两小时分层Bring-up Smoke。WBS 1.3继续保持BACKLOG，直到前置和Project Planner门禁允许实施。
