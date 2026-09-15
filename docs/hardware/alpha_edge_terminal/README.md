# Alpha Edge AI 终端硬件工程包

本目录是 WBS `1.4 Edge AI终端硬件集成与结构设计` 的工程事实来源。它定义一台可装配、可启动、可复验的桌面式 Edge AI 医疗终端原型；不声明量产、医疗器械认证、采购完成或 Jetson 实机通过。

> 2026-09-15 Speed Mode结论：**Purchase Decision = BORROW-FIRST**。Research与Design Baseline已收敛；预算为MARGINAL，CASE-A机械适配为PARTIAL。

## 系统边界

- `MRA-ALPHA-DEV-01`：现有开发电脑，负责开发、CI、浏览器操作和快速回归。
- `MRA-ALPHA-ENV-01 Rev.2`：Jetson Orin Nano Super 8GB 候选，负责 FastAPI、ASR、LLM、SQLite 和文件存储。
- 浏览器与 USB 音频在医生电脑侧；两端通过受控局域网连接。
- 当前 Minimal Hardware Purchase Gate：`VERIFY / sufficient for BORROW-FIRST`；目标设备验收仍为 `HARDWARE BLOCKED`。

## 交付物索引

| 交付物 | 文件 |
|---|---|
| Hardware Block Diagram | [alpha-edge-terminal-hardware-block.drawio](alpha-edge-terminal-hardware-block.drawio) / [PNG](alpha-edge-terminal-hardware-block.drawio.png) |
| Interface / BOM Closure / Cost | [bom-closure-matrix.md](bom-closure-matrix.md) |
| Power / LAN / USB Audio | [hardware-architecture.md](hardware-architecture.md) |
| Mechanical Envelope / Layout / Airflow | [mechanical-envelope.md](mechanical-envelope.md) |
| Enclosure Candidate Comparison | [enclosure-candidate-comparison.md](enclosure-candidate-comparison.md) |
| Wiring Drawing | [alpha-edge-terminal-wiring.drawio](alpha-edge-terminal-wiring.drawio) / [PNG](alpha-edge-terminal-wiring.drawio.png) |
| Assembly Drawing | [alpha-edge-terminal-assembly.drawio](alpha-edge-terminal-assembly.drawio) / [PNG](alpha-edge-terminal-assembly.drawio.png) |
| Assembly SOP | [assembly-sop.md](assembly-sop.md) |
| Bring-up Checklist | [bring-up-checklist.md](bring-up-checklist.md) |
| Hardware Verification Plan | [hardware-verification-plan.md](hardware-verification-plan.md) |
| Minimal Hardware Purchase Gate | [hardware-design-gate.md](hardware-design-gate.md) / [JSON](hardware-purchase-gate.json) |
| Engineering Design Review | [1.4_hardware_purchase_design_review.md](../../engineering/1.4_hardware_purchase_design_review.md) |
| Hardware Design Gate | [hardware-design-gate.md](hardware-design-gate.md) |
| Digital Fit Spike | [digital-fit-spike.json](digital-fit-spike.json) |
| Research Sources | [research-sources.md](research-sources.md) |

## 当前结论

官方资料已经关闭套件组成、供电接口、主要 I/O、运行存储和完整套件包络等问题。数字 Spike 给出了概念内部净空下限，但没有候选外壳精确内部尺寸、六麦阵列实物型号和两份完整含税运费报价。因此 Research、Budget 与 Hardware Design Gate 均不能通过。
