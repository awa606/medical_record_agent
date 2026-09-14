from app.services import MockLLM
from app.services.clinical_facts import extract_clinical_facts
from app.services.fever_respiratory_pack import (
    PACK_VERSION,
    REFERENCE_CATALOG,
    SOURCE_CATALOG_VERSION,
    infer_fever_respiratory_candidates,
)


def _diagnosis_names(text: str) -> list[str]:
    fields = MockLLM().extract_fields(text)
    return [diagnosis.name for diagnosis in fields.candidate_diagnoses]


def test_short_fever_uses_facts_for_fever_workup_reference() -> None:
    fields = MockLLM().extract_fields("我发烧39°C")

    assert fields.chief_complaint.status == "partial"
    assert [diagnosis.name for diagnosis in fields.candidate_diagnoses] == ["发热待查"]
    diagnosis = fields.candidate_diagnoses[0]
    assert diagnosis.rule_id == "FEVER_RESP_V1_FEVER_WORKUP"
    assert diagnosis.evidence
    assert PACK_VERSION in diagnosis.reason
    assert "规则匹配度" in diagnosis.reason
    assert "缺失证据" in diagnosis.reason
    assert "症状持续多久了？" in diagnosis.follow_up_questions
    assert [reference.reference_id for reference in diagnosis.references] == [
        "NHC_FLU_2025",
        "WHO_SARI_TOOLKIT_2022",
    ]


def test_fever_headache_adds_influenza_like_reference() -> None:
    names = _diagnosis_names("我感觉我发烧了，头很痛，39°C")

    assert "发热待查" in names
    assert "流感样症状参考" in names


def test_fever_cough_adds_pulmonary_infection_reference() -> None:
    names = _diagnosis_names("昨天开始咳嗽，发热39度")

    assert "发热待查" in names
    assert "肺部感染待排" in names


def test_absent_fever_does_not_create_positive_fever_pack_candidate() -> None:
    fields = MockLLM().extract_fields("我没有发烧，只是头痛")

    assert fields.candidate_diagnoses == []


def test_high_fever_keeps_danger_signal_warning() -> None:
    fields = MockLLM().extract_fields("体温40度，头痛")

    assert [diagnosis.rule_id for diagnosis in fields.candidate_diagnoses] == [
        "FEVER_RESP_V1_FEVER_WORKUP",
        "FEVER_RESP_V1_INFLUENZA_LIKE",
    ]
    assert "40℃" in fields.present_illness.value
    warnings = "\n".join(
        warning for diagnosis in fields.candidate_diagnoses for warning in diagnosis.risk_warnings
    )
    assert "持续高热" in warnings
    assert "气促" in warnings


def test_pack_reads_facts_not_raw_text_keywords() -> None:
    facts = extract_clinical_facts("只是头痛，没有咳嗽，也没有发烧")

    assert infer_fever_respiratory_candidates(facts) == []


def test_influenza_and_pulmonary_candidates_expose_traceable_sources() -> None:
    influenza = MockLLM().extract_fields("发热39度，头痛").candidate_diagnoses
    pulmonary = MockLLM().extract_fields("发热39度，咳嗽").candidate_diagnoses

    influenza_reference_ids = {
        reference.reference_id
        for diagnosis in influenza
        for reference in diagnosis.references
    }
    pulmonary_reference_ids = {
        reference.reference_id
        for diagnosis in pulmonary
        for reference in diagnosis.references
    }

    assert "CDC_FLU_SIGNS_2026" in influenza_reference_ids
    assert "NICE_NG250_2025" in pulmonary_reference_ids
    assert all(
        reference.clinical_review_status == "needs_medical_review"
        for diagnosis in [*influenza, *pulmonary]
        for reference in diagnosis.references
    )


def test_source_catalog_uses_verified_official_https_sources() -> None:
    assert SOURCE_CATALOG_VERSION == "fever_respiratory_sources_v1"
    assert set(REFERENCE_CATALOG) == {
        "CDC_FLU_SIGNS_2026",
        "NHC_FLU_2025",
        "NICE_NG250_2025",
        "WHO_SARI_TOOLKIT_2022",
    }
    assert all(reference.url.startswith("https://") for reference in REFERENCE_CATALOG.values())
    assert all(
        reference.verification_status == "source_verified"
        for reference in REFERENCE_CATALOG.values()
    )


def test_candidate_reference_metadata_is_api_serializable() -> None:
    diagnosis = MockLLM().extract_fields("发热39度，咳嗽").candidate_diagnoses[0]
    payload = diagnosis.model_dump(mode="json")

    assert payload["references"]
    assert payload["references"][0]["reference_id"] == "NHC_FLU_2025"
    assert payload["references"][0]["clinical_review_status"] == "needs_medical_review"
