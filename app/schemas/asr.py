from __future__ import annotations

from pydantic import BaseModel, Field


class ASRSegment(BaseModel):
    speaker: str | None = None
    role: str | None = None
    text: str = ""
    start_time: float | None = None
    end_time: float | None = None
    confidence: float | None = None
    needs_review: bool = False
    reviewed_by_doctor: bool = False
    original_text: str | None = None


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


class ASRSegmentCorrection(BaseModel):
    index: int = Field(ge=0)
    role: str | None = None
    text: str | None = None
    reviewed_by_doctor: bool = True


class ASRSessionCorrectionRequest(BaseModel):
    segments: list[ASRSegmentCorrection] = Field(min_length=1)
    reviewer: str | None = None
    note: str | None = None


class ASRSessionCorrectionResponse(BaseModel):
    session_id: str
    audio_id: str
    status: str
    asr_result: ASRResult
    updated_at: str
