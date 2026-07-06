# Agent 架构图

本页用于答辩时快速展示系统不是线性“输入-输出”，而是具有感知、决策、行动、反馈和医生审核边界的 Agent 闭环。

## 总体闭环

```mermaid
flowchart LR
  A["输入: 文本问诊 / 音频文件"] --> B["感知层: 文本解析 / ASRResult"]
  B --> C["计划层: MedicalRecordOrchestrator"]
  C --> D["执行层: 字段抽取"]
  D --> E["执行层: 病历草稿生成"]
  E --> F["执行层: 安全校验"]
  F --> G["医生审核 Human-in-the-loop"]
  G --> H["确认字段 / 保存草稿 / 确认导出"]
  F --> I["反馈: SSE / agent_task_step / audit_log"]
  I --> C
  G --> I
```

## 分层架构

```mermaid
flowchart TB
  subgraph UI["前端展示层"]
    UI1["index.html 入口页"]
    UI2["doctor.html 医生工作台"]
    UI3["debug.html 调试台"]
  end

  subgraph API["API 层"]
    A1["/api/records/generate"]
    A2["/api/audio/upload"]
    A3["/api/audio/{audio_id}/transcribe"]
    A4["/api/audio/{audio_id}/generate-record"]
    A5["/api/tasks/{task_id}/events"]
  end

  subgraph Agent["Agent 编排层"]
    O["MedicalRecordOrchestrator"]
    S1["EXTRACTING_FIELDS"]
    S2["GENERATING_DRAFT"]
    S3["SAFETY_CHECKING"]
    S4["WAITING_DOCTOR_REVIEW"]
  end

  subgraph Tools["工具与执行层"]
    T1["ASR engines: mock / funasr / qwen3 / online"]
    T2["MockLLM / Prompt chain"]
    T3["ASR evaluator: CER / keyword_recall"]
    T4["Exporter"]
  end

  subgraph Data["状态与审计层"]
    D1["agent_task"]
    D2["agent_task_step"]
    D3["audit_log"]
    D4["ASRResult transcript"]
  end

  UI --> API
  API --> Agent
  API --> Tools
  Agent --> Tools
  Agent --> Data
  Tools --> Data
  Data --> UI
```

## 音频到病历路径

```mermaid
sequenceDiagram
  participant Doctor as 医生端
  participant AudioAPI as Audio API
  participant ASR as ASR Engine
  participant Agent as Orchestrator
  participant DB as Task DB

  Doctor->>AudioAPI: 上传 fever_01.wav
  AudioAPI-->>Doctor: audio_id
  Doctor->>AudioAPI: transcribe?engine=funasr
  AudioAPI->>ASR: transcribe(audio_id, path)
  ASR-->>AudioAPI: ASRResult
  AudioAPI-->>Doctor: text / conversation_text / warnings
  Doctor->>AudioAPI: generate-record
  AudioAPI->>Agent: create_text_task(conversation_text)
  Agent->>DB: agent_task CREATED
  Agent->>DB: agent_task_step extract_fields
  Agent->>DB: agent_task_step generate_draft
  Agent->>DB: agent_task_step safety_check
  Agent->>DB: status WAITING_DOCTOR_REVIEW
  DB-->>Doctor: SSE status and task result
```

## 医生审核边界

```mermaid
flowchart LR
  A["AI 生成字段和草稿"] --> B{"安全校验通过?"}
  B -- "否" --> C["阻止导出并显示 errors"]
  B -- "是" --> D{"候选诊断已确认?"}
  D -- "否" --> E["保留为候选待确认"]
  D -- "是" --> F{"医生确认字段?"}
  F -- "否" --> G["停留在医生审核"]
  F -- "是" --> H["允许确认导出"]
```

## 汇报要点

- 架构图中的 `MedicalRecordOrchestrator` 对应智能体计划层。
- `ASRResult`、字段抽取、草稿生成、安全校验对应行动层。
- `agent_task_step` 和 `audit_log` 对应反馈与审计。
- `doctor.html` 中的确认操作对应 Human-in-the-loop。
