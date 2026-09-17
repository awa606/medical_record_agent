# Alpha Edge AI 终端 BOM 参考基线

> **REFERENCE ESTIMATE ONLY**
>
> **NOT PURCHASE QUOTE**
>
> **PURCHASE STATUS: DEFERRED**
>
> **REAL PURCHASE COST: NOT VERIFIED**

本文件冻结硬件支线的工程估算，供后续恢复 Jetson 实机验证时参考。它不构成采购建议、成交报价或预算验收证据。本轮停止继续搜索报价、外壳和开发机 Jetson 模拟。

## 估算口径

预算只计算新增 Edge Terminal 必需硬件；当前电脑、显示器、键鼠、既有网络和现有六麦阵列属于 Existing Asset，不计入新增采购价。

| 项目 | 分类 | 工程估算（RMB） | 说明 |
| --- | --- | ---: | --- |
| Jetson Orin Nano Super 8GB Developer Kit | Required | 2,070 | NVIDIA 中国页面参考价；不是可成交价 |
| 512GB NVMe M.2 2280 | Required | 180–260 | 具体品牌、耐久度和含税运费待采购时核验 |
| 兼容外壳或安全绝缘安装结构 | Required | 100–180 | 实机机械净空尚未核验 |
| Cat6 网线 | Required / Reusable | 15–30 | 有可用现货时复用 |
| 32GB+ 系统安装 U 盘 | Development Tool | 25–45 | 与运行存储分开 |
| 螺柱、固定件和小配件 | Required | 20–40 | 按实际装配清单核验 |
| 六麦阵列 | Existing Asset | 0 新增采购 | 型号和兼容性待核验 |
| 显示器、键鼠、现有电脑和网络 | Existing Asset | 0 新增采购 | 不属于目标计算盒采购成本 |

## 计算结果

- 新增采购小计：`¥2,410–2,625`
- Prototype Contingency：`10%`
- 含预留参考总额：`¥2,651–2,888`

公式：

```text
Required New Purchase Subtotal × 1.10 = Reference Total
```

## ¥3,000 预算临界值

含 10% 预留时，税前采购小计上限为：

```text
¥3,000 ÷ 1.10 = ¥2,727.27
```

扣除最低外围成本 `¥340` 后，Jetson 实际成交价需约为：

```text
¥2,727.27 - ¥340 = ¥2,387.27
```

因此只有在开发套件实际含税运费成交价约 `≤¥2,387`、外围部件取最低可验证价格且复用六麦阵列时，完整方案才可能满足含 10% 预留的 `¥3,000` 目标。公开渠道价格高于该阈值时，预算结论必须重新计算。

## 恢复条件

硬件支线恢复时必须重新采样准确型号、含税价格、运费、库存和交期。任何缺项都不得把本参考估算升级为采购 PASS。
