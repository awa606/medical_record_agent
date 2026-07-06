# 运行日志：fever_01_final_demo

## 运行时间

- 日志生成时间：2026-06-20T23:54:19.600312+08:00
- task_id：38
- audio_id：9b3dd889e50042408fdc7ed4ac7c34ee

## 输入音频

- 文件名：chest_pain_01.wav
- 文件路径：C:\Users\AWA007\Desktop\Data\school\The second semester of the junior year in college\Fundamentals of Artificial Intelligence\medical_record_agent\data\uploads\9b3dd889e50042408fdc7ed4ac7c34ee.wav
- 上传状态：uploaded
- 文件大小：87547982

## ASR engine

- engine：funasr-paraformer-zh
- duration：None
- segments：1

## ASRResult 摘要

- text 摘要：嗯，你好，我是实习生小贺医生。嗯，请问您是何国忠吗？对，哦，嗯您今年多大了？五十五、五十五哈。呃您是什么职业呢？工地工人工地工人哈。嗯，您是南充本地人吗？嗯，家苏顺庆的顺庆区哈。嗯您这次来主要是哪里不舒服呢？我几年前胸痛厉害，胸痛痛嗯，可以给我指指吗？就这边左边胸口痛哈，就这里嗯胸痛大概多久了呢？胸痛大概就是一周多了，一周多了哈。嗯嗯，可以给我们描述一下具体是哪种疼痛吗？具体啊不痛痛，他是痛痛的，喉痛好痛，胸口压了一块石板一样的，像一块石头压在胸口上，对吧？嗯，哦那你发作的时候痛的厉害吗？厉害厉害嗯，痛的是痛厉害的...
- conversation_text 摘要：[待校正] 嗯，你好，我是实习生小贺医生。嗯，请问您是何国忠吗？对，哦，嗯您今年多大了？五十五、五十五哈。呃您是什么职业呢？工地工人工地工人哈。嗯，您是南充本地人吗？嗯，家苏顺庆的顺庆区哈。嗯您这次来主要是哪里不舒服呢？我几年前胸痛厉害，胸痛痛嗯，可以给我指指吗？就这边左边胸口痛哈，就这里嗯胸痛大概多久了呢？胸痛大概就是一周多了，一周多了哈。嗯嗯，可以给我们描述一下具体是哪种疼痛吗？具体啊不痛痛，他是痛痛的，喉痛好痛，胸口压了一块石板一样的，像一块石头压在胸口上，对吧？嗯，哦那你发作的时候痛的厉害吗？厉害厉害嗯，痛的是痛厉害的活了通讯你害呀，那个以前呢就吃了口药，忽略你吃药，那个效果都很好的，都不痛了。所以说医是你也给我喝点货源嘛，那个痛起来很难受的，快点点，他就跟我讲的玉璧一样嘛。哦，那您先别着急，嗯，我们先...
- recognized keywords：胸痛、高血压、冠心病
- missing keywords：胸闷、心慌、心电图

## CER / keyword_recall

- CER：未找到
- keyword_recall：未找到
- evaluation 来源：未找到

## role_strategy / warnings

- role_strategy：single_segment_needs_review
- warnings：FunASR returned a single long segment; speaker role mapping was not applied. Please manually review roles.

## Agent Trace / Decision Loop

- Agent mode: Plan-and-Execute + Human-in-the-loop
- Input type: audio
- LLM provider: mock
- LLM model: mock-deterministic-extractor
- LLM latency_ms: 0
- LLM fallback: False
- LLM fallback_reason: none
- Plan steps: ASR_TRANSCRIBE -> FIELD_EXTRACTION -> DRAFT_GENERATION -> SAFETY_CHECK -> DOCTOR_REVIEW
- Executed steps: FIELD_EXTRACTION:SUCCEEDED, DRAFT_GENERATION:SUCCEEDED, SAFETY_CHECK:SUCCEEDED
- Decision summary: next_state=WAITING_DOCTOR_REVIEW, reason=doctor_review_required
- Safety decision: passed=True, blocked=False
- Human-in-the-loop: True
- Export allowed: False

## 任务状态

- input_type：text
- status：WAITING_DOCTOR_REVIEW
- current_stage：doctor_review
- retry_count：0
- created_at：2026-06-15T08:48:38.704421+00:00
- updated_at：2026-06-15T08:48:38.968094+00:00
- completed_at：2026-06-15T08:48:38.951337+00:00
- error_message：无

## 步骤日志摘要

| 步骤 | 状态 | 尝试 | 耗时 ms | 输出摘要 | 错误 |
| --- | --- | ---: | ---: | --- | --- |
| extract_fields | SUCCEEDED | 1 | 14 | degraded, chief_complaint, present_illness, previous_treatment, accompanying_sym... | 无 |
| generate_draft | SUCCEEDED | 1 | 21 | str | 无 |
| safety_check | SUCCEEDED | 1 | 9 | passed, blocked, errors, warnings | 无 |

## 病历草稿摘要

门诊病历草稿
主诉：未提及/待补充
现病史：后出现头晕等不适。
既往处理：未提及/待补充
伴随症状：头晕
既往史：未提及/待补充
过敏史：未提及/待补充
查体：待医生查体补充
候选诊断：
未提及/待医生确认

## 安全校验摘要

- passed：True
- blocked：False
- errors：无
- warnings：过敏史未提及，建议医生补问。、查体未提及，需医生查体补充。
