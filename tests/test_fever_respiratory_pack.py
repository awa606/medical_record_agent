from app.services import MockLLM
from app.services.clinical_facts import extract_clinical_facts
from app.services.fever_respiratory_pack import PACK_VERSION, infer_fever_respiratory_candidates


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


def test_pack_reads_facts_not_raw_text_keywords() -> None:
    facts = extract_clinical_facts("只是头痛，没有咳嗽，也没有发烧")

    assert infer_fever_respiratory_candidates(facts) == []
