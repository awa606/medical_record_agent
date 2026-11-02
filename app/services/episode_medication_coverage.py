"""Find explicitly narrated, recent intake absent from this HPI; never author text."""
from __future__ import annotations

import re

from app.schemas import MedicalField
from app.services.clinical_facts import clinical_experiencer, clinical_segment_contexts
from app.services.treatment_context import treatment_contexts


GAP_PREFIX = "本次病程用药待核对（原文第"
GAP_HINT = "现病史可能遗漏本次用药，请核对下列原文后修改并保存。"
_TIME = {"昨日": "昨天", "今日": "今天", "昨夜": "昨晚"}
_COUNT = str.maketrans("一二两三四五六七八九", "1223456789")
_N = r"(?:[一二两三四五六七八九]|[1-9])次"
# This is a deliberately small comparison contract, not a drug dictionary.
# Restrict to completed, single-agent, directly attributed statements. Reject
# qualifiers we cannot interpret instead of guessing an illness, dose or effect.
_INTAKE = re.compile(
    rf"(?:我|患者|本人|孩子|儿子|女儿)?(?P<day>昨天|昨日|今天|今日|前天|昨晚|昨夜|今早)"
    rf"(?:曾经|已经|曾|已)?(?:吃过|吃了|用过|用了|服用过|服用了|服用|口服过|口服了|口服)"
    rf"(?P<before>{_N})?(?P<drug>布洛芬|对乙酰氨基酚|阿司匹林|阿莫西林)(?P<after>{_N})?"
)
_LABEL = re.compile(r"^\s*(?:[【\[](?:患者|病人|家属|家长|patient)[】\]]\s*[：:]?|(?:患者|病人|家属|家长|patient)\s*[：:])\s*", re.I)
_RETRACT = re.compile(r"说错|记错|更正|纠正|说反|记反|其实.{0,6}(?:没|未|不)|并没|实际上.{0,6}(?:没|未|不)")
_DENIED_INTAKE = re.compile(r"(?:没有|未曾|没|未)(?:有)?(?:吃|服用|口服|用)(?:过|了)?([^，,；;。！？!?]*)")
_CONDITIONAL = re.compile(r"如果|假如|假设|倘若|要是|若是")
_EXPLICIT_SUBJECT = re.compile(r"^(?:我|本人|患者|病人|孩子|儿子|女儿)")
_REPORTED_ADVICE = re.compile(r"医生说|医师说|建议|计划|应该|可以|可能|不确定")


def _intake(clause):
    match = _INTAKE.fullmatch("".join(clause.split()))
    if not match or (match["before"] and match["after"]):
        return None
    return (_TIME.get(match["day"], match["day"]), match["drug"],
            (match["before"] or match["after"] or "").translate(_COUNT))


def _intake_rows(text, *, require_role):
    contexts = clinical_segment_contexts(text)
    cursor = 0
    rows = []
    turn_labeled = False
    questioned = set()
    for sentence in contexts:
        # The shared splitter omits trailing punctuation; retain whether the
        # same original sentence was a question, including a patient's echo.
        start = text.index(sentence.text, cursor)
        end = start + len(sentence.text)
        if "\n" in text[cursor:start]:
            turn_labeled = False
        if _LABEL.match(sentence.text):
            turn_labeled = True
        cursor = end
        if sentence.question or re.match(r"\s*[?？]", text[end:]):
            questioned.add(sentence.index)
        if (sentence.index in questioned or _CONDITIONAL.search(sentence.text)
                or sentence.speaker not in {"unknown", "患者", "家属", "家长"}
                or (require_role and not turn_labeled)):
            continue
        for row in treatment_contexts(sentence.text):
            if sentence.speaker in {"家属", "家长"} and row.text.startswith(("本人", "我")):
                continue
            if (row.proposed or row.assertion != "present" or
                    clinical_experiencer(sentence.text, speaker=sentence.speaker,
                        patient_target=sentence.patient_target, position=row.action_start) != "patient"):
                continue
            # A speaker label identifies who talks, not who took the medicine.
            # If the previous sentence belongs to someone else, require this
            # clause to explicitly return to the patient before adding a gap.
            if sentence.index and not _EXPLICIT_SUBJECT.match(row.text):
                previous = contexts[sentence.index - 1]
                previous_subject = clinical_experiencer(previous.text, speaker=previous.speaker,
                    patient_target=previous.patient_target)
                if previous.speaker == sentence.speaker and previous_subject != "patient":
                    continue
            intake = _intake(row.text)
            if intake:
                rows.append((sentence, row, intake))

    def retracted(sentence, row, intake):
        day, drug, _ = intake
        for later in contexts[sentence.index:]:
            if later.speaker != sentence.speaker or later.index in questioned:
                continue
            offset = row.start + len(row.text) if later.index == sentence.index else 0
            rest = later.text[offset:]
            if not _RETRACT.search(rest) or _CONDITIONAL.search(rest) or _REPORTED_ADVICE.search(rest):
                continue
            for denial in _DENIED_INTAKE.finditer(rest):
                if clinical_experiencer(later.text, speaker=later.speaker, patient_target=later.patient_target,
                        position=offset + denial.start()) != "patient":
                    continue
                other_days = {_TIME.get(item, item) for item in
                    re.findall(r"昨天|昨日|今天|今日|前天|昨晚|昨夜|今早", rest[:denial.start()])}
                if other_days and day not in other_days:
                    continue
                obj = denial.group(1).strip()
                if drug == obj:
                    return True
                # An unnamed retraction can only refer back to one nearby
                # reported drug; another named medicine is never a match.
                if (obj in {"", "药", "药物", "这种药", "这个药"}
                        and later.index - sentence.index <= 1
                        and sum(item[0].index == sentence.index for item in rows) == 1):
                    return True
        return False

    return [(sentence, intake) for sentence, row, intake in rows
            if not retracted(sentence, row, intake)]


def episode_medication_gaps(source: str, value: str) -> list[str]:
    # Source arguments are stored task text, never the provider's chosen
    # citations. Other fields and bare drug names cannot satisfy this HPI.
    charted = {intake for _, intake in _intake_rows(value, require_role=False)}
    return list(dict.fromkeys(f"{GAP_PREFIX}{sentence.index + 1}段）：{sentence.text}"
        for sentence, intake in _intake_rows(source, require_role=True) if intake not in charted))


def has_episode_medication_gap(field: MedicalField) -> bool:
    return any(item.startswith(GAP_PREFIX) for item in field.missing_elements)


def refresh_episode_medication(field: MedicalField, source: str) -> list[str]:
    """Recompute our marker even if a client removed it; preserve competing evidence."""
    if field.status == "conflicting":
        return []
    old = has_episode_medication_gap(field)
    gaps = episode_medication_gaps(source, field.value or "")
    field.missing_elements = [item for item in field.missing_elements if not item.startswith(GAP_PREFIX)] + gaps
    if gaps:
        if field.status == "complete":
            field.status = "partial"
        if not field.hint:
            field.hint = GAP_HINT
    elif old and field.hint in {None, GAP_HINT}:
        field.hint = None
        if not field.missing_elements and field.status == "partial" and not field.doctor_review_note:
            field.status = "complete"
    return gaps
