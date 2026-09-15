# Enclosure Concept 与候选比较

## Alpha Strategy

Alpha 先满足绝缘、安全固定、原装主动散热、接口可达、SSD可维护和桌面稳定。外观优化推迟到 Alpha+/Beta；本轮不制作最终工业外观 CAD。

## Comparison

| Dimension | Waveshare CASE-A | Open-source STEP Case | Open Insulated Stand |
|---|---|---|---|
| Claimed board fit | 厂商明确声明兼容官方开发套件 | 作者声明面向官方 Super 开发套件 | 按官方包络自行定义 |
| NVMe access | 未取得精确内部图 | README说明有底部NVMe pocket | 完全开放 |
| Original cooling | 待查进/排风截面 | 有fan duct与exhaust设计 | 原装风扇无遮挡 |
| Connector access | CASE-A开口针对官方载板 | 多版本含不同GPIO/按钮开口 | 全开放 |
| Assembly evidence | 有厂商资料，精确装配图待取 | 有STEP和M3装配说明 | 简单支柱装配 |
| Price / landed quote | 缺 | 缺材料/打印/五金报价 | 缺底板/支柱报价 |
| Protection | High | High | Low |
| Rework | Low–Medium | Medium | Low |
| Decision | 未决定 | 未决定 | 回退候选 |

## Decision Boundary

- 若 CASE-A 提供精确尺寸/装配图、确认原装风扇与2280 NVMe净空，并有预算内落地报价，可进入 `REUSE` 候选。
- 若开源 STEP 经尺寸叠合、许可证和本地打印成本验证，且只做有限开口/标识适配，可进入 `ADAPT` 候选。
- 若两者均无法关闭接口、风道或成本，先使用开口绝缘支架完成 Alpha；自定义外壳进入后续阶段。

当前没有足够证据选择 `REUSE / ADAPT / BUILD`。
