from __future__ import annotations

from pydantic import BaseModel, Field


class ASRSegment(BaseModel):
    speaker: str | None = None
    role: str | None = None
    text: str = ""
    start_time: float | None = None
    end_time: float | None = None
    confidence: float | None = None


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
