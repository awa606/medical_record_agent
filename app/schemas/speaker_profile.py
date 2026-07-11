from __future__ import annotations

from pydantic import BaseModel, Field


class DoctorSpeakerProfile(BaseModel):
    profile_id: str
    name: str
    model: str
    embedding_dimension: int = Field(ge=1)
    effective_speech_seconds: float = Field(ge=0.0)
    created_at: str


class SpeakerProfileList(BaseModel):
    profiles: list[DoctorSpeakerProfile] = Field(default_factory=list)
