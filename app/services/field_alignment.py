"""Conservative field membership and cited-fact coverage; never generate content."""
from __future__ import annotations

import re

from app.schemas import MedicalRecordFields
from app.services.clinical_facts import extract_clinical_facts
from app.services.field_grounding import FIELD_KEYS, compact
from app.services.treatment_context import treatment_contexts


CLAUSES = re.compile(r"[，,。；;\n]+")
RELATION = re.compile(r"表现为|表现是|引起|导致|所致|伴有|伴随|出现|发生|(?:过敏|服药|用药|注射).{0,8}(?:时|后)")
COVERAGE_HINT = "引用含本字段尚未写入的事实，请核对后补充；系统未自动补写。"
COVERAGE_GAP_PREFIXES = ("已引用但未写入：", "已引用的检查状态未写入：")


def nonempty_clauses(text):
    return [clause.strip() for clause in CLAUSES.split(text) if clause.strip()]


def affinity_errors(key, value):
    """Detect known independent-clause contamination, preserve reaction chains.

    An explicit causal/manifestation relation can span comma clauses in the same
    sentence. Do not treat the next bare negative symptom as definitely unrelated
    once an explicit reaction chain has been established. Sentence boundaries or
    explicit separate-topic markers reset that inference. This conservative
    prototype does not infer a reaction from an allergy keyword alone.
    """
    if key not in {"allergy_history", "accompanying_symptoms"}:
        return []
    errors = []
    for sentence in re.split(r"[。；;\n]+", value):
        rows = [row.strip() for row in re.split(r"[，,]+", sentence) if row.strip()]
        typed = [{fact.type for fact in extract_clinical_facts(row)} for row in rows]
        related = set()
        allergy_anchor = None
        reaction_chain = False
        for index, (clause, types) in enumerate(zip(rows, typed)):
            separate = bool(re.match(r"(?:另外|此外|另有|另诉|除此之外|独立地)", clause))
            if separate:
                allergy_anchor, reaction_chain = None, False
            if "allergy" in types:
                allergy_anchor = index
            explicit = bool(RELATION.search(clause))
            if explicit and allergy_anchor is not None:
                related.update(range(allergy_anchor, index + 1))
                reaction_chain = True
            elif reaction_chain and "symptom" in types and not separate:
                related.add(index)
            # Explicit reversed causality: symptom, allergy caused it.
            if explicit and "allergy" in types and index and "symptom" in typed[index - 1]:
                related.update({index - 1, index})
        for index, (clause, types) in enumerate(zip(rows, typed)):
            if index in related:
                continue
            if key == "allergy_history" and "symptom" in types and "allergy" not in types:
                errors.append("过敏史含独立症状子句：" + clause)
            elif key == "accompanying_symptoms" and "allergy" in types and "symptom" not in types:
                errors.append("伴随症状含独立过敏史子句：" + clause)
    return list(dict.fromkeys(errors))


def treatment_detail(text):
    """Compare one action and its details without unrelated meal negation.

    Keep the suffix verbatim, including drug, dose and response. Retain all
    prefixes except the explicit breakfast-then-intake predicate already
    distinguished by treatment_contexts; time, uncertainty and negated intake
    must not disappear through a general substring match.
    """
    contexts = treatment_contexts(text)
    if len(contexts) != 1:
        return (compact(text), "")
    context = contexts[0]
    action = context.action_start - context.start
    prefix = context.text[:action]
    if (context.assertion == "present" and not context.proposed
            and re.fullmatch(r"(?:我|患者|本人)?(?:没有|没|未)(?:吃|吃过)(?:早饭|早餐)就", prefix)):
        prefix = ""
    return (compact(prefix), compact(context.text[action:]))


def fact_identity(fact):
    """Reuse typed state, not word presence, when comparing known facts."""
    detail = (treatment_detail(fact.value or "") if fact.type == "treatment"
              else compact(fact.value or "") if fact.type in {"measurement", "duration"} else "")
    return (fact.type, fact.name, fact.assertion, fact.experiencer,
            fact.temporality, fact.certainty, detail, fact.unit)


def field_facts(key, text):
    facts = [fact for fact in extract_clinical_facts(text) if fact.experiencer == "patient"]
    if key == "present_illness":
        # A wider quote may contain historical/allergy material outside the
        # current-episode contract. No inference that it must be copied.
        return [fact for fact in facts if fact.type in {"symptom", "measurement", "duration", "treatment"}
                and fact.temporality != "historical"]
    if key == "previous_treatment":
        return [fact for fact in facts if fact.type == "treatment"]
    return []


def comparison_without_role(text):
    """Compare only: preserve all original values, source text and citations."""
    return re.sub(r"^\s*(?:[\[【](?:患者|病人|医生|医师|家属|家长|patient|doctor)[\]】]\s*[:：]?|(?:患者|病人|医生|医师|家属|家长|patient|doctor)\s*[:：])\s*", "", text, flags=re.I)


