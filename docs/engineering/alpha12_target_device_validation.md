# Alpha 1.2 目标设备复验清单

本清单用于在 `MRA-ALPHA-ENV-01` 上复验 Docker、本地ASR、本地LLM和运行目录。开始前必须确认设备身份与已批准的1.1硬件基线一致；若正式目标从旧办公主机基线改为Jetson，应先更新1.1的范围与证据，不能只在1.2报告中静默替换目标。

## 1. 设备身份与环境

记录以下原始输出，不手工改写：

```bash
date --iso-8601=seconds
uname -a
uname -m
cat /etc/os-release
docker version
docker compose version
free -h
df -h
```

Jetson候选设备另记录：

```bash
cat /etc/nv_tegra_release
dpkg-query --show nvidia-jetpack 2>/dev/null || true
nvidia-smi 2>/dev/null || true
tegrastats --interval 1000
```

验收前在报告中明确：CPU/SoC、架构、共享内存、存储、JetPack/CUDA、Docker与Compose版本，以及设备是否与1.1批准基线一致。

## 2. 私有目录和模型缓存

- 运行目录、SQLite、上传和导出目录只允许当前测试账号访问。
- 管理员密码使用本次测试独立值，不写入Git、命令历史或截图。
- 模型缓存必须在断网前准备完毕，并记录模型文件SHA-256。
- `qwen3:4b`、Paraformer、VAD、标点和CAM++必须能从本地缓存加载。
- 缓存缺失时记录`BLOCKED`，不得临时切换Mock或云端Provider制造成功。

## 3. 构建与启动

在目标设备的当前提交上执行；路径替换为设备本地私有目录：

```bash
export MRA_LOOP_RUNTIME=/private/mra-alpha12/runtime
export MRA_ASR_CACHE=/private/mra-alpha12/asr-cache
export MRA_OLLAMA_MODELS=/private/mra-alpha12/ollama-models
export MRA_LOOP_ADMIN_PASSWORD='本次独立密码'
export MRA_LOOP_PORT=2782

docker compose -p mra-alpha12-target -f compose.local-loop.yml config --quiet
docker compose -p mra-alpha12-target -f compose.local-loop.yml build app
docker compose -p mra-alpha12-target -f compose.local-loop.yml up -d --pull never
```

如果ARM64构建、PyTorch/FunASR依赖或Jetson容器运行时失败，保存第一处失败及完整版本信息，停止扩大修改范围。不得在同一次实验中同时更换基础镜像、模型和Compose结构。

## 4. 就绪与页面

```bash
curl --fail http://127.0.0.1:2782/health
curl --fail http://127.0.0.1:2782/ready
curl --fail --request POST http://127.0.0.1:2782/api/llm/test
curl --fail --output /dev/null http://127.0.0.1:2782/static/doctor.html
docker compose -p mra-alpha12-target -f compose.local-loop.yml ps
docker stats --no-stream
```

必须同时满足：

- `/health`为HTTP 200。
- `/ready`为HTTP 200，SQLite和三个运行目录可写且空间充足。
- Provider为`ollama`，模型为批准的本地模型，`fallback_allowed=false`、`fallback_provider=null`、`fallback=false`。
- `/api/llm/test`执行真实结构化生成并返回`reachable=true`。
- ASR预热profile与本次验证目标一致；upload四组件不得用于宣称streaming五组件已通过。
- 医生页面返回HTTP 200。

## 5. 容量与稳定性

至少记录：

- 冷启动到首次`/ready`成功的时间。
- App、Ollama及系统总峰值内存。
- 模型加载失败、OOM、超时、温度和降频事件。
- 30分钟持续运行期间每分钟一次的就绪结果。

8GB共享内存设备若出现OOM或系统换页导致服务不稳定，应将1.2保持`BLOCKED/IN PROGRESS`并返回模型或运行策略研究，不能降低既有验收标准。

## 6. 证据包

目标设备测试完成后保存：

```text
environment.json
compose-config.sha256
image-inspect.json
model-manifest.json
ready-samples.jsonl
resource-samples.csv
container-logs.txt
README.md
```

报告必须包含分支、Git SHA、镜像摘要、设备编号、采样时间、执行者、通过项、失败项和未测试项。原始音频、身份数据、数据库、密码和模型权重留在受控本地目录。

## 通过条件

只有目标设备身份与1.1一致、构建成功、真实Provider与指定ASR profile就绪、容量与持续运行无阻断错误，并且证据包可重算时，1.2才可从`IN PROGRESS`进入`VERIFY`。人工或Codex核验完成后再按Project Planner Engineering门禁判断是否允许`DONE`。
