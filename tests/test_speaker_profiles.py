from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.speaker_profile import DoctorSpeakerProfile
from app.services.asr.speaker_profiles import (
    cosine_similarity,
    create_doctor_profile,
    delete_doctor_profile,
    list_doctor_profiles,
)


class FakeCamppExtractor:
    def generate(self, *, input):
        return [{"spk_embedding": np.asarray([[3.0, 4.0]], dtype=np.float32)}]


class SpeakerProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR"] = self.temp_dir.name

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR", None)
        self.temp_dir.cleanup()

    def test_profile_store_keeps_normalized_embedding_and_public_metadata(self):
        audio = Path(self.temp_dir.name) / "doctor.wav"
        audio.write_bytes(b"RIFF")
        with patch("app.services.asr.speaker_profiles._audio_duration", return_value=12.5):
            profile = create_doctor_profile(audio, name="张医生", extractor=FakeCamppExtractor())

        stored = json.loads((Path(self.temp_dir.name) / f"{profile.profile_id}.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["embedding"], [0.6000000238418579, 0.800000011920929])
        self.assertEqual(list_doctor_profiles()[0].name, "张医生")
        self.assertTrue(delete_doctor_profile(profile.profile_id))
        self.assertFalse(delete_doctor_profile(profile.profile_id))

    def test_cosine_similarity(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_profile_routes_and_enrollment_temp_audio_cleanup(self):
        captured_path: list[Path] = []

        def fake_create(path: Path, *, name: str):
            captured_path.append(path)
            self.assertTrue(path.exists())
            return DoctorSpeakerProfile(
                profile_id="profile-1",
                name=name,
                model="cam++",
                embedding_dimension=192,
                effective_speech_seconds=10.0,
                created_at="2026-07-10T00:00:00+00:00",
            )

        client = TestClient(app)
        with patch("app.api.speaker_profiles.create_doctor_profile", side_effect=fake_create):
            response = client.post(
                "/api/speaker-profiles/doctor?name=王医生",
                files={"file": ("doctor.wav", b"RIFF audio", "audio/wav")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "王医生")
        self.assertEqual(len(captured_path), 1)
        self.assertFalse(captured_path[0].exists())


if __name__ == "__main__":
    unittest.main()
