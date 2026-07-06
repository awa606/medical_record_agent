# 2026-06-11 Issue #36 Online ASR / Online LLM 区分与 LLM 自检

## 修改日期 / 时间

2026-06-11，时区：Asia/Shanghai

## 修改目标

完成 Issue #36：修正 Online ASR 与 Online LLM 容易混淆的问题，新增 LLM 状态和连接自检能力，并在医生端和调试端顶部明确区分 ASR Engine、LLM Provider、LLM Model、LLM Fallback。

## 修改前问题

- 用户设置 `LLM_PROVIDER=online` 和 DeepSeek 的 `ONLINE_LLM_*` 后，如果前端音频下拉框选择 `Online ASR`，实际调用的是 `/api/audio/{audio_id}/transcribe?engine=online`。
- Online ASR 缺少 `ONLINE_ASR_API_URL` / `ONLINE_ASR_API_KEY` 时，错误提示没有明确说明这是在线语音识别配置，不是在线大模型配置。
- 页面顶部只显示 ASR 状态，缺少 LLM provider / model / fallback 独立状态。
- 没有可点击的 LLM 连接自检入口。

## 输入

- Issue #36 需求。
- 现有 Online ASR、LLM Adapter、Agent Trace、doctor/debug 前端页面。
- 用户 DeepSeek / OpenAI-compatible LLM 配置场景。

## 输出

- 新增 `GET /api/llm/status`：只检查 LLM 配置，不调用外部模型，不返回 API Key。
- 新增 `POST /api/llm/test`：调用当前 LLM provider 做连接与 JSON 输出自检，不返回 API Key。
- doctor/debug 顶部状态区分显示 ASR Engine、LLM Provider、LLM Model、LLM Fallback。
- doctor/debug 增加“LLM自检”按钮。
- debug 音频上传默认 ASR 改为 FunASR，避免误选 Online ASR。
- debug 抽屉新增 LLM Trace JSON，明确展示 `llm_provider`、`model`、`latency_ms`、`fallback`、`fallback_reason`。
- Online ASR 缺配置错误明确提示“当前选择的是在线 ASR，不是在线 LLM”，并引导 DeepSeek 测试使用文本导入或 FunASR 上传生成病历。
- 新增 `docs/online_llm.md`，更新 `docs/online_asr.md` 和评分文档说明。

## 修改文件

- `app/api/llm.py`
- `app/api/__init__.py`
- `app/main.py`
- `app/services/llm/factory.py`
- `app/services/llm/__init__.py`
- `app/services/asr/online_engine.py`
- `static/doctor.html`
- `static/doctor.js`
- `static/debug.html`
- `static/main.js`
- `docs/online_asr.md`
- `docs/online_llm.md`
- `docs/scoring/prompt_chain_design.md`
- `docs/dev_logs/2026-06-11_issue_36_asr_llm_status.md`
- `tests/test_llm_status_api.py`
- `tests/test_asr_factory.py`

## 关键设计决策

- `GET /api/llm/status` 不触网，避免页面加载因为外部模型慢或不可用而卡住。
- `POST /api/llm/test` 才做连接自检，失败时只返回 fallback 状态和安全摘要，不返回 API Key。
- 已配置但未自检的 online / ollama 显示 `reachable=false`、`checked=false`、`fallback=false`，避免误报 fallback。
- Online ASR 错误直接引导用户：测试 DeepSeek/在线 LLM 时，应使用文本导入，或 ASR 选择 FunASR 后上传生成病历。
- MockLLM 继续作为默认和兜底 provider。

## 验证步骤

1. 运行 `python -m py_compile app/api/llm.py app/services/llm/factory.py app/services/asr/online_engine.py`。
2. 运行 `node --check static/doctor.js` 和 `node --check static/main.js`。
3. 运行 `python -m pytest tests/test_llm_status_api.py tests/test_llm_adapter.py tests/test_asr_factory.py`。
4. 运行 `python -m pytest`。
5. 浏览器打开 `/static/doctor.html` 和 `/static/debug.html`，检查顶部 ASR/LLM 状态与 LLM 自检按钮。

## 验证结果

- `python -m py_compile app/api/llm.py app/services/llm/factory.py app/services/asr/online_engine.py`：通过。
- `node --check static/doctor.js`、`node --check static/main.js`：通过。
- `python -m pytest tests/test_asr_factory.py tests/test_llm_status_api.py`：17 passed。
- `python -m pytest`：70 passed。
- `git diff --check -- app static scripts tests docs`：通过。
- 浏览器烟测：`/static/doctor.html` 默认 ASR 为 FunASR，`/static/debug.html` 默认 ASR 为 FunASR；两个页面都显示 LLM Provider、LLM Model、LLM Fallback 和 LLM自检按钮；控制台无 error。
- 补充验收：`/static/debug.html` 上传音频下拉框默认值已改为 `funasr`；调试抽屉存在 `LLM Trace JSON`，明确展示 `llm_provider`、`model`、`latency_ms`、`fallback`、`fallback_reason`。

## 未解决问题

- 本次没有真实调用 DeepSeek；真实连通性需用户本地设置 `ONLINE_LLM_*` 后点击“LLM自检”验证。
- `POST /api/llm/test` 会调用当前 provider，可能产生 provider 侧少量请求成本，故不在页面加载时自动执行。

## 下一步

- 汇报或本地验收时，使用 FunASR/Mock 作为 ASR，引导老师查看 LLM Provider/Model/Fallback 与 Agent Trace。
