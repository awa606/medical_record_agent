from __future__ import annotations

import json
import re
from typing import Any


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    return fence.group(1).strip() if fence else stripped


def _extract_balanced_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("LLM response does not contain a JSON object")

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("LLM response contains an incomplete JSON object")


def parse_json_object(text: str) -> dict[str, Any]:
    candidate = _extract_balanced_object(_strip_code_fence(text))
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed
