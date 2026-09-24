# WBS 5.1：V3.4 工作台与离线恢复候选

V3.4 三栏版式已获用户认可并接入真实业务。DEV-01 的文本、上传音频、物理麦克风三条路径各完成一次生成、医生修改、审核和 DOCX 导出；[匿名结果](20260924_alpha51_real_three_path_smoke.json)为 3/3。音频路径使用真实 FunASR，三条路径使用本地 Ollama `qwen3:4b`，没有 Mock 或云端回退。这是工程 Smoke，不是临床准确性或 Jetson 验收。

## 最终归档

| 项目 | 结果 |
|---|---|
| 本地归档 | `C:\Users\AWA007\Desktop\Data\开题报告\病历\01_STABLE_BASELINES\alpha-demo-m4-rc1-r5` |
| 归档源 Git SHA | `b8d01eecdfc3cbe53092a6d03631956d6f9a7335` |
| `manifest.json` SHA256 | `1e62974bdcf3c6b0244d20d9e3cc4ab597b6af05ffb2592392a48590a5c20beb` |
| 文件 | 80 项、10,244,433,421 字节；逐文件 SHA256 位于 `sha256sums.txt` |
| 模型 | `qwen3:4b`，Ollama 清单 SHA256 `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`；FunASR 缓存原文件逐项校验 |
| 数据 | 一名合成患者与一次合成就诊；归档内无用户、任务、音频、密码或真实患者数据库 |
| 证据 | 归档内含三路径 JSON、V3.4 匿名截图、许可清单及 SHA 匹配的合成病例 DOCX |

从归档复制到全新 `.artifacts/alpha51-offline-restore-r5-20260924/`，在新端口 `8785` 运行恢复器。`restore-result.json` 记录：`/health=200`、`/ready=200`、医生页面 `200`、应用容器外部连接 `BLOCKED`；模型摘要与上表相同，FunASR 四组件预热完成，SQLite `quick_check=ok`。恢复后的合成病例再次由本地 Qwen 生成到 `WAITING_DOCTOR_REVIEW`。原始运行日志、密码和恢复数据库只留在 `.artifacts`，不进入 Git。

```powershell
python scripts/alpha51_release_archive.py restore `
  --package 'C:\Users\AWA007\Desktop\Data\开题报告\病历\01_STABLE_BASELINES\alpha-demo-m4-rc1-r5' `
  --target '.artifacts\alpha51-offline-restore-new' --port 8786 --timeout 600
```

恢复目标必须是新的空路径，端口必须空闲。归档的 `manifest.json` 保留 `CANDIDATE_UNVERIFIED` 原始状态；只有配套的恢复结果才证明这次运行成功，不能回写归档掩盖此前失败。

## 失败记录与边界

| 尝试 | 原样保留的结果 | 定位与修正 |
|---|---|---|
| 初始包 | Docker Desktop 的 `internal` 网络未向 Windows 主机发布端口 | 增加仅监听 `127.0.0.1`、不挂载模型或运行数据的 HTTP 网关 |
| r2 | CPU 模式 Qwen 探测超时，初期网关连接偶发断开 | 使用开发机 NVIDIA GPU、明确 `OLLAMA_NO_CLOUD=1`，网关改为流式 HTTP 转发；没有放宽 `/ready` |
| r3 | 归档创建时 Python 导入路径错误 | 修复归档脚本；失败包未被标为候选通过 |
| r4 | 新目录 `8784` 恢复、真实探测与合成病例生成通过 | 用于确认修正有效；最终封存的不是此包 |
| r5 | 新目录 `8785` 恢复、真实探测与合成病例生成通过 | 最终工程候选；归档内补齐匿名证据和样例 |

这次验证证明**应用与模型可在服务级隔离网络中使用本地缓存运行**，没有证明主机物理断网。额外探针显示：应用容器外连被阻断，但只监听 loopback 的前端网关仍有外网出口。网关代码仅转发到内部应用、无模型和数据库挂载；在完全禁止每个容器外连的严格口径下，此网络拓扑仍需修正并重测。不得把 `restore-result.json` 的应用容器 `BLOCKED` 写成“所有容器均无外网路由”。

## 验证与剩余项

- Python 全量：`541 passed, 8 subtests passed`；前端语法与 `git diff --check` 通过。
- 样稿交互：76 项通过；锁定截图比较：40 项通过。[视觉记录](20260924_alpha51_visual_verification.md)保留 Chromium 固定环境和有效视口的边界。
- Edge 完成用户现场物理麦克风录音；Chrome 完成三栏几何检查。Edge **实际** 125%/150% 浏览器缩放尚未完成；等效 CSS 视口检查不能替代。
- 原 2600/2666 容器保持停止，2626 现用容器未切换。Jetson 与完整 Alpha M4 Gate 仍未验收。

当前结论是**可恢复工程候选**，不标记为稳定发布版。5.1 的视觉缩放与严格网关断网口径须在 Release Gate 中继续核验，完成前不得启动 5.3 的正式连续五次验收。

## 参考资料

- [Qwen3-4B-Thinking-2507 官方许可](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507/blob/main/LICENSE)
- FunASR 缓存中各模型的 `README.md` 许可字段与 SHA，见归档 `evidence/model_license_inventory.json`。
