from __future__ import annotations

from pathlib import Path

from app.schemas import ASRResult, ASRSegment


MOCK_SEGMENTS = [
    ASRSegment(
        speaker="医生",
        role="doctor",
        text="你好，哪里不舒服？",
        start_time=0.0,
        end_time=2.0,
        confidence=0.99,
    ),
    ASRSegment(
        speaker="患者",
        role="patient",
        text="左手手掌被蛇咬伤了，肿痛两个小时左右。",
        start_time=2.1,
        end_time=6.8,
        confidence=0.99,
    ),
    ASRSegment(
        speaker="医生",
        role="doctor",
        text="被咬后做过什么处理吗？",
        start_time=6.9,
        end_time=9.4,
        confidence=0.99,
    ),
    ASRSegment(
        speaker="患者",
        role="patient",
        text="用酒精冲洗了，绑了绷带，吃了季德胜蛇药片。",
        start_time=9.5,
        end_time=14.8,
        confidence=0.99,
    ),
    ASRSegment(
        speaker="医生",
        role="doctor",
        text="现在除了咬伤部位不舒服，还有什么其他难受的？",
        start_time=14.9,
        end_time=19.2,
        confidence=0.99,
    ),
    ASRSegment(
        speaker="患者",
        role="patient",
        text="现在有些畏寒、头晕、胸闷、心慌，牙龈也有些出血。",
        start_time=19.3,
        end_time=25.0,
        confidence=0.99,
    ),
]

EXPECTED_KEYWORDS = [
    "蛇咬伤",
    "左手",
    "肿痛",
    "两个小时",
    "酒精",
    "绷带",
    "季德胜蛇药片",
    "畏寒",
    "头晕",
    "胸闷",
    "心慌",
    "牙龈出血",
]


class MockASREngine:
    name = "mock-asr-v0.2"

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        conversation_text = "\n".join(
            f"[{segment.speaker}] {segment.text}" for segment in MOCK_SEGMENTS
        )
        plain_text = "\n".join(segment.text for segment in MOCK_SEGMENTS)
        recognized_text = conversation_text.replace("牙龈也有些出血", "牙龈出血")
        recognized = [
            keyword for keyword in EXPECTED_KEYWORDS if keyword in recognized_text
        ]

        return ASRResult(
            audio_id=audio_id,
            engine=self.name,
            text=plain_text,
            conversation_text=conversation_text,
            segments=MOCK_SEGMENTS,
            duration=25.0,
            medical_keywords={
                "expected": EXPECTED_KEYWORDS,
                "recognized": recognized,
                "missing": [
                    keyword for keyword in EXPECTED_KEYWORDS if keyword not in recognized
                ],
            },
        )
