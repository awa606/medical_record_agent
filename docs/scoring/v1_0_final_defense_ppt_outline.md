# v1.0 终答辩 PPT 大纲

## 1. 题目与定位

- AI 生成式电子病历辅助系统 Medical Record Agent。
- 定位为课程 POC：医生审核辅助，不是真实临床自动诊断系统。
- 输入支持文本、Mock ASR 和本地 FunASR 音频流程。

## 2. 问题与边界

- 门诊问诊文本结构化成本高，音频转写后仍需医生复核。
- 系统只生成草稿、候选诊断和安全提醒。
- 不接真实患者数据、HIS/EMR、API Key 或模型权重。

## 3. 系统架构

- FastAPI 后端：records、audio、asr_sessions、speaker_profiles。
- ASR 层：Mock、FunASR、可选 SenseVoice/Qwen3/Whisper 评测路线。
- Agent 层：字段抽取、草稿生成、安全校验、医生审核。
- 前端：医生端三栏工作台、播放器、证据回放和角色校正。

## 4. 核心闭环

- 文本问诊生成病历。
- 音频上传后 SSE 分段转写。
- 说话人校准与医生/患者角色统一校正。
- 实时病历预览与证据定位。
- 正式生成、医生审核、确认导出。

## 5. v0.8.3-v0.8.5 关键突破

- Paraformer 原生流式识别，避免“上传后长时间 0 段”的体验。
- 播放器支持拖动、倍速、Range 和转写行定位。
- CAM++ 对最终片段做说话人校准。
- 证据保留来源 segment，可回放对应音频位置。

## 6. v0.8.8 评测证据

- 人工 RTTM：`fever_01.rttm`、`chest_pain_01.rttm`。
- 只发布两说话人结果，不合成三说话人。
- 平均 `boundary_f1=0.3708`，平均 `role_consistency=0.9004`。
- `DER/JER=not_available`，原因是本机缺 `pyannote.metrics`。
- `pyannote`、`3D-Speaker` 为 `skipped`，不代表模型效果结论。

## 7. 前端复测证据

- Docker 2601 健康检查通过。
- 文本生成、Mock ASR、FunASR 短音频、播放器 Range、角色统一校正、证据面板均有截图。
- FunASR 首次冷启动有下载耗时，答辩前需预热。

## 8. 工程质量

- 测试覆盖 ASR session、records、speaker profiles、speaker role classifier、diarization evaluator。
- 文档覆盖 README、版本记录、能力证据矩阵、debug log、daily log、freeze checklist。
- 表单由 `scripts/update_homework_forms.py` 统一刷新，避免手工错填。

## 9. 已知限制

- 三说话人样本待补。
- `snakebite_01` 是单人朗读，不纳入 diarization 成绩。
- FunASR 冷启动和本地 CPU 性能受机器影响。
- 真实临床部署仍需隐私、权限、审计、医院系统接口和医学验证。

## 10. 收束

- 本项目完成了可运行、可评测、可追踪、可降级的 Medical Record Agent 原型。
- 最终价值是把生成式 AI 放在医生审核边界内，而不是替代医生诊断。
