# 外壳 MVP 适配结论

## 主选 · Waveshare JETSON-ORIN-CASE-A

| 检查 | 证据 | 结论 |
|---|---|---|
| 官方开发套件兼容 | 厂商文档明确声明 CASE-A 兼容 NVIDIA 官方 Jetson Orin Nano 开发套件 | PASS |
| 安装孔 | 厂商装配说明要求移除原塑料底座后，以 M2.5 螺钉将官方套件直接固定到底壳 | PASS |
| 原装散热器 | 产品页保留顶部原装风扇孔并提供三侧通风 | PASS |
| 接口可访问 | 产品页声明精确开口；A/B 型号差异仅为前后面板开口，A 对应官方载板 | PASS |
| 进排风 | 顶部风扇孔与三侧通风明确 | PASS FOR DESIGN |
| J11 下置 2280 NVMe | 官方载板确认 J11 位于底面且仅支持单面 M.2；厂商装配图证明底壳支柱空间，但未给 SSD 厚度/散热片净空 | PARTIAL |
| 可拆装 | 厂商提供分步装配与可恢复原底座说明 | PASS |
| 价格 | 厂商 $11.99；国内参考 ¥79.21，税费/运费不完整 | REFERENCE ONLY |

**适配结果：PARTIAL。** 厂商已经证明板卡、安装孔、接口、原装风扇和通风适配；J11 单面 2280 NVMe 的实际厚度、散热片和底壳净空仍需借机或到货后确认。它是主选验证对象，但在实物叠合前不写成 `FIT`。

## 备选 · 开源 Jetson Orin Nano Super Desktop Case

- 项目提供 STEP、风道和 NVMe 空间，可作为本地加工退路。
- 许可证、源文件和修改边界可追踪；仍缺本地加工、五金、材料和交期报价。
- **适配结果：PARTIAL。** 保留为退路，不启动最终 CAD 或本地加工。

## Digital Overlay Result

以 NVIDIA 完整套件 `103 × 90.5 × 34.77 mm`、底面 J11 2280 单面 NVMe、Waveshare 直接螺钉安装和顶部/三侧风道做静态叠合：板卡、孔位、主要接口、原装散热和拆装路径闭合；SSD 实际厚度与热垫空间未闭合。因此 G4 Mechanical 为 `VERIFY`，不是 `BLOCKED`，采购决策转入 `BORROW-FIRST`。

找到这一主选后停止外壳搜索。最终 3D 打印外壳留到 Alpha+/Beta。

## Sources

- [Waveshare CASE-A 产品页](https://www.waveshare.com/product/jetson-orin-case-a.htm)
- [Waveshare CASE-A/B 兼容说明](https://docs.waveshare.com/JETSON-ORIN-CASE-B)
- [Waveshare 装配说明](https://docs.waveshare.com/JETSON-ORIN-CASE-B/Assembly-Guide)
- [NVIDIA 载板机械规格](https://developer.nvidia.com/downloads/assets/embedded/secure/jetson/orin_nano/docs/jetson_orin_nano_devkit_carrier_board_specification_sp.pdf)
- [开源备选外壳](https://github.com/crussella0129/Jetson-Orin-Nano-Super-Case)
