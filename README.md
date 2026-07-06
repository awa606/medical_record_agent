# Medical Record Agent V0.4.5

AI 生成式电子病历辅助系统课程项目。当前版本已经从早期 V0.2 的 Mock ASR 三入口原型，演进为“医生端工作台 + 调试台 + ASR 对比评测 + 开发日志”的完整 POC。

本项目只使用模拟问诊文本、课程样例音频和 Mock/可选本地 ASR，不接真实患者数据、不接真实医院 HIS/EMR、不提交真实 API Key。AI 输出定位为病历草稿，最终字段、候选诊断和导出必须由医生审核确认。

## 当前功能范围

- 医生端工作台：`/static/doctor.html`
  - 文本导入生成病历。
  - 上传音频测试转写。
  - 上传音频生成病历。
  - ASR 评测：CER、keyword_recall、recognized、missing。
  - 左栏病历字段、中栏对话转写、右栏 AI 辅助与安全校验。
  - JSON 仅放在隐藏调试抽屉，不直接出现在主界面。
- 开发调试台：`/static/debug.html`
  - 保留 ASRResult、Task、Steps、Safety JSON。
  - 保留文本、音频、评测、SSE 调试能力。
- 入口页：`/static/index.html`
  - 只提供“进入医生端”和“进入调试页”。
- Agent 主链路：
  - `conversation_text -> 字段抽取 -> 病历草稿 -> 安全校验 -> 医生审核`。
  - 任务状态通过 SSE 推送。
  - 任务步骤和审计日志可追踪。
- ASR 对比引擎：
  - `mock`：默认可用，验证工程链路。
  - `funasr`：本地真实 ASR baseline，可选依赖。
  - `qwen3`：Qwen3-ASR-0.6B 本地对比引擎，可选依赖。
  - `online`：线上 ASR 对比接口，通过环境变量配置。

## 目录与文件说明

```text
medical_record_agent/
  app/                         FastAPI 后端主代码
    api/                       HTTP API 路由
      audio.py                 音频上传、ASR 转写、ASR 评测、音频生成病历
      records.py               文本生成病历任务入口
      tasks.py                 任务查询、SSE、医生审核、确认、导出
    agents/
      medical_record_orchestrator.py
                                病历 Agent 编排器，负责状态流转和步骤记录
    db/
      sqlite.py                SQLite 任务表、步骤表、审计日志封装
    prompts/                   字段抽取、草稿生成、安全校验 Prompt 模板
      medical_record_prompts.py
                                课程汇报用 Prompt 链示例，不接入当前 MockLLM 主流程
    schemas/                   Pydantic 数据结构
      asr.py                   ASRResult、ASRSegment、AudioRecord、评测结果
      medical_record.py        病历字段、候选诊断、安全校验结构
      task.py                  Agent 任务响应结构
    services/                  业务服务
      asr/                     ASR 引擎、评测器、角色策略
        mock_engine.py         Mock ASR
        funasr_engine.py       FunASR 可选引擎
        qwen3_engine.py        Qwen3-ASR 可选引擎
        online_engine.py       Online ASR 适配器
        evaluator.py           CER 与关键词召回评测
        role_strategy.py       医生/患者角色策略与人工校正提示
      mock_llm.py              Mock LLM 字段抽取、草稿和安全校验规则
      exporter.py              Markdown / Word 导出
    data_builder/              课程数据构造与知识库模板工具
    dataset_pipeline/          外部中文医疗问答数据清洗、过滤、伪 EMR 构造
    main.py                    FastAPI 应用入口

  static/                      前端页面
    index.html                 入口页，只跳转医生端或调试台
    doctor.html                医生端工作台页面
    doctor.css                 医生端样式
    doctor.js                  医生端 API 接入和状态渲染
    debug.html                 开发调试页
    style.css                  调试页样式
    main.js                    调试页 API 接入和状态渲染

  docs/                        项目文档
    flow_v0_2.md               V0.2 三入口与 Mock ASR 流程
    asr_v0_3.md                FunASR、ASR 评测、角色策略说明
    online_asr.md              Online ASR 环境变量与对比方法
    qwen3_asr.md               Qwen3-ASR 本地对比引擎说明
    course_scoring_plan.md     课程评分点映射说明
    scoring/                   课程评分冲刺材料
      course_scoring_plan.md   评分证据总表
      agent_design.md          Agent 设计模式说明
      agent_architecture_diagram.md
                                Agent 架构 Mermaid 图
      decision_system.md       决策系统设计
      prompt_chain_design.md   Prompt 链和 JSON 约束说明
      ethics_compliance.md     伦理合规说明
    dev_logs/                  开发日志目录
      TEMPLATE.md              开发日志模板
      DEVELOPMENT_RULES.md     Issue 驱动、日志同步和验证规范
      V0.x_*.md                各版本回顾和变更记录

  scripts/                     数据处理、评测和诊断脚本
    check_funasr_env.py        FunASR 环境检查
    evaluate_asr.py            ASR 评测脚本
    save_run_log.py            根据 task_id 和 audio_id 生成演示运行日志
    ingest_toyhom_dataset.py   Toyhom 数据导入
    build_pseudo_emr_dataset.py
                                伪 EMR 数据集构建
    run_audio_flow.py          音频链路脚本化运行

  tests/                       单元测试与 API 测试
  config/
    hotwords_medical.txt       医疗热词
  data/                        本地运行数据和样例数据，默认不上传真实数据
  video/                       本地音频/视频样例目录，不作为默认提交内容

  requirements.txt             基础依赖
  requirements-asr.txt         FunASR 可选依赖
  requirements-qwen3-asr.txt   Qwen3-ASR 可选依赖
  README.md                    项目总说明
```

