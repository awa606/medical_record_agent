from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ManualFirstDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    failed_task_id: int = Field(gt=0)
    request_id: UUID
    chief_complaint: str | None = Field(default=None, max_length=4000)
    present_illness: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def require_clinical_text(self):
        if not (self.chief_complaint or self.present_illness):
            raise ValueError("请填写本次主诉或现病史。")
        return self


class ClinicianDraftOrigin(BaseModel):
    kind: Literal["doctor_manual_first"] = "doctor_manual_first"
    recorded_by: int
    recorded_by_name: str
    recorded_at: str
    previous_failed_task_id: int
    failure_category: Literal["no_supported_facts", "generation_failed"]

    def display(self, *, recorded_at: str | None = None) -> str:
        failure = "未找到可用病历信息" if self.failure_category == "no_supported_facts" else "生成未完成"
        return (
            f"首稿执笔：{self.recorded_by_name}（医生手录，编号 {self.recorded_by}）。"
            f"手录时间：{recorded_at or self.recorded_at}。原生成任务 T{self.previous_failed_task_id}，"
            f"失败分类：{failure}。"
        )
