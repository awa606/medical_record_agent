from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ClinicianAssessmentInput(BaseModel):
    """An explicit assessment supplied by the reviewing clinician."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    statement: str = Field(min_length=1, max_length=2000)
    certainty: Literal["documented", "under_consideration"]

    @property
    def status_label(self) -> str:
        return "待排" if self.certainty == "under_consideration" else "医生记录"


class ClinicianAssessment(ClinicianAssessmentInput):
    recorded_by: int
    recorder_name: str
    recorded_at: str
