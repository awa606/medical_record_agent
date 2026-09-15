# Alpha 最小采购 BOM 与报价闭环

> 采样时间：2026-09-15 16:00 +08:00
> 价格口径：公开下单页。准确型号、价格、税费、库存或交期、运费/包邮五项缺一即为 `REFERENCE ONLY`。价格会变化，交易前必须重新核验。

## 成本口径

```text
Required 含税运费小计 + 10% Contingency = Total New Purchase Cost
```

现有电脑、网络设备和已有采音设备不计入 3000 元新增边缘终端采购预算。缺价不是 0 元，也不以 NVIDIA 建议价代替成交价。

## BOM-A · 推荐组合（国内渠道优先）

| ID | 类别 | 准确型号 / 规格 | 数量 | 单价 | 税费 | 运费 | 库存 / 交期 | 证据状态 | 来源与验证 |
|---|---|---|---:|---:|---|---|---|---|---|
| A01 | Required | NVIDIA Jetson Orin Nano Super Developer Kit 8GB；中国区料号应核对 `945-13766-0000-000` | 1 | ¥3,199.00 | 页面称含税并支持发票 | 未披露 | 现货 0；订货库存 100；预计 12–14 周 | REFERENCE ONLY | [iCEasy 下单页](https://www.iceasy.com/product/JETSON_ORIN_NANO_SUPER_DEVELOPER_KIT)未同时显示制造商料号与运费；到货须核对 SKU、8GB、原装电源和散热 |
| A02 | Required | Lenovo KTN8 512GB，M.2 2280 NVMe PCIe 3.0 | 1 | ¥568.99 | 页面片段未闭合 | 未披露 | 未闭合 | REFERENCE ONLY | 公开零售搜索结果；必须复核单面颗粒、下单页库存、税费和运费 |
| A03 | Required | Waveshare `JETSON-ORIN-CASE-A`，SKU 25334 | 1 | ¥79.21 | 未披露 | 未披露 | 现货 0；订货库存 100；约 7 个工作日 | REFERENCE ONLY | [厂商页](https://www.waveshare.com/product/jetson-orin-case-a.htm) / [iCEasy](https://www.iceasy.com/product/1958426344982781954)；兼容声明成立，底部 2280 NVMe 净空仍需实物确认 |
| A04 | Development Tool | ≥16GB USB 安装盘 | 1 | 待核实物 | — | — | Existing Asset candidate | PENDING | 缺失时才采购；不作为终端运行部件 |
| A05 | Required capability | Cat5e/Cat6 网线与现有路由器 | 1 | Existing Asset | — | — | 待实物核对 | COMPATIBILITY PENDING | 1Gbps Link、ping 和 API 访问实测 |
| A06 | Required capability | 现有六麦阵列，接医生电脑 | 1 | Existing Asset | — | — | 型号未提供 | COMPATIBILITY PENDING | 不阻塞计算盒借机；后续核对 USB/UAC、浏览器识别和双人拾音 |

已知参考小计（A01+A02+A03）为 `¥3,847.20`，加 10% 为 `¥4,231.92`。由于 A01–A03 均缺至少一项有效报价字段，该数值仅用于说明当前公开价格风险，不是完整可下单总价。

## BOM-B · 独立渠道与退路组合

| ID | 类别 | 准确型号 / 规格 | 数量 | 单价 | 税费 | 运费 | 库存 / 交期 | 证据状态 | 来源与验证 |
|---|---|---|---:|---:|---|---|---|---|---|
| B01 | Required | NVIDIA `945-13766-0005-000` Jetson Orin Nano Super Developer Kit 8GB | 1 | ¥5,930.68 | 含税 ¥6,701.67 | 需下单确认 | 有库存；885 件从其他地点发货，具体交期待地址 | REFERENCE ONLY | [RS 中国](https://www.rsonline.cn/web/p/processor-development-tools/2647384)；型号、税额和库存明确，运费/交期未闭合 |
| B02 | Required | Colorful CN600 512GB，M.2 2280 NVMe PCIe 3.0 x4 | 1 | ¥539.00 | 页面片段未闭合 | 未披露 | 未闭合 | REFERENCE ONLY | 公开零售搜索结果；须核单面、温度、下单页库存、税费和运费 |
| B03 | Required | 开源 Jetson Orin Nano Super Desktop Case（STEP） | 1 | 待本地加工报价 | — | — | 未报价 | PARTIAL | [GitHub 源文件](https://github.com/crussella0129/Jetson-Orin-Nano-Super-Case)；可编辑、有风道与 NVMe 空间，材料/打印/五金成本未知 |
| B04 | Development Tool | ≥16GB USB 安装盘 | 1 | 待核实物 | — | — | Existing Asset candidate | PENDING | 与 A04 相同，不重复采购 |
| B05 | Required capability | Cat5e/Cat6 网线与现有路由器 | 1 | Existing Asset | — | — | 待实物核对 | COMPATIBILITY PENDING | 与 A05 相同 |
| B06 | Required capability | 现有六麦阵列，接医生电脑 | 1 | Existing Asset | — | — | 型号未提供 | COMPATIBILITY PENDING | 与 A06 相同 |

## 套件包含关系

| 组件 | 是否包含在 Jetson 套件 | 是否另行计价 | 核验 |
|---|---:|---:|---|
| Orin Nano 8GB 计算模组 | 是 | 否 | 到货核对料号与 8GB 共享内存 |
| 官方参考载板 | 是 | 否 | 核对 USB、GbE、DP、M.2 |
| 原装主动散热 | 是 | 否 | 风扇、散热器和线缆检查 |
| 19V 电源 | 是 | 否 | 铭牌、插头和极性核对 |
| 无线模块 | 是 | 否 | 不替代首选有线链路 |
| NVMe / microSD | 否 | 是 | 本项目采用 512GB 单面 M.2 2280 NVMe |

## 报价判定

- NVIDIA 中国 `¥2,070`是建议价/价格信号，不是同时具备税费、库存、交期和运费的公开可成交报价。
- iCEasy `¥3,199`和 RS 含税 `¥6,701.67`必须保留；它们说明当前可见渠道价格明显高于建议价。
- 两套组合都没有取得满足五项字段的完整公开报价，按项目规则预算分类为 **MARGINAL**，不能声明 `≤¥3,000`。
- 在有效低价渠道出现前，不执行采购；优先借用 Jetson 做 48 小时分层验证。

## Required / Existing / Optional / Tool

- **Required**：Jetson 套件、512GB 单面 M.2 2280 NVMe、安全安装结构、LAN 能力、音频输入能力。
- **Existing Asset**：开发电脑、路由器、显示器、键鼠、已有网线和六麦阵列；六麦为 `COMPATIBILITY PENDING`。
- **Optional**：摄像头、扬声器、电池、触摸屏、机械按键和最终工业外观。
- **Development Tool**：安装 U 盘、临时 DisplayPort 链路和必要时使用的串口工具。
