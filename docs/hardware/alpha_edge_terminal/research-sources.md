# Research Sources

访问日期：2026-09-15。

| Source | Type | Used For | Limit |
|---|---|---|---|
| [NVIDIA Carrier Board Specification v1.3](https://developer.nvidia.com/downloads/assets/embedded/secure/jetson/orin_nano/docs/jetson_orin_nano_devkit_carrier_board_specification_sp.pdf) | Official PDF | 完整/载板机械尺寸、DC、接口、ESD、温度范围 | 需用候选外壳图纸做叠合 |
| [NVIDIA Hardware Layout](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/hardware_layout.html) | Official docs | M.2 2280、USB、GbE、DP、USB-C边界 | 不提供采购报价 |
| [NVIDIA Quick Start](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/quick_start.html) | Official docs | 包装、运行存储、16GB USB、JetPack 7.2.1路径 | 不证明项目依赖兼容 |
| [JetPack 6.2.3](https://developer.nvidia.com/embedded/jetpack-sdk-623) | Official release | Orin的JetPack 6生产基线 | 仍需实机依赖验证 |
| [NVIDIA Docker Setup](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/setup_docker.html) | Official docs | NVIDIA Container Toolkit与GPU容器验证 | 示例镜像不是本项目镜像 |
| [NVIDIA China Product](https://www.nvidia.cn/autonomous-machines/embedded-systems/jetson-orin/nano-super-developer-kit/) | Official product | 2070元参考价、平台定位 | 非含税运费订单报价 |
| [NVIDIA Jetson FAQ](https://developer.nvidia.com/embedded/faq) | Official FAQ | Developer Kit为开发/测试/原型；MSRP $399 | 不代替中国落地报价 |
| [RS China 945-13766-0005-000](https://www.rsonline.cn/web/p/processor-development-tools/2647384) | Distributor | 2026-09-15页面含税价6701.67元 | 仅套件，未形成完整BOM和运费确认 |
| [Waveshare CASE-A/B docs](https://docs.waveshare.com/JETSON-ORIN-CASE-B) | Vendor docs | CASE-A兼容官方开发套件的声明 | 精确内部尺寸与价格未闭合 |
| [Open-source Case](https://github.com/crussella0129/Jetson-Orin-Nano-Super-Case) | Maintained community repo | STEP、NVMe pocket、风道、M3装配线索 | GPL-3.0；需本地测量/制造验证 |

搜索停止条件已经满足：官方套件/载板事实明确，外壳已有三条可比较路线；剩余关键差异必须通过候选图纸、报价或实物实验回答，继续泛搜不会关闭 Gate。
