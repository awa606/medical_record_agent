# Docker 本地部署与局域网访问

本文说明如何把 Medical Record Agent 部署到本机 Docker，并让同一局域网内的其他人访问医生端网页。

## 适用范围

- 适合本机演示、课程答辩、同一 Wi-Fi 或同一局域网内访问。
- Docker 镜像包含基础 Web 服务、SQLite、Mock ASR、FunASR 和 SenseVoice CPU 依赖。
- 不包含公网暴露、HTTPS、登录认证、GPU/CUDA 或医院生产部署。
- Docker 默认尝试使用宿主机端口 `2626`，容器内部仍监听 `8000`，即 Compose 端口映射为 `${MRA_HOST_PORT:-2626}:8000`。
- Windows 可能保留一段 TCP 端口。启动前建议扫描 `2600-2699`，选择脚本推荐的可绑定端口；本机当前示例端口为 `2644`。

## 前置条件

- 已安装 Docker Desktop。
- Docker Desktop 正在运行。
- 首次运行 FunASR / SenseVoice 时，电脑需要能访问模型下载源。

检查 Docker：

```powershell
docker --version
docker compose version
```

## 构建与启动

在项目根目录运行，先选择一个可用的 `26xx` 端口：

```powershell
$env:MRA_HOST_PORT = (python scripts\check_docker_port.py --start 2600 --end 2699 --format env).Split("=")[1]
docker compose up -d --build
```

如需手动指定端口，先检查再启动：

```powershell
$env:MRA_HOST_PORT = "2644"
python scripts\check_docker_port.py --port $env:MRA_HOST_PORT
docker compose up -d --build
```

启动后，本机访问：

```text
http://127.0.0.1:<实际端口>/static/doctor.html
```

健康检查：

```powershell
curl http://127.0.0.1:<实际端口>/health
```

预期返回：

```json
{"status":"ok"}
```

## 局域网访问

查找本机 IPv4：

```powershell
ipconfig
```

找到当前网卡下的 IPv4，例如：

```text
192.168.1.23
```

同一局域网内其他电脑访问：

```text
http://192.168.1.23:<实际端口>/static/doctor.html
```

如果其他人无法访问，优先检查：

- 你的电脑和对方是否在同一 Wi-Fi / 局域网。
- Docker 容器是否正在运行。
- 端口映射是否为 `${MRA_HOST_PORT:-2626}:8000`，以及当前 `MRA_HOST_PORT` 是否为真实可用端口。
- Windows 防火墙是否允许当前实际 TCP 端口入站。

如需添加 Windows 防火墙规则，请用管理员 PowerShell 运行：

```powershell
New-NetFirewallRule -DisplayName "Medical Record Agent" -Direction Inbound -Protocol TCP -LocalPort $env:MRA_HOST_PORT -Action Allow
```

## 数据与缓存

Docker Compose 使用两个宿主机目录：

| 宿主机目录 | 容器目录 | 用途 |
| --- | --- | --- |
| `data/docker_runtime/` | `/app/runtime` | SQLite、上传音频、导出结果 |
| `data/asr_model_cache/` | `/app/model_cache` | Hugging Face、ModelScope、Torch 模型缓存 |

这些目录只保留在本机，不提交 GitHub。

容器内关键环境变量：

```text
MEDICAL_RECORD_AGENT_DB=/app/runtime/medical_record_agent.sqlite3
MEDICAL_RECORD_AGENT_UPLOAD_DIR=/app/runtime/uploads
MEDICAL_RECORD_AGENT_OUTPUT_DIR=/app/runtime/outputs
HF_HOME=/app/model_cache/hf
MODELSCOPE_CACHE=/app/model_cache/modelscope
```

## 前端展示测试

本轮不改医生端视觉布局。Docker 启动后，页面应与本地 Python 启动时一致。

测试步骤：

1. 打开 `http://127.0.0.1:<实际端口>/static/doctor.html`。
2. 点击“粘贴问诊文本”，生成病历草稿。
3. 检查病历字段区、对话转写区、AI 辅助与安全校验区是否正常显示。
4. 上传短 MP3/WAV，选择 `Mock ASR`，确认 SSE 分段、角色校正和生成病历流程正常。
5. 上传中文音频并选择 `FunASR`。首次运行会下载 Paraformer Streaming、VAD、标点和 CAM++ 模型，模型加载阶段不显示百分比。
6. 识别开始后，检查中栏是否持续出现转写行和真实进度；测试播放器的播放、拖动和倍速。
7. 等待全局校准完成，确认时间戳、说话人标签和实时病历预览已更新；失败时应显示可理解的原因和重试提示。

## 常见问题

### 1. 镜像构建很慢

本镜像包含 CPU PyTorch、FunASR 和 SenseVoice 依赖，首次构建会下载较多 Python 包，耗时较长。

### 2. FunASR / SenseVoice 首次运行慢

首次使用真实 ASR 引擎会下载模型到 `data/asr_model_cache/`。FunASR 原生流式路线还会下载 Paraformer Streaming、FSMN-VAD、标点和 CAM++，首次加载可能需要数分钟；后续会话复用磁盘缓存和进程内模型实例。

### 3. 其他电脑打不开页面

先在本机确认：

```powershell
curl http://127.0.0.1:<实际端口>/health
```

再确认对方访问的是你的局域网 IPv4，而不是 `127.0.0.1`。`127.0.0.1` 只代表访问者自己的电脑。

### 4. 不建议公网直接访问

当前系统没有登录认证、HTTPS、上传限流和公网安全加固。公网访问应另行设计认证、反向代理和 HTTPS。