def explicit_unperformed_tests(text):
    """Tiny source-only observation, not a new clinical_facts fact type.

    Existing clinical_facts has no examination type. Keep this narrow and
    separate: an explicit not-done examination is not a normal physical exam.
    """
    return [clause for clause in nonempty_clauses(text)
            if re.search(r"(?:没有|未)(?:做|进行)?(?:过)?检查", clause)
            and not re.search(r"[?？]|有没有|是否|计划|建议", clause)]


def excluded_replacement(fact, text, present):
    """Do not demand an explicitly replaced negative option when B is covered.

    Only a single explicit '而是' with one fully represented, positive patient
    treatment qualifies. Other conjunctions, uncertain choices, omitted doses
    and multiple alternatives remain coverage questions.
    """
    if fact.type != "treatment" or fact.assertion != "absent" or text.count("而是") != 1:
        return False
    before, after = text.split("而是")
    if compact(fact.value or "") not in compact(before):
        return False
    replacement = field_facts("previous_treatment", after)
    return (len(replacement) == 1 and replacement[0].assertion == "present"
            and fact_identity(replacement[0]) in present)


def coverage_missing(key, value, spans):
    if key not in {"present_illness", "previous_treatment"}:
        return []
    present = {fact_identity(fact) for fact in field_facts(key, value)}
    missing = []
    for span in spans:
        for fact in field_facts(key, span.text):
            if fact_identity(fact) not in present:
                if excluded_replacement(fact, span.text, present):
                    continue
                state = {"present": "有", "absent": "无", "uncertain": "不确定", "resolved": "已缓解"}.get(fact.assertion, fact.assertion)
                detail = fact.value if fact.type in {"measurement", "duration", "treatment"} else fact.name
                missing.append("已引用但未写入：" + str(detail) + "（" + state + "）")
        if key == "previous_treatment":
            for clause in explicit_unperformed_tests(span.text):
                if compact(comparison_without_role(clause)) not in compact(comparison_without_role(value)):
                    missing.append("已引用的检查状态未写入：" + clause)
    return list(dict.fromkeys(missing))


def refresh_existing_coverage_hints(fields: MedicalRecordFields) -> MedicalRecordFields:
    """Refresh only our existing coverage findings after an explicit review save.

    Call after authoritative grounding. Never reclassify ordinary/manual fields,
    clear another validator's finding, alter content or treat coverage as approval.
    Historical reads must not call this helper.
    """
    refreshed = fields.model_copy(deep=True)
    for key in ("present_illness", "previous_treatment"):
        field = getattr(refreshed, key)
        if (not field.value or field.missing or field.status != "partial"
                or field.hint != COVERAGE_HINT or field.confirmed_by_doctor
                or str(field.doctor_review_note or "").startswith("manual_doctor_edit_v1:")
                or not any(item.startswith(COVERAGE_GAP_PREFIXES) for item in field.missing_elements)):
            continue
        unrelated = [item for item in field.missing_elements
                     if not item.startswith(COVERAGE_GAP_PREFIXES)]
        missing = coverage_missing(key, field.value, field.source_spans)
        field.missing_elements = list(dict.fromkeys([*unrelated, *missing]))
        if not missing:
            field.hint = None
            if not field.missing_elements:
                field.status = "complete"
    return refreshed


def validate_field_alignment(
    fields: MedicalRecordFields,
) -> tuple[MedicalRecordFields, dict[str, dict[str, object]]]:
    """Check newly extracted fields after authoritative grounding.

    Report the two known independent-clause mixings and cited same-field
    coverage gaps. Never repair facts, replace source text, or relax an existing
    conflict. Historical reads and doctor review must not call this validator.
    """
    checked = fields.model_copy(deep=True)
    diagnostics = {}
    for key in FIELD_KEYS:
        field = getattr(checked, key)
        manual_source = str(field.doctor_review_note or "").startswith(
            ("manual_doctor_edit_v1:", "doctor_source_correction_v1:")
        )
        if (not field.value or field.missing or field.status == "conflicting"
                or manual_source or field.confirmed_by_doctor):
            continue
        errors = affinity_errors(key, field.value)
        if errors:
            field.status = "conflicting"
            field.hint = "；".join(errors)
            diagnostics[key] = {"kind": "independent_clause_field_mismatch", "items": errors}
            continue
        missing = coverage_missing(key, field.value, field.source_spans)
        if missing:
            field.status = "partial"
            field.missing_elements = list(dict.fromkeys([*field.missing_elements, *missing]))
            field.hint = COVERAGE_HINT
            diagnostics[key] = {"kind": "cited_same_field_coverage_gap", "items": missing}
    return checked, diagnostics
