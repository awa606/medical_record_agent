# Hardware Architecture、接口与供电方案

## Block Definition

```text
医生电脑 / MRA-ALPHA-DEV-01
Chrome / Edge + USB Audio + Doctor Workbench
                  │
             Gigabit LAN
                  │
MRA-ALPHA-ENV-01 Rev.2 / Jetson Orin Nano Super 8GB
FastAPI + FunASR + Local LLM + SQLite + Record Storage
```

可编辑图见 [alpha-edge-terminal-hardware-block.drawio](alpha-edge-terminal-hardware-block.drawio)。

## Interface Matrix

| From | To | Physical Interface | Power | Software Contract | Compatibility Evidence | Verification |
|---|---|---|---|---|---|---|
| 19 V 原装适配器 | Jetson J16 | 5.5 × 2.5 mm DC barrel，中心正极 | 套件输入；板载 DC 输入允许 9–20 V | 开机与功耗模式 | NVIDIA Carrier Spec | 铭牌、极性、开机、满载无重启 |
| Jetson | 512 GB NVMe | M.2 Key-M 2280，PCIe 3.0 x4 | 板载供电 | Jetson Linux block device | NVIDIA Hardware Layout | `lsblk`、SMART、容量、重启持久化 |
| Jetson | 路由器/交换机 | RJ45 GbE | 无额外供电 | TCP/IP，固定主机名或 DHCP reservation | 官方 GbE 接口 | Link 1 Gbps、ping、API、断网 |
| 医生电脑 | USB 音频 | USB/UAC，型号待核实 | USB 总线供电 | Chrome/Edge `getUserMedia` | 当前只有资产线索 | 设备枚举、权限、双人样本、削波/噪声 |
| 医生电脑 | Jetson | LAN 上 HTTPS/API | 各自供电 | Workbench→FastAPI | 需部署证书与地址 | 上传、SSE、审核、导出 |
| 临时显示器 | Jetson | DisplayPort | 显示器独立供电 | UEFI/首次安装 | NVIDIA Hardware Layout | 启动菜单与安装画面 |
| 安装电脑/U盘 | Jetson | USB ISO 或 USB-C recovery | USB 总线/Jetson供电 | JetPack 安装流程 | NVIDIA Quick Start/BSP | 固件版本、介质校验、安装日志 |

## Power Plan

1. 默认只使用套件 19 V 原装适配器；不另购替代电源。
2. 断电状态连接 NVMe、USB、DP 和网线；NVIDIA 规范要求连接/拆卸内部或扩展设备前去除电源。
3. 上电前确认适配器铭牌、插头尺寸和中心正极。
4. Bring-up 记录空闲/ASR/LLM 三阶段功耗、温度与降频；不以标称 TOPS 推断供电与热稳定性。
5. 不加入电池、UPS 或 PoE；这些对 Alpha 核心闭环并非必要。

## LAN Plan

- 优先复用已有 Cat5e/Cat6 成品线和路由器；实物未核对前保持 Open。
- Jetson 使用独立设备名与受控地址；医生电脑只通过局域网访问。
- 麦克风权限要求浏览器安全上下文，部署时使用受信任 HTTPS 或合规本地安全上下文。
- 断网测试切断外部网络，同时保留医生电脑到 Jetson 的局域网通信。

## USB Audio Plan

- 默认复用现有六麦阵列，前提是确认型号、USB/UAC、驱动、浏览器识别和线缆。
- 麦克风接医生电脑，避免在 Jetson 端增加桌面音频路由与驱动变量。
- 讯飞或其他阵列不是默认采购项；只有固定距离 A/B 测试证明现有设备无法达到 ASR/角色门禁目标时再进入候选。
- 角色识别不能由麦克风型号自动保证，仍需人工真值和软件门禁验证。

## Software Boundary

- JetPack 6.2.3 与 7.2.1 都保留候选。1.2 实机 Bring-up 必须记录实际固件、Jetson Linux、CUDA、PyTorch、NVIDIA Container Toolkit、Docker、FunASR 与 Ollama 版本。
- x86 CPU 镜像不能直接当作 Jetson ARM64/CUDA 镜像使用。
- `/health` 只证明服务活性；`/ready` 必须探测真实 Provider、模型缓存、存储和运行目录。
