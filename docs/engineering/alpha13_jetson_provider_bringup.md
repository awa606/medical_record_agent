# Alpha 1.3 Jetson Provider 两小时 Bring-up Runbook

本Runbook用于`MRA-ALPHA-ENV-01 Rev.2`的首次分层Smoke。每一步只验证一个层级；失败即保存证据并停止，不同时改JetPack、镜像、模型和应用代码。

## 0. 证据目录与设备身份

```bash
export MRA_EVIDENCE="$HOME/mra-evidence/$(date +%Y%m%d-%H%M%S)"
export MRA_CACHE=/srv/mra-alpha/model-cache
mkdir -p "$MRA_EVIDENCE"
python3 scripts/validate_alpha13_jetson_smoke.py --preflight \
  | tee "$MRA_EVIDENCE/preflight.json"
```

`preflight.json`不是产品验收；任一必需检查失败时停止。

## 1. Docker GPU Smoke

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker info --format '{{json .Runtimes}}' | tee "$MRA_EVIDENCE/docker-runtimes.json"
docker run --rm --runtime=nvidia \
  nvcr.io/nvidia/pytorch:25.06-py3-igpu \
  python -c 'import json,torch; print(json.dumps({"torch":torch.__version__,"cuda":torch.version.cuda,"available":torch.cuda.is_available()}))' \
  | tee "$MRA_EVIDENCE/pytorch-gpu-smoke.json"
```

拉取后用`docker image inspect`记录实际RepoDigest和`Architecture=arm64`。若CUDA不可见，停止在Docker层。

## 2. FunASR首选路线

在25.06 iGPU镜像的临时派生容器中，只安装锁定依赖并导入现有模型缓存：

```bash
docker run --rm --runtime=nvidia \
  -v "$MRA_CACHE:/models:ro" \
  nvcr.io/nvidia/pytorch:25.06-py3-igpu \
  bash -lc 'python -V; python -m pip install --dry-run funasr==1.3.29 modelscope==1.38.1 transformers==5.14.1'
```

依赖解析成功后再构建专用测试镜像并运行一段脱敏16kHz单声道PCM音频。记录模型摘要、设备、加载时间、转写、RTF、峰值内存和温度。模型无法安装、无法加载、OOM或无有效文本时停止首选路线。

## 3. FunASR备用路线

首选路线失败才使用官方ARM64 ONNX CPU Runtime 0.4.6，先核验镜像架构及摘要，再做独立文件转写。输出必须标记`fallback_candidate`，不得作为现有Provider或角色链路通过证据。

## 4. 停止ASR并确认释放

```bash
docker ps --format '{{.Names}} {{.Image}}'
docker stop mra-alpha13-asr 2>/dev/null || true
sleep 10
free -b | tee "$MRA_EVIDENCE/memory-after-asr.txt"
tegrastats --interval 1000 --count 10 | tee "$MRA_EVIDENCE/tegrastats-after-asr.txt"
```

ASR进程仍存在或内存未回落时，不进入LLM阶段。

## 5. Ollama与Qwen3:4b

```bash
docker run -d --name mra-alpha13-ollama --runtime=nvidia \
  -e JETSON_JETPACK=6 -e OLLAMA_NO_CLOUD=1 -e OLLAMA_KEEP_ALIVE=0 \
  -e OLLAMA_NUM_PARALLEL=1 \
  -v "$MRA_CACHE/ollama:/root/.ollama/models:ro" \
  -p 127.0.0.1:11434:11434 \
  ollama/ollama:0.34.0@sha256:684d8674b4315fa18f4f0e973a118ec2652ed96f67563277839985175858e0ba
curl -fsS http://127.0.0.1:11434/api/tags | tee "$MRA_EVIDENCE/ollama-tags.json"
```

先确认`qwen3:4b`摘要为`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`，再发送固定Schema请求：

```json
{
  "model": "qwen3:4b",
  "stream": false,
  "think": false,
  "format": "json",
  "keep_alive": 0,
  "options": {"num_ctx": 2048, "num_predict": 512, "temperature": 0}
}
```

30秒内再次查询运行模型，确认已卸载。摘要不符、超时、非法JSON、OOM或无法卸载即记录失败；不自动切换1.7B。

## 6. FastAPI语义

```bash
curl -i http://127.0.0.1:8000/health | tee "$MRA_EVIDENCE/health.txt"
curl -i http://127.0.0.1:8000/ready  | tee "$MRA_EVIDENCE/ready.txt"
```

- `/health` HTTP 200只证明进程存活。
- 在串行生命周期尚未接入应用前，`/ready` HTTP 503是正确结果。
- 只有真实ASR、固定摘要LLM、SQLite、运行目录和无fallback全部有效后，`/ready`才允许HTTP 200。

## 7. 两小时Smoke结束条件

成功进入下一阶段必须同时具备：

- ARM64、JetPack 6.2.3、L4T 36.5.2与CUDA信息已记录。
- Docker/NVIDIA runtime能在容器中看到CUDA。
- FunASR首选或明确标记的备用路线得到真实转写。
- ASR停止后内存释放可见。
- 固定摘要Qwen3:4b返回合法结构化结果并在30秒内卸载。
- 没有Mock、云端回退、OOM、持续swap或身份数据外泄。

失败时保存第一处失败、日志、命令版本和SHA。两小时Smoke通过后再安排4–8小时功能验证；此时仍不自动进入48小时稳定性测试。

## 8. 回退

```bash
docker rm -f mra-alpha13-asr mra-alpha13-ollama 2>/dev/null || true
```

保留运行目录、证据和缓存，只撤回本次测试容器。恢复已记录的镜像及模型摘要后，重新执行失败层；禁止清空模型缓存或删除历史证据。
