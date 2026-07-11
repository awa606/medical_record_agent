from __future__ import annotations

from pydantic import BaseModel, Field


class ASRSegment(BaseModel):
    segment_id: str | None = None
    revision: int = Field(default=1, ge=1)
    provisional: bool = False
    speaker: str | None = None
    speaker_id: str | None = None
    speaker_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    role: str | None = None
    text: str = ""
    start_time: float | None = None
    end_time: float | None = None
    confidence: float | None = None
    role_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    role_source: str | None = None
    role_note: str | None = None
    speaker_turn: int | None = None
    needs_review: bool = False
    reviewed_by_doctor: bool = False
    original_text: str | None = None
    overlap: bool = False


class DiarizationTurn(BaseModel):
    start_time: float = Field(ge=0.0)
    end_time: float = Field(ge=0.0)
    speaker_id: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    overlap: bool = False


class SpeakerRoleAssignment(BaseModel):
    speaker_id: str
    role: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "unassigned"
    reason: str | None = None
    requires_confirmation: bool = False


class ASRResult(BaseModel):
    audio_id: str
    engine: str
    text: str
    conversation_text: str
    segments: list[ASRSegment] = Field(default_factory=list)
    duration: float | None = None
    medical_keywords: dict[str, list[str]] = Field(default_factory=dict)
    manifest_sample_id: str | None = None
    scenario: str | None = None
    speaker_mode: str | None = None
    evaluate_diarization: bool = False
    role_strategy: str | None = None
    needs_review: bool = False
    reviewed_by_doctor: bool = False
    warnings: list[str] = Field(default_factory=list)
    diarization_turns: list[DiarizationTurn] = Field(default_factory=list)
    speaker_assignments: list[SpeakerRoleAssignment] = Field(default_factory=list)


class AudioRecord(BaseModel):
    audio_id: str
    filename: str
    path: str
    status: str = "uploaded"
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: str | None = None


class ASREvaluationRequest(BaseModel):
    ground_truth_text: str = Field(min_length=1)
    expected_keywords: list[str] = Field(default_factory=list)


class ASREvaluationResult(BaseModel):
    audio_id: str
    engine: str
    cer: float
    reference_length: int
    edit_distance: int
    keyword_recall: float
    medical_keywords: dict[str, list[str]]


class ASRSessionRecord(BaseModel):
    session_id: str
    engine: str = "mock"
    status: str = "created"
    audio_id: str | None = None
    filename: str | None = None
    events_url: str | None = None
    result_url: str | None = None
    error: str | None = None
    doctor_profile_id: str | None = None
    diarization_engine: str = "auto"
    created_at: str | None = None
    updated_at: str | None = None


class ASRSessionEvent(BaseModel):
    id: int
    event: str
    data: dict[str, object] = Field(default_factory=dict)
    created_at: str | None = None


class ASRSessionUploadResponse(BaseModel):
    session_id: str
    audio_id: str
    status: str
    filename: str
    engine: str
    events_url: str
    result_url: str
    media_url: str | None = None
    duration_seconds: float | None = None


class ASRSegmentCorrection(BaseModel):
    index: int = Field(ge=0)
    role: str | None = None
    text: str | None = None
    reviewed_by_doctor: bool = True


class ASRSpeakerRoleCorrection(BaseModel):
    speaker_id: str = Field(min_length=1)
    role: str
    reviewed_by_doctor: bool = True


class ASRSessionCorrectionRequest(BaseModel):
    segments: list[ASRSegmentCorrection] = Field(default_factory=list)
    speaker_roles: list[ASRSpeakerRoleCorrection] = Field(default_factory=list)
    reviewer: str | None = None
    note: str | None = None


class ASRSessionCorrectionResponse(BaseModel):
    session_id: str
    audio_id: str
    status: str
    asr_result: ASRResult
    updated_at: str
