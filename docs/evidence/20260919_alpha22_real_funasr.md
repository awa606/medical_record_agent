# WBS 2.2 真实 FunASR 验收证据

> 环境：MRA-ALPHA-DEV-01 / Windows / CPU
> 分支基线：`codex/alpha22-real-funasr-spike@76d20cd61d13380ed98d8e973adffaa6e91507c9`
> 2.1来源：`codex/alpha21-browser-recording-verification@8089163e4d7600297ebc37c9fb144eca83f9df45`
> 输入：WBS 2.1 Realtek物理麦克风录音
> Integration Gate：**PASS**
> Single-sample Quality Gate：**PASS**

## 输入闭环

| 项目 | 值 |
|---|---|
| 原audio_id | `2d1063dd3afb4eec9c6c518c569694c6` |
| API隔离运行audio_id | `f3f29ea40ff24cef8e42bb5330a15fda` |
| 格式 | PCM WAV，单声道，48 kHz，16-bit |
| 时长 | 13.397333秒 |
| 大小 | 1,286,188 bytes |
| 原件与API上传件SHA256 | `c58c6ff5b5437a2152a2472d2cd8e10be64b42dc213bb3157611ee4333fa732c` |
| API request_id | `f3b91c742d73410a8ee43c2a9c67b3ee` |
| 结果文本SHA256 | `214ac7f07d47c7a9770684e1f2b910737a94c85b8a7009e388164ca0b83976aa7` |
| API持久化transcript SHA256 | `b79b82660515205f1c19ac3c160ff9893bf34b1db38f7df0f7e67357c57c0aa7` |

人工真值由用户确认，内容为匿名合成医疗语句。原2.1目录和`mock-asr-v0.2`蛇咬结果保持原样；本轮在新的忽略目录中运行。

## 运行环境

| 组件 | 实际版本 |
|---|---|
| Python | 3.11.6 |
| FunASR | 1.3.14 |
| ModelScope | 1.38.1 |
| Torch | 2.12.1+cpu |
| Torchaudio | 2.11.0+cpu |
| SoundFile | 0.14.0 |
| Provider | `funasr` / `funasr-paraformer-zh` |

运行强制离线、CPU和配置的FunASR backend。系统没有ffmpeg，本PCM WAV由Torchaudio路径读取。

实际`RECORD_PROVIDER_MODE=demo`，同时设置`MEDICAL_RECORD_AGENT_ASR_ENGINE=funasr`、`MEDICAL_RECORD_AGENT_REQUIRE_FUNASR=1`和离线变量。本轮观察到的Mock/云端/固定文本回退为0；该证据不宣称重新验证了edge strict-mode。

## 模型身份

| 组件 | SHA256 | 本轮使用 |
|---|---|---|
| Paraformer | `3d491689244ec5dfbf9170ef3827c358aa10f1f20e42a7c59e15e688647946d1` | 是 |
| FSMN-VAD | `b3be75be477f0780277f3bae0fe489f48718f585f3a6e45d7dd1fbb1a4255fc5` | 是 |
| CT-Punc | `7176cae922a872e130e6b88aef9a1153581711baf79c9124c7c95be383cd6f81` | 是 |
| CAM++ | `3388cf5fd3493c9ac9c69851d8e7a8badcfb4f3dc631020c4961371646d5ada8` | 否，仅核验缓存身份 |

## 实测结果

真实FunASR两次均输出：

> 患者今天发热三十八点二度，伴有咳嗽和咽痛，没有胸痛，也没有药物过敏史。

| 指标 | 直接引擎 | FastAPI TestClient应用路由链 |
|---|---:|---:|
| CER | 0.00% | 0.00% |
| 医学关键词Recall | 100%（6/6） | 100%（6/6） |
| 模型加载/处理 | 63.0422秒加载 | 56.1642秒冷启动处理 |
| 推理/处理RTF | 0.124565 | 4.192193（服务端processing）；4.219280（wall） |
| 峰值RSS | 5,899.34 MiB | 6,001.40 MiB |
| backend / model | `funasr-paraformer-zh` | `funasr` / `funasr-paraformer-zh` |
| Mock/固定蛇咬回退 | 0 | 0 |
| OOM/异常退出 | 0 | 0 |

六项关键词全部识别；“没有胸痛”和“没有药物过敏史”均逐字保留。

计分集合为`发热`、`38.2℃`、`咳嗽`、`咽痛`、`胸痛`、`药物过敏史`。温度规范项`38.2℃`接受别名`三十八点二度`、`38.2度`、`38.2℃`和`三十八点二摄氏度`；否定提及计入识别召回，否定词另行逐句核验。

## Gate解释

- **Integration PASS**：进程内应用生命周期、认证上传、同字节音频、真实FunASR、完整ASRResult、transcript持久化和运行追踪闭环；未验证Uvicorn监听和网络传输。
- **Single-sample Quality PASS**：直接模型推理CER 0%、Recall 100%、RTF 0.124565。
- **API Cold-start Performance PARTIAL**：应用路由冷启动包含约56秒模型加载，且缺少ffprobe/时间戳使响应原生RTF为`null`；服务端processing RTF为4.192193，TestClient wall RTF为4.219280。总Single-sample Quality PASS采用直接引擎热推理RTF 0.124565，不能用来掩盖该冷启动缺口。
- **指标元数据缺口**：现有`ASRResult.medical_keywords`对未登记样本保留了历史蛇咬默认清单；本报告的6/6来自显式六关键词与别名的独立重算。该缺口没有改变转写文本、backend或Mock回退计数。
- 该样本不是正式冻结集，因此T09和V01均不得转为PASS。

## 数据保护

原始WAV、SQLite、完整日志和逐秒资源数据只保存在本地忽略的运行目录；模型权重保留在预先存在且被Git忽略的`data/asr_model_cache`。Git只保存匿名标识、哈希、版本、指标和验收摘要。

## 回归验证

```text
ASR/API定向测试：52 passed in 21.91s
完整pytest：512 passed, 8 subtests passed in 193.74s
node --check static/main.js：PASS
node --check static/doctor.js：PASS
隔离服务 /health：200 ok
隔离服务 /ready：200 ready（回归Smoke环境，不代替本轮真实FunASR结果）
git diff --check：PASS
提交候选敏感/二进制扫描：PASS
```

共享虚拟环境未安装pytest，回归使用与CI主版本一致的系统Python 3.11.6。首次非权威运行把`basetemp`强制放到仓库外，触发一项`Path.relative_to(PROJECT_ROOT)`测试夹具路径失败；该测试用默认路径单独通过，随后完全按默认CI入口重跑得到上述512项全绿。系统`pip check`仍报告全局numba/tensorflow与numpy冲突，本轮代码和真实FunASR运行未依赖这些冲突包。

## WBS验收映射

- 至少一次2.1真实录音由本地Provider转写：PASS。
- 输入ID、音频SHA、结果和日志可对应：PASS。
- Mock不得计入正式通过：PASS，实际Mock回退0次。
