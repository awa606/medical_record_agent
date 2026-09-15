# Hardware Verification Plan

| ID | Verification | Input / Procedure | Pass Criteria | Evidence |
|---|---|---|---|---|
| HV01 | BOM identity | 逐件核对 P/N、数量、包装与资产编号 | 与批准BOM一致；无漏件/重复计价 | `bom-receipt.json`、匿名照片 |
| HV02 | Mechanical fit | 装入NVMe、支架/外壳，插拔全部Required接口 | 无干涉、短路或板弯；SSD/风扇可维护 | 尺寸记录、装配照片 |
| HV03 | Power | 原装19V上电，空闲/ASR/LLM观察 | 无异常发热/重启；风扇正常 | 电源铭牌、日志 |
| HV04 | Storage | 安装/识别/读写/重启 | 512GB NVMe稳定；部署后≥100GB余量 | SMART、`lsblk`、容量 |
| HV05 | LAN | 1GbE与API传输、外网断开 | 医生电脑到Jetson稳定；离线不走云 | link/ping/API日志 |
| HV06 | USB Audio | 固定距离双人录音 | 浏览器识别；无削波；文件可追踪 | 音频哈希、设备摘要 |
| HV07 | JetPack/CUDA | 固件、JetPack、GPU容器 | 版本冻结；容器内CUDA有效 | 环境清单、容器摘要 |
| HV08 | ASR load | 真实本地模型+固定音频 | 无Mock/云；输出有效；资源受控 | 转写指标、资源CSV |
| HV09 | LLM load | 固定结构化输入 | 合法Schema；无Mock/云；可卸载 | 输出哈希、时延、驻留状态 |
| HV10 | Sequential E2E | ASR→资源切换→LLM | 无OOM/持续swap；阶段峰值在预算内 | 每秒资源采样 |
| HV11 | Thermal stability | 30分钟代表性负载 | 无热降频、失联或重启 | `tegrastats`、环境温度 |
| HV12 | Serviceability | 断电后换SSD/清风扇演练 | 无需拆载板即可完成；复装通过 | SOP执行记录 |
| HV13 | Cost closure | 两份完整含税运费报价 | Total New Purchase Cost≤3000 | 报价、公式、时间戳 |

## Result Rules

- 结果仅允许 `PASS / FAIL / BLOCKED / NOT TESTED`。
- 开发机证据只能作为 Resource Feasibility Estimate，不计 HV07–HV12 的 Jetson PASS。
- 任何硬件实测都记录设备、环境、Git SHA、模型摘要、执行者、时间与原始日志。
- 原始音频、身份、数据库和密钥留在受控本地，不提交 Git。
