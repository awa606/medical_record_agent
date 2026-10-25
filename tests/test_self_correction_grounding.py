"""A quoted, explicitly withdrawn symptom must not survive as a positive chief."""
import pytest

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.llm.base import LLMProviderResponse
from app.services.llm.llm_record_generator import LLMRecordGenerator


def extract_recorded(monkeypatch, source, chief, *, illness=None, audio=False):
    monkeypatch.setattr("app.services.llm.llm_record_generator.anonymize_text", lambda text: text)
    original = source.removeprefix("患者：").rstrip("。")
    illness = illness or original
    payload = MedicalRecordFields(
        chief_complaint=MedicalField(value=chief, source_spans=[SourceSpan(text=chief, index=0)]),
        present_illness=MedicalField(value=illness, source_spans=[SourceSpan(text=illness, index=0)]),
    )

    class RecordedProvider:
        name = "self-correction-regression"
        model = "no-model-call"
        calls = 0

        def generate_fields_json(self, text, *, timeout_seconds):
            self.calls += 1
            return LLMProviderResponse(provider=self.name, model=self.model,
                                       content=payload.model_dump_json(), latency_ms=0)

    provider = RecordedProvider()
    generator = LLMRecordGenerator(provider=provider, allow_mock_fallback=False)
    generator.max_retries = 0
    if audio:
        generator.source_segments = [{"segment_id": "patient-1", "text": original, "role": "患者"}]
    fields = generator.extract_fields(source)
    assert provider.calls == 1
    return generator, fields


@pytest.mark.parametrize("audio", [False, True])
@pytest.mark.parametrize("source,chief", [
    ("患者：刚才说发烧，其实没有发热。", "刚才说发烧"),
    ("患者：刚才说发热，其实没有发烧。", "刚才说发热"),
    ("患者：刚才说头疼，我说错了，其实没有头痛。", "刚才说头疼"),
    ("患者：刚才说胸口痛，更正一下，没有胸痛。", "刚才说胸口痛"),
])
def test_generator_isolates_explicitly_retracted_chief(monkeypatch, source, chief, audio):
    generator, fields = extract_recorded(monkeypatch, source, chief, audio=audio)

    assert fields.chief_complaint.status == "conflicting"
    assert "撤回" in fields.chief_complaint.hint
    assert fields.chief_complaint.value == chief
    assert fields.chief_complaint.source_spans[0].text == chief
    assert fields.chief_complaint.source_spans[0].index == 0
    assert fields.present_illness.status == "complete"
    assert fields.present_illness.value == source.removeprefix("患者：").rstrip("。")
    fields.chief_complaint.confirmed_by_doctor = True
    assert generator.safety_check(generator.generate_draft(fields), fields).blocked


@pytest.mark.parametrize("audio", [False, True])
@pytest.mark.parametrize("source,chief", [
    ("患者：昨天发烧，今天已经退了。", "昨天发烧，今天已经退了"),
    ("患者：刚才说发烧，今天已经退了。", "刚才说发烧，今天已经退了"),
    ("患者：刚才说发烧，其实没有胸痛。", "刚才说发烧"),
    ("患者：刚才说发烧，现在仍然发烧。", "刚才说发烧"),
    ("患者：刚才说发烧，其实不是没有发热。", "刚才说发烧，其实不是没有发热"),
])
def test_generator_keeps_occurrence_resolution_and_other_symptom(monkeypatch, source, chief, audio):
    _, fields = extract_recorded(monkeypatch, source, chief, audio=audio)

    assert fields.chief_complaint.status == "complete"
    assert fields.chief_complaint.value == chief
    assert fields.chief_complaint.source_spans[0].text == chief


@pytest.mark.parametrize("audio", [False, True])
def test_retraction_guard_does_not_target_a_later_selected_positive(monkeypatch, audio):
    source = "患者：刚才说发烧，其实没有发热，现在又发烧了。"
    _, fields = extract_recorded(monkeypatch, source, "现在又发烧了", audio=audio)

    # The existing general negation guard can still reject this sequence.
    # This narrow fix must not call the later, independently cited statement
    # the withdrawn one. General negation scope is a separate failure record.
    assert "撤回" not in (fields.chief_complaint.hint or "")
    assert fields.chief_complaint.value == "现在又发烧了"
    assert fields.chief_complaint.source_spans[0].text == "现在又发烧了"


@pytest.mark.parametrize("audio", [False, True])
@pytest.mark.parametrize("source,chief", [
    ("患者：刚才说昨晚发烧，其实没有发热的是今天。", "刚才说昨晚发烧"),
    ("患者：刚才说昨天头疼，其实没有头痛的是今天。", "刚才说昨天头疼"),
    ("患者：刚才说今天发烧，其实没有发热的是昨晚。", "刚才说今天发烧"),
])
def test_explicitly_different_occurrence_times_are_not_a_retraction(monkeypatch, source, chief, audio):
    _, fields = extract_recorded(monkeypatch, source, chief, audio=audio)

    assert fields.chief_complaint.status == "complete"
    assert fields.chief_complaint.value == chief
    assert fields.chief_complaint.source_spans[0].text == chief


def test_another_speakers_correction_cannot_retract_patient_chief(monkeypatch):
    source = "患者：刚才说发烧。\n家属：我刚才说发热，其实没有发热。"
    _, fields = extract_recorded(monkeypatch, source, "刚才说发烧", illness="刚才说发烧")

    assert fields.chief_complaint.status == "complete"
    assert fields.chief_complaint.value == "刚才说发烧"


def test_postposed_other_subject_cannot_retract_patient_chief(monkeypatch):
    source = "患者：父亲刚才说我发烧，其实没有发热的是他。"
    chief = "父亲刚才说我发烧"
    _, fields = extract_recorded(monkeypatch, source, chief)

    assert fields.chief_complaint.status == "complete"
    assert "撤回" not in (fields.chief_complaint.hint or "")
    assert fields.chief_complaint.value == chief
    assert fields.chief_complaint.source_spans[0].text == chief
