# 普通医院 Windows 电脑配置基线

本文用于 `v0.5.4` 本地模型评测阶段，目标是为 Medical Record Agent 的医院端部署给出一个可验证的硬件基线。这里的配置是基于公开采购线索和项目推断，不等同于任何一家医院的最终实机配置；最终结论必须以医院电脑采集表和本地复测为准。

## 公开线索

| 来源 | 可用线索 | 对本项目的意义 |
| --- | --- | --- |
| 中央国家机关台式计算机批量集中采购配置标准 2024 | Intel/AMD 档出现 `i5-12500` 或 `Ryzen5 5600G`，内存至少 16GB，固态存储至少 512GB，显示器 23.8 英寸，Windows 10 神州网信版为可选操作系统。 | 可作为普通政采办公台式机的参考下限。 |
| 信息类产品政府采购需求标准 2023 | 台式机要求内存插槽满配最高容量至少 16GB，固态盘至少 1 个，固态容量至少 240GB，若配置独显显存至少 1GB。 | 说明政府采购办公电脑通常强调可扩展性、SSD 和基础显卡能力。 |
| 北京大学肿瘤医院内蒙古医院 2026 年信息化项目需求意向 | 外网办公电脑需求包含 8 核 16 线程 CPU、16GB 内存、512GB SSD + 1TB SATA、2GB 显卡、千兆网卡。 | 医院信息化采购中，16GB 内存和 512GB SSD 已是常见办公/终端配置。 |
| 武汉大学口腔医院采购需求 | 一体机线索包含 Windows 10 64 位、8GB DDR4、1TB + 256GB M.2 SSD、集显。 | 部分医院终端仍可能只有 8GB 内存，因此本项目最低基线不能假设都有独显或 32GB 内存。 |

## 合理推断配置

| 档位 | 建议配置 | 本项目定位 | 预期可运行能力 |
| --- | --- | --- | --- |
| 最低可验证档 | Windows 10/11，Intel i3/i5 或 Ryzen 3/5，8-16GB 内存，256-512GB SSD，集成显卡 | 老旧门诊/护士站终端 | 可以跑网页、上传、SSE、规则、mock；真实本地 ASR 可能延迟较高，只适合短音频验证。 |
| 普通医院办公 PC 基线 | Windows 10/11，Intel i5-12500 / Ryzen5 5600G 或近似 6 核以上 CPU，16GB 内存，512GB SSD，集成显卡 | 本项目最低交付基线 | 优先评测 FunASR、SenseVoice、Whisper CPU-only；可跑短到中等长度音频，Qwen3-ASR 只做可用性尝试。 |
| 推荐门诊工作站 | Windows 10/11 或 Linux，8-16 核 CPU，32GB 内存，1TB SSD，NVIDIA 8-12GB VRAM | 本地 ASR + 小模型试点 | 支持较稳定的本地 ASR、批量评测、长音频和后续轻量 LLM。 |
| 边缘端/高配试点 | 8-16 核 CPU，32-64GB 内存，1TB NVMe，NVIDIA 12-16GB 以上 VRAM 或边缘 GPU/NPU | 离线部署、隐私隔离、方言/多语种试点 | 适合复测 Qwen3-ASR、SenseVoice、Whisper/faster-whisper、多说话人分离和本地 LLM。 |

## 医院实机采集表

| 字段 | 采集值 |
| --- | --- |
| 医院电脑类型 | 待填写：门诊普通办公 PC / 护士站 PC / 医生工作站 / 边缘设备 |
| 操作系统 | 待填写 |
| CPU 型号 | 待填写 |
| CPU 核心/线程 | 待填写 |
| 内存 | 待填写 |
| 硬盘类型与容量 | 待填写 |
| 是否有独显 | 待填写 |
| GPU 型号与显存 | 待填写 |
| 是否允许安装 Python | 待填写 |
| 是否允许安装 ffmpeg | 待填写 |
| 是否允许本地模型缓存 | 待填写 |
| 是否允许外网下载模型 | 待填写 |
| 麦克风/音频输入方式 | 待填写 |
| 本地部署限制 | 待填写 |

## v0.5.7 本机实测映射

当前开发机为 24 逻辑核心、约 31GB 内存、CPU-only。三条中文医患样本同口径评测显示：

| 模型 | 本机结果 | 对普通医院 PC 的推断 |
| --- | --- | --- |
| SenseVoice | 三样本平均 CER `0.166945`、平均 RTF `0.155381`、峰值 RSS `4297.01 MB` | 优先作为 v0.6 默认候选；16GB 办公 PC 有机会运行，但仍需实机复测。 |
| FunASR | 三样本平均 CER `0.195247`、平均 RTF `0.182726`、峰值 RSS `4626.28 MB` | 可作为稳定 fallback；适合普通话医患样本 baseline。 |
| Qwen3-ASR | 三样本平均 CER `0.550381`、平均 RTF `0.485806`、峰值 RSS `10502.26 MB` | 当前不建议作为普通医院 PC 默认模型；更适合 GPU/边缘端和研究路线复测。 |

结论：在没有医院实机的阶段，前端产品化和本地部署优先围绕 SenseVoice/FunASR 做可交付闭环；Qwen3-ASR 保留在模型评测和边缘端优化路线中。

## 结论

- `v0.5.4` 的医院 PC 基线按“普通 Windows 办公 PC”处理：16GB 内存、512GB SSD、集成显卡是当前最稳妥的最低交付假设。
- 真实本地 ASR 选择先以 FunASR、SenseVoice、Whisper CPU-only 做延迟和准确率对比；Qwen3-ASR 进入 Python 3.12 独立环境复测。
- 方言、多语种、多人物分离不能只靠普通办公 PC 下结论，必须在推荐工作站或边缘端配置上补充复测。
- 所有配置结论都必须标注“公开线索”“合理推断”或“医院实测”，不能混写。

## 参考资料

- [Qwen3-ASR-0.6B 模型卡](https://huggingface.co/Qwen/Qwen3-ASR-0.6B)
- [AISHELL OpenSLR SLR33](https://www.openslr.org/33/)
- [LibriSpeech OpenSLR SLR12](https://www.openslr.org/12/)
- [中央国家机关台式计算机批量集中采购配置标准 2024](https://cgxx.ecnu.edu.cn/cms/contentwh/download.htm?attachmentid=2924b2685a6f48cb9c9bdf567c04be25)
- [信息类产品政府采购需求标准 2023](https://gks.mof.gov.cn/guizhangzhidu/202312/P020260130468060065055.pdf)
- [北京大学肿瘤医院内蒙古医院 2026 年信息化项目需求意向](https://www.nmgzlyy.cn/m/ywgk/Info/7943)
- [武汉大学口腔医院项目采购需求](https://www.whuss.com/attachments/M/Ml/MldE/MldEAJPQYBLyn5PnZUxVR2dSgmMb3j2iRzjhU1SS.pdf/MldEAJPQYBLyn5PnZUxVR2dSgmMb3j2iRzjhU1SS.pdf?filename=%E9%A1%B9%E7%9B%AE%E9%87%87%E8%B4%AD%E9%9C%80%E6%B1%82+%282%29.pdf)
