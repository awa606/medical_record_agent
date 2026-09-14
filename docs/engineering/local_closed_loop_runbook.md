# 真实本地闭环：复现与边界

本配置用于开发机的 FunASR CPU + Ollama Qwen3:4b GPU 验证。它不代表 Jetson ARM/CUDA 或真实麦克风验收。医生审核接口的自动化测试也不等于医生临床签字。

## 准备

需要 Docker/Compose、可供容器使用的 NVIDIA GPU、已下载的 Qwen3:4b 和五个 FunASR 模型。镜像构建和依赖下载在断网验收之前完成。Python/ASR版本由 `requirements-local-loop.txt` 固定；Ollama和入口代理镜像由 Compose 中的摘要固定。

在当前仓库执行 PowerShell，路径替换为实际的本地私有目录。密码不要保存进 Git：

```powershell
$env:MRA_LOOP_RUNTIME = 'C:/private/mra-loop/runtime'
$env:MRA_ASR_CACHE = 'C:/private/asr_model_cache'
$env:MRA_OLLAMA_MODELS = 'C:/Users/your-user/.ollama/models'
$env:MRA_LOOP_ADMIN_PASSWORD = Read-Host '输入本次隔离测试的独立管理员密码' -MaskInput
$env:MRA_LOOP_PORT = '2780'
docker compose -p mra-local-loop -f compose.local-loop.yml build
docker compose -p mra-local-loop -f compose.local-loop.yml up -d --pull never
curl.exe http://127.0.0.1:2780/health
curl.exe http://127.0.0.1:2780/ready
```

模型缓存目录包含 `modelscope/iic/<模型名>` 或 `modelscope/models/iic--<模型名>/snapshots/master`。必须有配置和对应权重；CAM++使用 `campplus_cn_common.bin`，其余模型使用 `model.pt`。离线缓存不完整时明确失败，不访问模型中心补下载。冷启动完成前 `/ready` 应为503。

浏览器打开 `http://127.0.0.1:2780/static/doctor.html`，使用本次测试的 admin 账号。端口仅绑定本机回环地址。app 和 Ollama 只接入 `internal: true` 网络；入口代理连接入口网络和内部网络，只向固定 app 转发，不提供任意代理接口。应分别验证 app、Ollama 的外部连接确实失败，不能只凭配置宣称离线。

## 执行与结果

```powershell
python scripts/verify_local_api_loop.py --mode privacy --count 20 --output .artifacts/local-loop/privacy-new
python scripts/verify_local_api_loop.py --mode audio --count 5 --audio C:/private/fever_01.wav --output .artifacts/local-loop/audio-new
```

输出目录必须不存在，避免覆盖失败记录。音频接口使用原始上传→真实 FunASR→角色门禁→真实 Ollama→证据校验→审核→导出。若角色未确认或字段冲突，脚本保留失败，不删除内容或伪造人工确认。重复回放同一段音频会明确标记，不能代替五段独立录音或真实麦克风采集。

协议测试检查未批准导出、旧Revision批准、重复批准和修改后撤销旧批准。采用本次隔离测试账号的自动化动作，不写入正式项目的核验者或DONE。

20例合成身份的姓名、证件号和联系方式属于测试真值；原始输入、身份映射和运行DB只保存在私有目录。对外只发布脱敏截图、指标、日志哈希及源码版本。数据库与身份映射目录应使用当前用户的本地访问权限，不放入网盘或公开共享目录。

开发/验证集仅使用既有1–40例；41–60例是冻结测试集。`scripts/run_local_closed_loop_eval.py` 记录模型摘要、数据SHA、源码内容SHA和逐例结果。不要反复用冻结集调提示词。自动事实解析器得分是代理指标，结构字段齐全不代表临床内容完整或零幻觉。

## 结束

```powershell
docker compose -p mra-local-loop -f compose.local-loop.yml down
```

该命令仅停止本配置，私有运行数据仍保留。原始录音、模型权重、DB、身份映射和密码不得提交Git。项目正式15项任务、87h、排期和Alpha/EVT门禁不由测试脚本修改。
