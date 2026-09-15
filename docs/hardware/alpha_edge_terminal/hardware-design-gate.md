---
gate: Minimal Hardware Purchase Gate
task_id: MRA-ALPHA-1.4
status: verify
purchase_decision: borrow-first
date: 2026-09-15
---

# Minimal Hardware Purchase Gate

本 Gate 只回答是否已有足够证据进入采购或借机验证，不证明 Jetson 已通过 Alpha 验收。

| Gate | Status | Evidence / Decision |
|---|---|---|
| G1 Architecture | PASS | PC / USB Audio → LAN → Jetson；医生电脑负责采音与页面，Jetson负责 FastAPI、ASR、LLM、SQLite 和文件存储 |
| G2 BOM Completeness | PASS | 计算盒所需套件、512GB NVMe、安装结构、LAN和音频能力均已列明；套件内部件未重复计价，六麦为 Existing Asset / Compatibility Pending |
| G3 Cost ≤ ¥3000 | VERIFY · MARGINAL | ¥2070仅为建议价；公开渠道为¥3199和含税¥6701.67，且两套完整报价均缺运费或其它有效字段，不能证明≤¥3000 |
| G4 Mechanical Fit | VERIFY · PARTIAL | CASE-A已闭合板卡、孔位、接口、风扇、风道与拆装；J11单面2280 NVMe的实际厚度/散热片净空仍需实物验证 |
| G5 No Known Fatal Technical Blocker | PASS FOR REAL-HARDWARE VALIDATION | 共驻留OOM已知；进程隔离ASR 3/3成功，模型可卸载；ARM/CUDA、温度、持续运行和LLM时延由真实硬件验证 |

## Purchase Decision

**BORROW-FIRST**

原因：架构和必需部件已经清楚，未发现证明串行架构必然失败的致命阻塞；但预算仍为 MARGINAL，机械适配为 PARTIAL。先借用 Jetson 做 48 小时分层验证，能够以最低成本同时关闭性能、温度、软件栈和 SSD 净空风险。

## Scope Boundary

- 1.4 的本轮完成边界是 Design Baseline 与有证据的 `BORROW-FIRST` 决策。
- 到货、装配、热测试、Bring-up 和目标运行环境验收属于后续 1.2 实机工作。
- 不采购、不制作最终外壳 CAD、不把开发机结果写成 Jetson PASS。

**Gate Result：VERIFY · sufficient for BORROW-FIRST**

详细供电、接口、存储、网络、散热、装配和 Bring-up 检查继续作为支撑证据，不再拆成采购前的独立 Gate。
