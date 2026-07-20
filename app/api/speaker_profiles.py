from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from app.api.audio import _safe_extension
from app.api.auth import require_admin, require_current_user
from app.schemas.auth import AuthenticatedUser
from app.schemas.speaker_profile import DoctorSpeakerProfile, SpeakerProfileList
from app.services.asr.speaker_profiles import (
    create_doctor_profile,
    delete_doctor_profile,
    list_doctor_profiles,
)


router = APIRouter(
    prefix="/speaker-profiles",
    tags=["speaker-profiles"],
    dependencies=[Depends(require_current_user)],
)


@router.post("/doctor")
def enroll_doctor_voice(
    file: UploadFile = File(...),
    name: str = Query(default="本机医生", min_length=1, max_length=80),
) -> DoctorSpeakerProfile:
    extension = _safe_extension(file.filename or "doctor.wav")
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as output:
            shutil.copyfileobj(file.file, output)
            temp_path = Path(output.name)
        return create_doctor_profile(temp_path, name=name)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@router.get("")
def read_speaker_profiles() -> SpeakerProfileList:
    return SpeakerProfileList(profiles=list_doctor_profiles())


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_speaker_profile(
    profile_id: str,
    _admin: AuthenticatedUser = Depends(require_admin),
) -> Response:
    try:
        deleted = delete_doctor_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Speaker profile not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
