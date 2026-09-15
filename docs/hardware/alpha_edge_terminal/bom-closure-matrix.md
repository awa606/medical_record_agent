# BOM Closure Matrix 与 Cost Sheet

## 成本口径

```text
Required 含税运费小计 + 10% Contingency = Total New Purchase Cost
```

Existing Asset Value、Optional Cost 和 Development Tool 单列。缺价不是 0 元；任一 Required 能力未由已核实资产或采购项关闭时，不计算完整总价，也不宣称 `≤3000`。

## Required BOM

| ID | Function | Exact Specification | Interface / Power | Mechanical / Software | Included / External | Price CNY | Source | Alternative / Trade-off | Verification | Closure |
|---|---|---|---|---|---|---:|---|---|---|---|
| R01 | 边缘计算 | NVIDIA Jetson Orin Nano Super Developer Kit 8GB，SKU 到货核对 | 19 V 原装电源；GbE/USB/DP/M.2 | 完整包络约 103×90.5×34.77 mm；JetPack | 独立采购；模组/载板/散热/电源只计一次 | 2070* | NVIDIA 中国参考价，2026-09-15 | 更大内存平台降低 OOM 风险，但大概率超预算 | SKU、包装、序列号、内存、接口 | PARTIAL |
| R02 | 运行存储 | 512 GB，M.2 2280，PCIe NVMe；具体型号待定 | M.2 Key-M，PCIe 3.0 x4；板载供电 | 底部安装、厚度/温度/螺钉待核对；Jetson Linux | External |  | 规格来自 NVIDIA；报价待取 | microSD 成本低但容量、耐久和性能需重评 | 型号、SMART、容量、温度、≥100 GB 余量 | OPEN |
| R03 | 安全固定 | 非导电或绝缘支柱底板；兼容完整套件和 NVMe | 无电气连接 | 不遮挡底部 NVMe、风扇和接口；允许拆装 | External 或候选外壳内含 |  | 候选待定 | 开口底板防护较少；完整外壳风险较高 | 尺寸图、孔位、绝缘、稳固、服务性 | OPEN |
| R04 | 局域网 | 已有 Cat5e/Cat6 + 路由器，长度和端口待核实 | RJ45 GbE | 医生电脑↔Jetson | Existing Asset candidate |  | 实物待核 | 新购成品线可降低资产不确定性 | 型号/长度、1 Gbps link、ping/API | OPEN |
| R05 | 音频输入 | 已有六麦阵列，准确型号/UAC待核实 | USB，接医生电脑；总线供电 | Windows + Chrome/Edge | Existing Asset candidate |  | 实物待核 | 普通 USB 会议麦或阵列采购；需 A/B 而非按品牌决定 | 枚举、权限、双人样本、ASR/角色指标 | OPEN |

\* 2070 元是 NVIDIA 中国页面参考价，不是完整含税运费采购报价。

## Kit Inclusion

| Component | Function | Included in R01 | Separate Purchase? | Evidence / Check |
|---|---|---:|---:|---|
| Orin Nano 8GB 计算模组 | CPU/GPU/共享内存 | Yes | No | 到货核对 P/N 和 8GB |
| 参考载板 | USB/GbE/DP/M.2/供电 | Yes | No | 到货核对板卡版本 |
| 主动散热 | 连续推理热管理 | Yes | No | 风扇、散热器、线缆检查 |
| 无线模块 | 可选网络 | Yes | No | 不替代首选有线链路 |
| 19 V 电源 | 主电源 | Yes | No | 铭牌、插头、极性 |
| NVMe / microSD | 运行存储 | No | Yes | 本项目选择 512GB NVMe |

## Existing Assets

| Asset | Intended Use | Exact Model | Physical Check | Replacement Value | Status |
|---|---|---|---|---:|---|
| MRA-ALPHA-DEV-01 电脑 | 浏览器、开发、回归 | 已登记 Lenovo 开发机；本轮不重新计价 | 已有开发证据 | 单列，不计3000 | VERIFIED FOR DEV ONLY |
| 路由器/交换机 | 局域网 |  | 待核端口/速率 |  | OPEN |
| 显示器 | 首次安装/UEFI |  | 待核 DP 或转接 |  | OPEN |
| 键盘/鼠标 | 首次安装 |  | 待核 |  | OPEN |
| 网线 | LAN |  | 待核类别、长度、完好 |  | OPEN |
| 六麦阵列 | 浏览器采音 |  | 待核型号、USB/UAC、线缆 |  | OPEN |

## Development Tools

| Tool | Requirement | Existing? | Price | Note |
|---|---|---|---:|---|
| 安装U盘 | JetPack 7.2.1 路线要求 16GB 以上 | 待核 |  | 不属于终端运行硬件；无法复用时作为新增工具成本披露 |
| DisplayPort链路 | 显示器或 DP→HDMI 转接 | 待核 |  | USB-C 不输出显示 |
| 串口调试工具 | Headless 固件/启动诊断备用 | 待核 |  | 非默认 Required；无显示链路时启用 |

## Optional

| Item | Why Optional | Trigger to Reconsider |
|---|---|---|
| 完整美观外壳 | 开口绝缘支架已能支撑 Alpha 功能 | 搬运/展示风险或教师要求 |
| 摄像头、扬声器 | 不参与当前录音→病历主链路 | 新范围经 Gate 批准 |
| 电池/UPS | 桌面原型可接市电 | 明确移动/断电要求 |
| 触摸屏、机械按键 | 医生使用现有电脑网页 | 独立一体机范围进入 Alpha+/DVT |

## Quote Comparison

| Quote | Vendor | Required Scope Complete | Tax | Shipping | Total | Captured | Result |
|---|---|---:|---|---|---:|---|---|
| Reference | NVIDIA 中国 | No，仅开发套件参考价 | 未形成交易报价 | 未知 | 2070 | 2026-09-15 | 不能关闭预算 |
| Q-A | RS 中国 | No，仅开发套件 | 页面显示含税 6701.67 | 送货条件需下单确认 | ≥6701.67 | 2026-09-15 | 单项已超预算，Reject as budget source |
| Q-B |  | No |  |  |  |  | 待取得完整含税运费报价 |
| Q-C |  | No |  |  |  |  | 待取得完整含税运费报价 |

## Cost Calculation

- 已知 Required 参考小计：`2070 CNY`。
- 对已知小计计算的 10%：`207 CNY`，已知最低含预留为 `2277 CNY`。
- 若总预算为 3000 元，则在 10% Contingency 口径下，其他 Required 含税运费小计最多约 `657.27 CNY`。
- 由于 R02–R05 未形成完整报价或实物闭环，`Required 含税运费小计`、`Total New Purchase Cost` 和 `Budget Remaining` 均为 `UNKNOWN`。
- **Budget Gate：NEEDS MORE EVIDENCE**。
