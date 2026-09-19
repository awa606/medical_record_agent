# WBS 2.2 真实本地ASR Engineering Design Review

> 日期：2026-09-19
> Research输入：[`R-2.2-Real-FunASR-Integration`](../research/R-2.2-Real-FunASR-Integration.md)
> 选择：**REUSE**
> Design Review Gate：**PASS**

## 1. Goal

复用现有FunASR和音频API，把2.1真实麦克风录音转为可追溯的真实`ASRResult`。本评审不替换模型、不训练、不调整角色门禁，也不宣称正式T09通过。

## 2. Deliverables

- 直接模型与FastAPI进程内应用路由链的真实运行证据。
- 音频、模型、结果和提交SHA清单。
- CER、关键词召回、RTF、内存和失败边界。
- Research、Design、Evidence和Project OS状态同步。

## 3. Input / Output

输入为已验收的2.1 PCM WAV及用户确认真值；输出为现有`ASRResult`、持久化transcript、API运行追踪和可重算指标。

## 4. Constraints

- DEV-01 CPU、本地离线模型缓存；`RECORD_PROVIDER_MODE=demo`但强制配置FunASR并要求本地模型。本次执行路径观察到0次云端、Mock或固定文本回退，不等同edge strict-mode复验。
- 原录音和原Mock结果保持只读；原始媒体、SQLite和日志不进入Git。
- 公共HTTP路由、`ASREngine → ASRResult`和数据库结构保持不变。
- Jetson、长音频、角色判断和正式冻结集均不属于本任务。

## 5. Largest Uncertainty

最大未知是当前提交能否用真实FunASR处理2.1音频。双层Spike已消除该未知。剩余最大风险是冷启动和约6 GiB开发机RSS，不阻止当前集成结论。

## 6. PBS

真实输入、离线模型、FunASR引擎、认证音频API、ASR结果持久化、质量计量、验收证据。

## 7. Architecture

基线为`codex/alpha22-real-funasr-spike@76d20cd61d13380ed98d8e973adffaa6e91507c9`，本轮没有修改生产代码。验证架构为`2.1 WAV → TestClient application lifespan → authenticated audio upload → configured FunASR → ASRResult → transcript JSON`。质量计算从保存结果和人工真值派生，不改变业务结果；Uvicorn监听和网络传输不在本轮证据范围内。

## 8. Module Boundaries

| 模块 | 责任 | 数据所有权 |
|---|---|---|
| Audio API | 鉴权、上传、调用、持久化 | `audio_id`、音频记录、transcript |
| FunASR Engine | 离线转写 | `ASRResult`文本与segments |
| Evaluator | CER、关键词Recall | 派生指标，不修改病历 |
| Evidence | 输入/模型/结果哈希与Gate | 匿名摘要；不保存原始媒体到Git |

## 9. Interfaces

| 接口 | 输入 | 成功输出/状态所有权 | 错误 | 依赖/调用方 |
|---|---|---|---|---|
| `POST /api/audio` | 已认证的PCM WAV | 新`audio_id`和上传记录；Audio API拥有记录 | `401`未认证、格式/大小错误 | 医生工作台或受控客户端、隔离上传目录 |
| `POST /api/audio/{audio_id}/transcribe` | 已认证用户、现有`audio_id`、`engine=funasr` | `200`，backend、model、request ID、`ASRResult`并持久化transcript；Audio API拥有任务状态，FunASR拥有转写内容 | `401`未认证、`404`音频不存在、`409`状态冲突、`503`模型/依赖/推理失败 | Audio API调用FunASR Engine及SQLite/文件存储 |

公共请求和响应保持现状。模型缺失、非法输出、超时或推理失败必须显式失败，禁止生成Mock替代结果。

## 10. WBS

| 项目 | 冻结值 |
|---|---|
| WBS / Owner | 2.2 / 李国毅 |
| 日期 / 工时 | 2026-09-22 / 6h；2026-09-19提前取得证据不重排基线 |
| Deliverable | 真实Audio到ASRResult；音频ID、Provider与运行证据 |
| Acceptance | 一次2.1录音由本地Provider转写；输入标识/结果/日志同源；Mock不得计入 |
| Evidence | Research、Design Review、匿名Evidence摘要及本地原始运行包 |

