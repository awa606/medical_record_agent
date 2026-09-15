# Docker Desktop运行端点恢复记录

## 现象

2026-09-15恢复资源Spike时，Docker Desktop 4.80.0（build 232116）在Linux引擎启动前退出。后端日志先后指出：

- `%LOCALAPPDATA%\Docker\run\dockerInference` 无法删除；
- 修复第一处后，`%LOCALAPPDATA%\docker-secrets-engine\engine.sock` 出现同类错误；
- 两个对象均为0字节、`Archive, ReparsePoint`，`fsutil reparsepoint query`返回Windows错误1920。

这与Docker公开issue中的畸形运行端点故障一致，不是项目镜像、Compose或应用代码错误。

## Hypothesis → Test → Result → Conclusion

| 项目 | 内容 |
|---|---|
| Hypothesis | Docker非正常退出后遗留了当前进程无法清理的Windows Unix socket，Inference/Secrets初始化因此中止。 |
| Minimal Test | 完全停止Docker Desktop；只读检查对象类型、后端日志、WSL状态和Docker数据VHDX。 |
| Result | 两个端点均不可单独读取；Docker数据VHDX仍存在，大小90,340,065,280字节；Ollama缓存仍存在。 |
| Fix | 将只含瞬态socket的两个父目录原位改名留档，重新建立空目录；未删除备份、镜像、卷或VHDX。 |
| Verification | `docker info`恢复，Engine 29.6.1可用，原有容器重新可见，Phase B随后完成3/3音频转写。 |
| Conclusion | 根因为Docker Desktop Windows运行端点损坏；可逆隔离端点恢复了引擎。 |

## 数据保护说明

- 未执行`docker system prune`、卷清理、镜像删除或VHDX删除。
- 启动失败窗口的后端日志记录过一次“Reset to factory defaults”动作；本轮没有从命令行发出该动作。随后核对确认Docker数据VHDX及Ollama模型缓存仍存在，但部分Docker Desktop用户设置和CLI辅助目录被重建。
- 修复前设置SHA256为`6722B23DBCF3F6D1ABE60C88367FFCDED665DF44455A3DA60088ACB85D04BB06`；重建后为`D4EC5EB3E45C8192AEC3126D9341A288B25FB3ED5FA544EC61443D3ED5813776`。
- 畸形端点目录仍保留在本机，未提交Git；确认长期稳定后再由用户决定是否清理。

## 参考

- [Docker Desktop故障排查](https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/)
- [Docker Desktop malformed dockerInference issue #625](https://github.com/docker/desktop-feedback/issues/625)
- [Docker Desktop Inference manager issue #342](https://github.com/docker/desktop-feedback/issues/342)
