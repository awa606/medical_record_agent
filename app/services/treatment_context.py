"""Conservative clause-scoped medication context; no generated clinical text."""
from __future__ import annotations

import re
from dataclasses import dataclass


_BREAK = re.compile(r"[，,；;。！？!?\n]|但是|不过|然而|而是|但|随后|然后")
_ROLE = re.compile(r"^\s*(?:[\[【](?:患者|病人|医生|医师|家属|家长)[\]】]\s*[:：]?|(?:患者|病人|医生|医师|家属|家长)\s*[:：])\s*")
_ACTION = re.compile(r"服用|服药|口服|用药|吃药|注射|吃了|用了|(?:吃|用)(?:过)?(?=布洛芬|退热药|退烧药|对乙酰氨基酚|阿司匹林|头孢|青霉素|阿莫西林)")
_UNCERTAIN = re.compile(r"不确定|不知道|不清楚|说不清|可能|疑似|有没有|是否")
_PROPOSED = re.compile(r"建议|计划|准备|打算|拟|考虑|可以|应该|需要|不必|无需|假如|假设|倘若|(?<!主)要是|若|如果|明天|将要")
_NEGATED = re.compile(r"否认|没有|未曾|未|没|不再|不曾|不能|不要|不$")
_FOLLOWED_ADVICE = re.compile(r"(?:已经|已|曾经|曾)(?:按照|按|遵照|遵循)(?:医生|医师)?的?(?:建议|医嘱)$")
_SEQUENTIAL_ACTION = re.compile(r"就(?=(?:自行|已经|按时|规律|立即|马上)?$)")
_CAUSAL = re.compile(r"因为|由于|为了|以免|防止")
_CONTRAST = re.compile("而")
_COMPLETED_ACTION = re.compile(r"服用了|口服了|吃了|用了|注射了")
_INTENT_SUFFIX = re.compile(r"的(?:打算|计划|想法|意图|准备)")


@dataclass(frozen=True)
class TreatmentContext:
    text: str
    start: int
    action_start: int
    assertion: str
    proposed: bool


def _action_boundaries(text: str):
    """Split a bare 而 only before an explicitly completed second intake.

    A condition, recommendation or uncertainty may govern both actions. Keep
    that whole clause intact so a selected suffix cannot discard its scope.
    Other uses of 而 (including causal phrases) keep the existing behaviour.
    """
    start = 0
    for boundary in [*_BREAK.finditer(text), None]:
        end = boundary.start() if boundary else len(text)
        for contrast in _CONTRAST.finditer(text, start, end):
            position = contrast.start()
            following = position + 1
            prefix = text[start:position]
            if (_COMPLETED_ACTION.match(text, following) and _ACTION.search(prefix)
                    and not _PROPOSED.search(prefix) and not _UNCERTAIN.search(prefix)
                    and not _CAUSAL.search(prefix)
                    and not _INTENT_SUFFIX.search(text[following:end])):
                yield contrast
        if boundary:
            yield boundary
            start = boundary.end()


def treatment_contexts(text: str) -> list[TreatmentContext]:
    """Keep original clauses, with negation attached to intake, not its effect.

    A drug name alone is not proof of intake. Never combine another clause's
    drug or a word such as 退热药 with an invented outcome.
    """
    rows = []
    start = 0
    for boundary in [*_action_boundaries(text), None]:
        end = boundary.start() if boundary else len(text)
        raw = text[start:end]
        role = _ROLE.match(raw)
        offset = start + (role.end() if role else 0)
        body = text[offset:end]
        leading = len(body) - len(body.lstrip())
        body = body.strip()
        offset += leading
        for match in _ACTION.finditer(body):
            prefix = body[:match.start()]
            # Explicitly completed adherence is not merely a recommendation.
            # Do not drop any separate condition or plan preceding that phrase.
            followed = _FOLLOWED_ADVICE.search(prefix)
            modality_prefix = prefix[:followed.start()] if followed else prefix
            proposed = bool(_PROPOSED.search(modality_prefix))
            # "没有吃早饭就服用..." negates eating, not taking medication.
            # Conditions remain checked against the complete prefix above.
            negation_prefix = _SEQUENTIAL_ACTION.split(prefix)[-1]
            if _UNCERTAIN.search(prefix):
                assertion = "uncertain"
            elif re.search(r"不是没有|并非没有", negation_prefix):
                assertion = "present"
            elif _NEGATED.search(negation_prefix):
                assertion = "absent"
            else:
                assertion = "present"
            rows.append(TreatmentContext(body, offset, offset + match.start(), assertion, proposed))
        start = boundary.end() if boundary else len(text)
    return rows


def treatment_grounding_errors(value: str, context: str, *, previous_treatment: bool) -> list[str]:
    """Check the containing original clause, even if a quote drops its prefix.

    The existing extractive/numeric/subject guards remain authoritative for
    non-matching text. This function only adds medication-state checks.
    """
    value = re.sub(r"\s+", "", value)
    context = re.sub(r"\s+", "", context)
    originals = treatment_contexts(context)
    errors = []
    for selected in treatment_contexts(value):
        if previous_treatment and selected.proposed:
            errors.append("建议或计划用药不能作为既往实际用药")
        for match in re.finditer(re.escape(selected.text), context):
            action_position = match.start() + selected.action_start - selected.start
            corresponding = [row for row in originals if row.action_start == action_position]
            for original in corresponding:
                if original.assertion != selected.assertion:
                    errors.append("用药的否定或确定性与原文矛盾")
                if original.proposed != selected.proposed:
                    errors.append("引用截断了用药建议或计划限定")
    return list(dict.fromkeys(errors))
