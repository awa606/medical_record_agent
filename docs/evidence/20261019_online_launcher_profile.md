# 2026-10-19 在线审核候选启动器适配

## 输入与边界

设计输入：[在线审核候选增量研究与设计](../engineering/20261019_online_demo_review.md)。本批只补启动器的显式配置档，不部署、不停止容器，不修改原本地离线包。模型质量门禁未通过。

## 已实现

- 旧配置缺省 `local_qwen`，原三服务、固定模型清单及摘要验证不变。
- 新配置 `online_deepseek` 仅登记 `app/gateway`；强制 `ONLINE_LLM_PROFILE=deepseek_demo`、`live`、本地 FunASR、`deepseek-flash`、官方 HTTPS 地址、零重试及脱敏开启。密钥只检查是否配置，不写入登记文件，不生成密钥哈希。支持精确 `/run/secrets/deepseek.env` 只读文件挂载；费用和诊断目录必须是 `/app/online-private` 的可写独立挂载，已有文件类型须正确。
- 容器、镜像、挂载、Cookie 和页面资源仍固定；在线地址即使在两种官方合法形式间变化，也要求重新登记。
- 启停、活动环境互斥、空闲检查、锁及失败回退复用原流程；按目标和对端各自的服务清单操作。在线冷启动不会启动 Ollama，回退到本地档时仍使用其原三服务。
- 窗口标题、上下文及状态明确显示云端生成和联网要求；在线未就绪不再提示“本地模型预热”。用户说明见[在线审核候选使用说明](../pilot/online-review-candidate.md)。

`configure` 继续不猜测对端。维护部署需显式登记 `peer_config/switch_lock`，核对两端关系后再交付日常入口。

## 验证

先增加接口和失败保护测试，原实现结果为 **14 failed、1 passed**。实现后补测冷启动、不同服务数量的失败回退、资源指纹和就绪失败。

```powershell
python -m pytest tests/test_doctor_pilot_online.py tests/test_doctor_pilot.py tests/test_dual_environment_controls.py tests/test_offline_pilot_archive.py tests/test_pilot_docs_config.py -q --basetemp=.artifacts/test-tmp-online-launcher
```

初轮结果 **64 passed**。随后按真实 Compose 补上云端 profile 及只读凭据、费用目录契约，最终独立临时目录回归 **77 passed**。覆盖旧配置、双环境、离线归档工具、身份与端口保护、未知 profile、恶意或漂移地址、Mock、非零重试、关闭脱敏、凭据缺失、凭据挂载可写/不存在/类型错误、费用路径绕开，以及线上不加载 Ollama。凭据读取/哈希方法被测试主动禁止，合法只读挂载仍可验证。

Windows PowerShell 实际执行 `-STA -SmokeTest`，窗口控件构建成功；标题、上下文、按钮和 Logo 配置正确。此项未调用启动/停止动作，也不代替实际页面及缩放验收。脚本 AST 语法检查通过。

本地 Smoke 配置位于 `.artifacts/online-launcher-20261019/online-smoke.json`，仅为不含凭据的控件样例，不纳入 Git。

## 尚未证明

本批没有启动在线部署、调用真实 DeepSeek、切换环境或验证真实病历内容。最终运行入口、网络、费用约束、模型输出质量、精确版本完整流程由主任务统一验收；不能由启动器单元测试推定这些项目通过。
