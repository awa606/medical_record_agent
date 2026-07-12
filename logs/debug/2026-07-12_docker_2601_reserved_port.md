# Debug Log：Docker 2601 端口被 Windows 保留

## Problem

执行 `docker compose up -d --build` 时，镜像构建成功，但容器启动失败：

```text
ports are not available: exposing port TCP 0.0.0.0:2601
listen tcp 0.0.0.0:2601: bind: An attempt was made to access a socket in a way forbidden by its access permissions.
```

## Steps To Reproduce

```powershell
docker compose up -d --build
```

## Expected Vs Actual

- Expected：容器启动，医生端可通过 `http://127.0.0.1:2601/static/doctor.html` 访问。
- Actual：Docker 无法绑定宿主机 `2601` 端口，容器未启动。

## Root Cause

Windows 当前保留了 TCP `2526-2625` 端口范围：

```text
Start Port    End Port
2526          2625
```

`2601` 位于该保留范围内，因此即使没有进程占用，也不能被 Docker 绑定。

## Fix

- Docker 默认宿主机端口改为 `2626`，容器内部端口仍为 `8000`。
- `docker-compose.yml` 改为 `${MRA_HOST_PORT:-2626}:8000`，支持通过环境变量切换端口。
- 新增 `scripts/check_docker_port.py`，启动前可检查端口是否可绑定。

## Verification

```powershell
python scripts\check_docker_port.py --port 2626
docker compose up -d --build
curl http://127.0.0.1:2626/health
curl -I http://127.0.0.1:2626/static/doctor.html
```

## Notes

历史文档中的 Docker `2601` 记录保留为当时验收证据。当前可运行入口以 `2626` 为准。
