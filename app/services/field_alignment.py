"""Conservative field membership and cited-fact coverage; never generate content."""
from __future__ import annotations

import re

from app.schemas import MedicalField, MedicalRecordFields
from app.services.clinical_facts import _RESPIRATORY_SYMPTOMS, clinical_segment_contexts, extract_clinical_facts
from app.services.field_grounding import (
    FIELD_KEYS, _doctor_negative_equivalent_clause, _explicitly_retracted_chief, compact,
)
from app.services.treatment_context import treatment_contexts


CLAUSES = re.compile(r"[，,。；;\n]+")
RELATION = re.compile(r"表现为|表现是|引起|导致|所致|伴有|伴随|出现|发生|(?:过敏|服药|用药|注射).{0,8}(?:时|后)")
COVERAGE_HINT = "引用含本字段尚未写入的事实，请核对后补充；系统未自动补写。"
COVERAGE_GAP_PREFIXES = ("已引用但未写入：", "已引用的检查状态未写入：")
MANUAL_REVIEW_HINT = "医生手工修改；原始转写证据仅供对照，需在当前Revision中明确审核。"


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


def _covered_retracted_symptom(fact, value, span, spans, source):
    """A review may omit an old claim only when its exact source retracts it.

    Reuse the narrow same-patient retraction and direct-negative comparison;
    the trusted full source comes from the review's stored task, never a note.
    No source/citation/value or model-generation status is rewritten here.
    """
    aliases = _RESPIRATORY_SYMPTOMS.get(fact.name)
    if (not source or fact.type != "symptom" or fact.assertion != "present"
            or fact.experiencer != "patient" or fact.temporality != "current"
            or fact.certainty != "confirmed" or not aliases or type(span.index) is not int):
        return False
    if not any(other.type == "symptom" and other.name == fact.name
               and other.assertion == "absent" and other.experiencer == "patient"
               and other.temporality == "current" and other.certainty == "confirmed"
               for other in field_facts("present_illness", value)):
        return False
    contexts = clinical_segment_contexts(source)
    matching = [context for context in contexts if context.index == span.index
                and span.text and context.text.count(span.text) == 1]
    if not _explicitly_retracted_chief(span.text, matching, symptom_aliases=aliases):
        return False
    # The negative must itself be represented and supported by the retained
    # real citations. Another current positive cannot be hidden by one denial.
    quoted = MedicalField(value=value, source_spans=spans)
    negative_covered = False
    for clause in nonempty_clauses(value):
        if not any(compact(alias) in compact(clause) for alias in aliases):
            continue
        direct = re.sub(r"^(?:其实|实际上|实际)\s*", "", comparison_without_role(clause))
        if _doctor_negative_equivalent_clause(direct, quoted, contexts):
            negative_covered = True
        else:
            # The retraction helper proves which source claim was withdrawn;
            # it cannot turn a bare positive in the new body into reported speech.
            retold = (any(clause == old.text.strip() for old in spans)
                      and re.search(r"(?:刚才|刚刚|方才|前面|之前)(?:我)?说(?:过)?", clause))
            if not retold or not _explicitly_retracted_chief(clause, matching, symptom_aliases=aliases):
                return False
    return negative_covered


def coverage_missing(key, value, spans, *, source: str | None = None):
    if key not in {"present_illness", "previous_treatment"}:
        return []
    present = {fact_identity(fact) for fact in field_facts(key, value)}
    missing = []
    for span in spans:
        for fact in field_facts(key, span.text):
            if fact_identity(fact) not in present:
                if excluded_replacement(fact, span.text, present):
                    continue
                if key == "present_illness" and _covered_retracted_symptom(fact, value, span, spans, source):
                    continue
                state = {"present": "有", "absent": "无", "uncertain": "不确定", "resolved": "已缓解"}.get(fact.assertion, fact.assertion)
                detail = fact.value if fact.type in {"measurement", "duration", "treatment"} else fact.name
                missing.append("已引用但未写入：" + str(detail) + "（" + state + "）")
        if key == "previous_treatment":
            for clause in explicit_unperformed_tests(span.text):
                if compact(comparison_without_role(clause)) not in compact(comparison_without_role(value)):
                    missing.append("已引用的检查状态未写入：" + clause)
    return list(dict.fromkeys(missing))


def refresh_existing_coverage_hints(
    fields: MedicalRecordFields, *, source: str | None = None,
) -> MedicalRecordFields:
    """Refresh only our existing coverage findings after an explicit review save.

    Call after authoritative grounding. Manual edits with retained, checked
    citations may refresh our old gaps, but keep their manual hint and partial
    status. Never clear another validator's finding, alter content or treat
    coverage as approval. Historical reads must not call this helper.
    """
    refreshed = fields.model_copy(deep=True)
    for key in ("present_illness", "previous_treatment"):
        field = getattr(refreshed, key)
        manual_source = str(field.doctor_review_note or "").startswith("manual_doctor_edit_v1:")
        manual_with_evidence = manual_source and bool(field.source_spans) and field.hint == MANUAL_REVIEW_HINT
        owned_hint = not manual_source and field.hint == COVERAGE_HINT
        if (not field.value or field.missing or field.status != "partial"
                or not (owned_hint or manual_with_evidence) or field.confirmed_by_doctor
                or not any(item.startswith(COVERAGE_GAP_PREFIXES) for item in field.missing_elements)):
            continue
        unrelated = [item for item in field.missing_elements
                     if not item.startswith(COVERAGE_GAP_PREFIXES)]
        missing = coverage_missing(key, field.value, field.source_spans, source=source)
        field.missing_elements = list(dict.fromkeys([*unrelated, *missing]))
        if not missing and not manual_source:
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