## 安装

基础环境：

```powershell
cd "C:\Users\AWA007\Desktop\Data\school\The second semester of the junior year in college\Fundamentals of Artificial Intelligence\medical_record_agent"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果 PowerShell 禁止激活脚本，可以使用：

```bat
.venv\Scripts\activate
```

FunASR 可选依赖：

```powershell
pip install -r requirements-asr.txt
python scripts/check_funasr_env.py
```

Qwen3-ASR 可选依赖：

```powershell
pip install -r requirements-qwen3-asr.txt
```

Online ASR 不允许写死 Key，需要运行时配置：

```powershell
$env:ONLINE_ASR_API_URL = "https://your-asr-provider.example/api/transcribe"
$env:ONLINE_ASR_API_KEY = "<set-in-environment-only>"
```

## 启动

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后访问：

- 入口页：http://127.0.0.1:8000/static/index.html
- 医生端：http://127.0.0.1:8000/static/doctor.html
- 调试台：http://127.0.0.1:8000/static/debug.html
- API 健康检查：http://127.0.0.1:8000/health

## 主要 API

文本病历生成：

- `POST /api/records/generate`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/steps`
- `GET /api/tasks/{task_id}/events`

音频与 ASR：

- `POST /api/audio/upload`
- `POST /api/audio/{audio_id}/transcribe?engine=mock|funasr|qwen3|online`
- `GET /api/audio/{audio_id}/transcript`
- `POST /api/audio/{audio_id}/evaluate`
- `POST /api/audio/{audio_id}/generate-record`

医生审核与导出：

- `POST /api/tasks/{task_id}/review`
- `POST /api/tasks/{task_id}/approve`
- `POST /api/tasks/{task_id}/export`

## 手动验收

文本链路：

1. 打开 `/static/doctor.html`。
2. 点击“文本导入”。
3. 粘贴 fever clean 问诊文本。
4. 点击“确认生成”。
5. 确认左栏生成病历字段，中栏显示对话转写，右栏显示病历草稿、安全校验和候选诊断。

音频链路：

1. 打开 `/static/doctor.html`。
2. 点击“上传转写”或“上传生成病历”。
3. 选择 `fever_01.wav`。
4. ASR 引擎默认选择 FunASR。
5. 如果当前 Python 环境未安装 FunASR，会返回清晰 503 错误；安装 `requirements-asr.txt` 后可重新验收。
6. 转写完成后可打开“ASR评测”，输入人工标注和关键词，查看 CER、keyword_recall、recognized、missing。

调试链路：

1. 打开 `/static/debug.html`。
2. 使用文本、音频或评测入口。
3. 打开调试详情，检查 ASRResult、Task、Steps、Safety JSON。

## 自动测试

```powershell
python -m pytest
```

当前测试覆盖：

- ASR factory、Mock ASR、Online ASR、Qwen3 ASR。
- ASR role strategy。
- ASR evaluator。
- 音频 API。
- 文本病历生成 API。
- 任务 API。
- fever 字段抽取规则。
- 数据集处理 pipeline。

## 数据与隐私边界

- 不上传真实患者数据。
- 不提交真实 API Key。
- 不提交模型权重、下载数据集、运行输出和大体积音视频文件。
- `data/raw_external/`、`data/uploads/`、`data/outputs/` 等运行数据目录只保留必要占位文件。
- Toyhom/Chinese-medical-dialogue-data 等外部数据只用于课程实验，不用于真实诊疗。
- 诊断相关内容只能作为候选，必须由医生确认。

## 开发日志机制

开发日志位于：

```text
docs/dev_logs/
```

后续每次代码、接口、前端、测试或文档结构发生实质修改，都必须新增或更新对应开发日志。模板见：

```text
docs/dev_logs/TEMPLATE.md
```

课程评分材料位于：

```text
docs/scoring/
```

演示运行日志可以通过脚本生成：

```powershell
python scripts/save_run_log.py --task-id 19 --audio-id xxx --title fever_01_demo
```

默认输出到：

```text
docs/dev_logs/runs/YYYY-MM-DD_fever_01_demo.md
```

## 版本回顾

- V0.1：文本版 Agent 骨架。
- V0.2：Mock ASR 与三入口。
- V0.3：FunASR 接入与 ASR 评测。
- V0.3.1：fever 字段抽取规则。
- V0.4：`doctor.html`、`debug.html`、`index.html` 三页面拆分。
- V0.4.3：医生工作台 UI 优化。
- V0.4.5：README 更新、目录说明补齐、GitHub 上传整理。
