from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    segment_id: str | None = None
    index: int | None = None
    start_time: float | None = None
    end_time: float | None = None


class MedicalField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None = None
    missing: bool = False
    status: Literal["complete", "partial", "missing", "conflicting"] = "complete"
    hint: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_spans: list[SourceSpan] = Field(default_factory=list)
    missing_elements: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    confirmed_by_doctor: bool = False

    @classmethod
    def missing_field(cls, hint: str = "建议补问") -> "MedicalField":
        return cls(
            value=None,
            missing=True,
            status="missing",
            hint=hint,
            confidence=None,
            source_spans=[],
            missing_elements=[],
            fact_ids=[],
            confirmed_by_doctor=False,
        )

    @model_validator(mode="after")
    def validate_missing_field(self) -> "MedicalField":
        if self.missing:
            if self.value is not None:
                raise ValueError("missing field must keep value as None")
            self.status = "missing"
            if not self.hint:
                self.hint = "建议补问"
        elif self.status == "missing":
            self.missing = True
            self.value = None
            if not self.hint:
                self.hint = "建议补问"
        elif self.status == "partial" and not self.missing_elements:
            self.missing_elements = ["待医生补充"]
        return self


class ClinicalReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_id: str
    title: str
    organization: str
    source_type: Literal[
        "national_guideline",
        "clinical_guideline",
        "official_clinical_resource",
    ]
    version: str
    published_at: str
    url: str
    evidence_scope: str
    verification_status: Literal["source_verified"] = "source_verified"
    clinical_review_status: Literal["needs_medical_review", "reviewed"] = (
        "needs_medical_review"
    )
    retrieved_at: str


class CandidateDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["候选/待医生确认"] = "候选/待医生确认"
    evidence: list[SourceSpan] = Field(default_factory=list)
    reason: str | None = None
    rule_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    suggested_checks: list[str] = Field(default_factory=list)
    medication_notes: list[str] = Field(default_factory=list)
    risk_warnings: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    references: list[ClinicalReference] = Field(default_factory=list)
    confirmed_by_doctor: bool = False


class MedicalRecordFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degraded: bool = False
    chief_complaint: MedicalField = Field(default_factory=MedicalField.missing_field)
    present_illness: MedicalField = Field(default_factory=MedicalField.missing_field)
    previous_treatment: MedicalField = Field(default_factory=MedicalField.missing_field)
    accompanying_symptoms: MedicalField = Field(default_factory=MedicalField.missing_field)
    past_history: MedicalField = Field(default_factory=MedicalField.missing_field)
    allergy_history: MedicalField = Field(default_factory=MedicalField.missing_field)
    physical_exam: MedicalField = Field(default_factory=MedicalField.missing_field)
    candidate_diagnoses: list[CandidateDiagnosis] = Field(default_factory=list)


class SafetyCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    blocked: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
