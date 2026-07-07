# 知识库规则验证报告

> 本报告只验证工程规则是否按预期命中，不证明医学诊断正确性。

## 汇总

- 样例总数：6
- 通过：6
- 失败：0
- 通过率：1.0
- 临床有效性声明：not_claimed

## 样例结果

| 样例 | 是否通过 | 期望规则 | 命中规则 | 失败原因 |
| --- | --- | --- | --- | --- |
| KB_VAL_WIND_COLD_001 | 通过 | R_WIND_COLD_001 | R_WIND_COLD_001 | 无 |
| KB_VAL_WIND_HEAT_001 | 通过 | R_WIND_HEAT_001 | R_WIND_HEAT_001 | 无 |
| KB_VAL_SUMMER_DAMP_001 | 通过 | R_SUMMER_DAMP_001 | R_SUMMER_DAMP_001 | 无 |
| KB_VAL_QI_DEF_001 | 通过 | R_QI_DEF_001 | R_QI_DEF_001 | 无 |
| KB_VAL_NEGATIVE_TRAUMA_001 | 通过 | 无 | 无 | 无 |
| KB_VAL_SAFETY_WARNING_001 | 通过 | R_WIND_HEAT_001 | R_WIND_HEAT_001 | 无 |

## 使用说明

```powershell
python scripts/validate_kb_rules.py
```

如果后续导入教材、指南或书籍知识，应先补充来源元数据和人工审核状态，再新增验证样例。
