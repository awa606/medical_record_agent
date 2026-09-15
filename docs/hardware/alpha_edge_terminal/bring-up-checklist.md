# Bring-up Checklist

## 0. Identity and Safety

- [ ] 设备编号 `MRA-ALPHA-ENV-01 Rev.2` 与资产记录一致。
- [ ] 套件 P/N、板卡、内存、风扇、电源铭牌和 NVMe 型号已记录。
- [ ] 绝缘固定、ESD、螺钉长度、接口开口与风道检查通过。

## 1. Hardware / SSD

- [ ] 风扇可自由转动，无线缆进入叶片。
- [ ] NVMe 被 UEFI/系统识别，SMART 无错误。
- [ ] 运行分区、模型缓存和数据目录建立；部署后可用空间 ≥100GB。

## 2. Firmware / JetPack / CUDA

- [ ] 记录 UEFI/QSPI、`/etc/nv_tegra_release`、JetPack、CUDA、TensorRT 和内核。
- [ ] 选择 JetPack 6.2.3 或 7.2.1 的依据已写入记录。
- [ ] `tegrastats` 可采样；功耗模式明确。

## 3. Docker Runtime

- [ ] Docker 与 NVIDIA Container Toolkit 安装成功。
- [ ] Jetson兼容容器能看到 CUDA/GPU；镜像架构为 arm64。
- [ ] Compose 配置通过，数据卷位于 NVMe。

## 4. Network / Audio

- [ ] GbE link、IP、ping、DNS/离线边界验证。
- [ ] 医生电脑可访问 Jetson HTTPS/API。
- [ ] 六麦阵列或批准 USB 麦克风被 Chrome/Edge 识别并完成双人短录音。

## 5. FastAPI / ASR / LLM

- [ ] `/health` 与 `/ready` 含真实 Provider 状态。
- [ ] FunASR upload profile 从本地缓存加载，无 Mock/云回退。
- [ ] 真实音频成功转写并保存输入哈希与运行日志。
- [ ] 本地 LLM 返回合法结构化输出，无 Mock/云回退。
- [ ] ASR→释放/切换→LLM 的共享内存行为可见。

## 6. Thermal / Stability

- [ ] 冷启动、ASR、LLM、串行 E2E 的峰值内存/温度/功耗已记录。
- [ ] 30分钟就绪采样无 OOM、swap 持续增长、降频或重启。
- [ ] 失败后数据、任务和模型缓存可恢复。

任一关键项失败时，1.2 保持 `BLOCKED`，不转入 VERIFY。
