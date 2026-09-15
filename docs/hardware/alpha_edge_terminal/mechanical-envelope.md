# Mechanical Envelope、内部布局与散热要求

## Official Envelope

| Object | Width | Depth | Height | Source |
|---|---:|---:|---:|---|
| Carrier board | 100.00 ± 0.13 mm | 79.00 ± 0.13 mm | board stack figures 16.70 mm max / 4.30 mm max | NVIDIA Carrier Spec v1.3 Fig. 4-1 |
| Complete developer kit | 103.00 ± 0.20 mm | 90.50 ± 0.20 mm | 34.77 ± 1.09 mm | NVIDIA Carrier Spec v1.3 Fig. 4-2 |

外壳适配使用完整开发套件包络，不使用较小的裸载板数值代替散热器、支架和脚垫占用。

## Concept Internal Envelope

数字 Spike 使用以下显式假设：

- X/Y 每侧结构余量 5 mm：`113 × 100.5 mm`。
- 顶部风道净空 20 mm。
- 底部 NVMe、绝缘与服务净空 8 mm。
- 由此得到概念内部高度下限：`34.77 + 20 + 8 = 62.77 mm`。

这组数值只用于判断是否能形成低风险桌面盒，不是现成外壳的已验证内部尺寸，也不是最终 CAD。

## Keep-out and Service Zones

| Zone | Requirement | Current Evidence | Closure |
|---|---|---|---|
| Top fan intake | 风扇正上方无遮挡，顶部净空和开孔面积待热测试确认 | 原装主动散热 + 概念20mm净空 | PARTIAL |
| Exhaust | 至少一个侧/后排风路径，不让热风短路回进风 | 方案要求 | OPEN |
| Bottom NVMe | 仅使用单面2280、螺钉、可能的薄型热垫和拆装空间 | 官方底部J11位置及单面M.2限制；CASE-A底壳支柱装配 | PARTIAL · 实物关闭 |
| DC jack | 直插头与应力释放，插拔不压迫壳体 | 官方位置；CASE-A精确开口声明 | PASS FOR DESIGN |
| RJ45 | 水晶头卡扣可按压，线缆弯曲不顶壳 | 官方位置；CASE-A对应官方载板面板 | PASS FOR DESIGN |
| USB-A stacks | 四口全部可插拔；相邻大尺寸接头不冲突 | 官方位置；CASE-A对应官方载板面板 | PASS FOR DESIGN |
| DisplayPort | 首装调试可接；不由USB-C替代 | 官方位置；CASE-A对应官方载板面板 | PASS FOR DESIGN |
| USB-C recovery | 可接安装/恢复线 | 官方位置；CASE-A对应官方载板面板 | PASS FOR DESIGN |
| Mounting holes | 支柱、孔位、螺钉长度与绝缘垫片匹配 | CASE-A装配说明直接用M2.5螺钉固定官方套件 | PASS FOR DESIGN |
| Service clearance | 拆盖后可换SSD、清风扇，不先拆载板 | 可逆分步装配已证明；SSD更换动作待实物 | PARTIAL |

## Internal Layout

- 上层：原装散热器与风扇，保持进风净空。
- 中层：完整 Jetson 开发套件，使用绝缘支柱固定。
- 下层：底部 M.2 2280 NVMe 与薄型散热/绝缘区。
- 后/侧：DC、RJ45、USB、DP、USB-C 对应独立开口和外部线缆服务区。
- 外部：医生电脑、USB 麦克风与路由器，不塞入边缘盒内部。

## Thermal Requirements

1. 保留套件主动散热与原风扇控制。
2. 外壳不覆盖风扇入口，排风路径不短路。
3. 温度验证记录环境温度、`tegrastats`、功耗模式、频率和 throttling。
4. ASR、LLM 各自持续运行及串行切换都要采样；单次启动成功不能关闭热风险。
5. 未取得实机 30 分钟稳定性与峰值温度前，Thermal closure 保持 Open。