不新增任务、不改变验收标准，生产代码无需修改。

## 11. Dependencies

- 技术链保持`2.1 → 2.2 → 2.3`；2.1已有效DONE并提供真实录音，2.2有效DONE后才释放2.3 Research。
- 项目现有4条资源依赖保持原样，本轮不新增或删除资源关系。
- V01和T09仍依赖正式冻结集及目标环境，因此本任务完成不会把它们改为PASS。

## 12. Critical Path

沿用Project Planner软件执行链，不自行重算CPM。本次不修改16项、99h、19条技术依赖、4条资源依赖或M1–M4。

## 13. Risks

| 风险 | Trigger | Mitigation / 回退 | Owner / 影响 |
|---|---|---|---|
| R01离线模型加载 | 缓存缺失、权重SHA变化、加载失败 | 固定四模型SHA；失败即保留日志并停止，不回退Mock | 李国毅 / 2.2、V01 |
| R10正式质量失败 | 冻结集CER或关键词Recall不达阈值 | 保留单样本事实，重新打开H-ASR-01；不改写本次结果 | 李国毅 / 2.2、5.x、T09 |
| 性能/资源 | 冷启动RTF 4.192193或RSS约6 GiB导致超时/OOM | 后续预热和生命周期验证；本轮失败时只定位性能层 | 李国毅 / 1.3、2.2 |
| 指标元数据 | 未登记样本带历史蛇咬默认关键词 | 本轮用显式六关键词独立重算；后续清理默认元数据 | 李国毅 / ASR评测 |
| 证据污染/安全 | Mock结果、原音频或身份数据进入Git | 分目录保存、只提交匿名摘要和哈希；发现即回退提交 | Codex / 证据链 |
| Schedule / Scope / People | N/A：未改日期、范围或Owner | 保持16项/99h及单任务执行 | 李国毅 / Alpha |

## 14. Minimal Validation

同一真实WAV依次执行直接FunASR和FastAPI TestClient应用路由链。通过条件为非空真实输出、身份可追溯、backend/model正确、本次路径无Mock/云端/固定文本回退且无OOM；单样本质量单列CER≤15%、Recall≥90%、直接推理RTF≤1。

失败路由固定为：全部集成条件通过则`REUSE/PASS`；只发现明确局部适配时为`ADAPT + Design NEEDS VALIDATION`且2.2留在BACKLOG；模型、依赖、缓存或应用路由无法稳定运行时Research保持`NEEDS MORE EVIDENCE`，2.2留在BACKLOG并只报告第一处阻塞。API冷启动性能不达RTF阈值单列为PARTIAL，不抹去已成立的模型与集成事实。

## 15. Milestones / Acceptance

- 一次2.1真实录音由本地Provider转写：PASS。
- 输入标识、字节SHA、结果和日志对应：PASS。
- Mock不计入通过且实际回退数为0：PASS。
- V01、T09、Jetson及Alpha Gate：未通过/保持原状态。

## 固定五问

1. **为什么这样拆？** 模型层与API层分开后能定位加载、推理或集成失败。
2. **替代方案？** 适配现有链路或重写Provider；真实结果证明无需采用。
3. **最可能失败在哪里？** 离线缓存、冷启动内存和模型输出；均由本轮证据显式观测。
4. **如何最低成本验证？** 复用同一条真实麦克风WAV，无需重新录音或模型大选型。
5. **如何证明完成？** 音频SHA、模型SHA、真实文本、CER/Recall/RTF、API标识和持久化文件闭环。

## Assumptions

- **A01**：用户确认的固定测试句是本录音人工真值。
- **A02**：本次实际FunASR 1.3.14结果只代表DEV-01；不能与历史1.3.29容器证据混称。

## Design Review Gate

**PASS**。已有实现无需生产改动即可完成2.2；该结论不表示V01、T09、Jetson或Alpha Exit通过。
