---
gate: Hardware Design Gate
task_id: MRA-ALPHA-1.4
status: needs_more_evidence
date: 2026-09-15
---

# Hardware Design Gate

| Check | Status | Evidence / Missing Item |
|---|---|---|
| Architecture complete | PASS | PC Browser + USB Audio + LAN + Jetson Edge Server |
| Required parts identified | PASS | R01–R05 已识别 |
| Interfaces complete | NEEDS MORE EVIDENCE | 六麦阵列型号与浏览器行为未核实；候选外壳开口未测 |
| Power complete | PASS FOR DESIGN | 原装19V、J16规格明确；仍需到货铭牌核对 |
| Storage complete | NEEDS MORE EVIDENCE | 512GB NVMe规格明确，具体型号/厚度/热特性未定 |
| Network complete | NEEDS MORE EVIDENCE | 架构明确，既有线缆/路由器实物未核 |
| Audio complete | NEEDS MORE EVIDENCE | 六麦阵列实物型号、USB/UAC、双人样本缺失 |
| Mechanical fit complete | NEEDS MORE EVIDENCE | 数字包络完成，候选外壳STEP/内部尺寸未叠合 |
| Thermal plan complete | PASS FOR DESIGN | 原装主动散热、进/排风和实测计划明确 |
| Cost complete | NEEDS MORE EVIDENCE | 只有2070参考价和一个超预算单项报价；缺两份完整含税运费报价 |
| Assembly plan complete | PASS | Draw.io装配图与SOP已建立 |
| Bring-up plan complete | PASS | 分层Checklist与HV01–HV13已建立 |

## Gate Result

**NEEDS MORE EVIDENCE**

禁止采购。禁止将 1.4 进入 VERIFY/DONE。取得六麦阵列实物信息、候选外壳精确尺寸以及两份完整含税运费报价后，先更新 Research Decision，再执行 Engineering Design Review 和本 Gate 复评。
