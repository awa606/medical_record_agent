SAFETY_CHECK_PROMPT = """
你是门诊病历草稿安全检查助手。请检查草稿是否存在医疗安全边界问题。

检查项：
1. 是否编造原文未提及事实。
2. 是否把候选诊断写成最终诊断。
3. 是否把过敏史未提及写成“无”。
4. 是否存在未确认字段却允许导出的风险。

输出必须是合法 JSON，不要输出 Markdown，不要输出解释文字。

输出 JSON 结构：
{
  "passed": boolean,
  "blocked": boolean,
  "errors": [string],
  "warnings": [string]
}

字段 JSON：
{fields_json}

病历草稿：
{draft_text}
""".strip()


def build_safety_check_prompt(draft_text: str, fields_json: str = "{}") -> str:
    return SAFETY_CHECK_PROMPT.replace("{fields_json}", fields_json).replace(
        "{draft_text}",
        draft_text,
    )
