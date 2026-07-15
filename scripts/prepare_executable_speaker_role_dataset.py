from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_DIR = PROJECT_ROOT / "data" / "asr_eval" / "executable_clinical_v1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare executable synthetic speaker-role fixtures.")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    args = parser.parse_args()

    build_dataset(args.dataset_dir)
    print(json.dumps({"status": "ok", "dataset_dir": str(args.dataset_dir)}, ensure_ascii=False))
    return 0


def build_dataset(dataset_dir: Path) -> None:
    audio_dir = dataset_dir / "audio"
    annotation_dir = dataset_dir / "annotations"
    for folder in (audio_dir, annotation_dir):
        folder.mkdir(parents=True, exist_ok=True)
        for child in folder.glob("ec_v1_*"):
            if child.is_file():
                child.unlink()

    samples = _sample_specs()
    manifest_samples = []
    for sample in samples:
        sample_id = sample["sample_id"]
        wav_path = audio_dir / f"{sample_id}.wav"
        synthesis_text = " ".join(turn["text"] for turn in sample["turns"])
        synthesize_wav(synthesis_text, wav_path)
        duration_sec = audio_duration(wav_path)
        annotation = _build_annotation(sample, duration_sec)
        annotation_path = annotation_dir / f"{sample_id}.truth.json"
        write_json(annotation_path, annotation)
        manifest_samples.append(
            {
                "sample_id": sample_id,
                "scenario_type": sample["scenario_type"],
                "split": sample["split"],
                "audio_ref": f"audio/{sample_id}.wav",
                "sha256": sha256_file(wav_path),
                "duration_sec": duration_sec,
                "speaker_count": len(sample["speaker_roles"]),
                "annotation_path": f"annotations/{sample_id}.truth.json",
                "annotation_version": "truth-v1",
            }
        )

    manifest = {
        "dataset_version": "executable_clinical_v1",
        "schema_version": "executable-speaker-role-dataset-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "audio_storage": "git_lfs",
        "privacy": {
            "synthetic_only": True,
            "contains_real_patient_data": False,
            "note": "All audio is generated locally from synthetic scripts by Windows TTS.",
        },
        "split_policy": {
            "calibration": "May be used for threshold selection in #41.",
            "test": "Must not be read during calibration; use only for final acceptance.",
        },
        "samples": manifest_samples,
    }
    write_json(dataset_dir / "manifest.json", manifest)


def synthesize_wav(text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        handle.write(text)
        input_path = Path(handle.name)
    escaped_input = str(input_path).replace("'", "''")
    escaped_output = str(output_path).replace("'", "''")
    command = f"""
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speaker.Rate = 0
$text = [System.IO.File]::ReadAllText('{escaped_input}', [System.Text.Encoding]::UTF8)
$speaker.SetOutputToWaveFile('{escaped_output}')
$speaker.Speak($text)
$speaker.Dispose()
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        input_path.unlink(missing_ok=True)


def audio_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return round(wav.getnframes() / float(wav.getframerate()), 3)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_annotation(sample: dict[str, Any], duration_sec: float) -> dict[str, Any]:
    transcript = []
    speaker_turns = []
    rttm = []
    segment_duration = max(0.45, duration_sec / max(1, len(sample["turns"])))
    cursor = 0.0
    for index, turn in enumerate(sample["turns"], start=1):
        start_sec = round(cursor, 3)
        end_sec = round(duration_sec if index == len(sample["turns"]) else min(duration_sec, cursor + segment_duration), 3)
        turn_id = f"t{index:02d}"
        transcript.append(
            {
                "turn_id": turn_id,
                "speaker_id": turn["speaker_id"],
                "start_sec": start_sec,
                "end_sec": end_sec,
                "text": turn["text"],
                "mixed_utterance": bool(turn.get("mixed_utterance", False)),
            }
        )
        speaker_turns.append(
            {
                "turn_id": turn_id,
                "speaker_id": turn["speaker_id"],
                "start_sec": start_sec,
                "end_sec": end_sec,
            }
        )
        rttm.append(
            f"SPEAKER {sample['sample_id']} 1 {start_sec:.3f} "
            f"{max(0.001, end_sec - start_sec):.3f} <NA> <NA> {turn['speaker_id']} <NA> <NA>"
        )
        cursor = end_sec

    full_text = " ".join(turn["text"] for turn in sample["turns"])
    keywords = sorted(keyword for keyword in MEDICAL_KEYWORD_CATALOG if keyword in full_text)
    return {
        "sample_id": sample["sample_id"],
        "annotation_version": "truth-v1",
        "privacy": {
            "synthetic": True,
            "contains_real_patient_data": False,
            "source": "Windows local TTS generated from synthetic scripts",
        },
        "transcript": transcript,
        "speaker_turns": speaker_turns,
        "rttm": rttm,
        "speaker_roles": sample["speaker_roles"],
        "medical_keywords": keywords,
        "medical_record_fields": [
            {"field": key, "value": value, "evidence_turn_ids": ["t01", "t02"]}
            for key, value in sample["fields"].items()
        ],
        "evidence_spans": [
            {
                "field": "chief_complaint",
                "turn_id": "t02" if len(sample["turns"]) > 1 else "t01",
                "quote": sample["turns"][1]["text"] if len(sample["turns"]) > 1 else sample["turns"][0]["text"],
            }
        ],
    }


def _turn(speaker_id: str, text: str, mixed_utterance: bool = False) -> dict[str, Any]:
    return {"speaker_id": speaker_id, "text": text, "mixed_utterance": mixed_utterance}


def _sample_specs() -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []

    two_party_specs = [
        ("fever_cough", "发热", "咳嗽", "急性上呼吸道感染待查"),
        ("chest_pain", "胸痛", "胸闷", "胸痛原因待查"),
        ("abdominal_pain", "腹痛", "恶心", "急性胃肠炎待查"),
        ("dizziness", "头晕", "血压", "头晕原因待查"),
        ("sore_throat", "咽痛", "发热", "咽炎待查"),
        ("asthma", "咳嗽", "哮喘", "哮喘急性发作待查"),
        ("allergy", "过敏", "皮疹", "药物过敏待查"),
        ("diabetes", "糖尿病", "头晕", "血糖异常待查"),
        ("hypertension", "高血压", "胸闷", "血压控制不佳"),
        ("injury", "外伤", "疼痛", "软组织损伤待查"),
    ]
    for index, (name, keyword1, keyword2, assessment) in enumerate(two_party_specs, start=1):
        samples.append(
            {
                "sample_id": f"ec_v1_{index:03d}_two_party_{name}",
                "scenario_type": "two_party",
                "split": "calibration" if index <= 5 else "test",
                "speaker_roles": {"spk0": "doctor", "spk1": "patient"},
                "turns": [
                    _turn("spk0", f"请问今天哪里不舒服，有没有{keyword1}或者{keyword2}？"),
                    _turn("spk1", f"我从昨天开始{keyword1}，今天还有{keyword2}，感觉不舒服。"),
                    _turn("spk0", "症状持续多久了，之前有没有用药或者过敏史？"),
                    _turn("spk1", "大概一天多，没有明显过敏史，暂时没有自己用药。"),
                    _turn("spk0", f"建议先做基础检查，结合病史评估是否为{assessment}。"),
                ],
                "fields": {"chief_complaint": f"{keyword1}伴{keyword2}", "assessment": assessment},
            }
        )

    three_party_specs = [
        ("child_fever", "孩子", "发热", "咳嗽", "儿童发热待查"),
        ("elder_dizziness", "老人", "头晕", "高血压", "头晕伴血压异常"),
        ("mother_chest", "母亲", "胸痛", "胸闷", "胸痛原因待查"),
        ("father_diabetes", "父亲", "糖尿病", "头晕", "血糖波动待查"),
        ("post_injury", "他", "外伤", "疼痛", "外伤后疼痛待查"),
    ]
    for offset, (name, family_subject, keyword1, keyword2, assessment) in enumerate(three_party_specs, start=11):
        order = offset - 10
        samples.append(
            {
                "sample_id": f"ec_v1_{offset:03d}_three_party_{name}",
                "scenario_type": "three_party_family",
                "split": "calibration" if order <= 3 else "test",
                "speaker_roles": {"spk0": "doctor", "spk1": "patient", "spk2": "family"},
                "turns": [
                    _turn("spk0", f"请问主要问题是什么，{keyword1}持续多久？"),
                    _turn("spk1", f"我有{keyword1}和{keyword2}，今天比昨天明显。"),
                    _turn("spk2", f"我是家属，{family_subject}昨晚也说不舒服，我陪他过来。"),
                    _turn("spk0", "有没有基础病、过敏史或者近期用药？"),
                    _turn("spk2", f"我们家知道的情况是有{keyword2}相关病史，最近没有新药。"),
                    _turn("spk0", f"需要结合查体和检查，先按{assessment}处理。"),
                ],
                "fields": {"chief_complaint": f"{keyword1}伴{keyword2}", "assessment": assessment},
            }
        )

    single_specs = [
        ("script_reading", "发热", "咳嗽"),
        ("teaching_material", "胸痛", "高血压"),
        ("case_summary", "腹痛", "恶心"),
    ]
    for offset, (name, keyword1, keyword2) in enumerate(single_specs, start=16):
        order = offset - 15
        samples.append(
            {
                "sample_id": f"ec_v1_{offset:03d}_single_reader_{name}",
                "scenario_type": "single_reader_counterexample",
                "split": "calibration" if order == 1 else "test",
                "speaker_roles": {"spk0": "other"},
                "turns": [
                    _turn("spk0", f"这是一段单人朗读材料，内容提到{keyword1}和{keyword2}，不能伪造成医生和患者两人。"),
                    _turn("spk0", "朗读者继续说明病例摘要，仅用于反例测试和质量门禁。"),
                ],
                "fields": {"chief_complaint": f"单人朗读包含{keyword1}和{keyword2}", "assessment": "非真实医患对话"},
            }
        )

    challenge_specs = [
        ("noisy_fever", "noisy_background", "calibration", "发热", "咳嗽", [False, False, False, False, False]),
        ("interruption_chest", "interruption", "calibration", "胸痛", "胸闷", [False, True, False, False, False]),
        ("overlap_abdominal", "overlap", "calibration", "腹痛", "腹泻", [False, True, False, True, False]),
        ("noisy_dizziness", "noisy_background", "test", "头晕", "血压", [False, False, True, False, False]),
        ("overlap_noise_allergy", "noise_interruption_overlap", "test", "过敏", "咳嗽", [False, True, True, False, False]),
    ]
    for offset, (name, scenario, split, keyword1, keyword2, mixed_flags) in enumerate(challenge_specs, start=19):
        samples.append(
            {
                "sample_id": f"ec_v1_{offset:03d}_challenge_{name}",
                "scenario_type": scenario,
                "split": split,
                "speaker_roles": {"spk0": "doctor", "spk1": "patient"},
                "turns": [
                    _turn("spk0", f"请问现在最明显的症状是{keyword1}还是{keyword2}？", mixed_flags[0]),
                    _turn("spk1", f"我主要是{keyword1}，说话时可能被打断，旁边有背景声音。", mixed_flags[1]),
                    _turn("spk0", "我需要确认持续时间、用药情况和过敏史。", mixed_flags[2]),
                    _turn("spk1", f"昨天开始明显，今天还有{keyword2}，没有自己吃药。", mixed_flags[3]),
                    _turn("spk0", "建议先完成必要检查，再决定治疗方案。", mixed_flags[4]),
                ],
                "fields": {"chief_complaint": f"{keyword1}伴{keyword2}", "assessment": "挑战场景下症状待查"},
            }
        )

    if len(samples) != 23:
        raise AssertionError(f"expected 23 samples, got {len(samples)}")
    return samples


MEDICAL_KEYWORD_CATALOG = [
    "发热",
    "发烧",
    "咳嗽",
    "胸痛",
    "胸闷",
    "头晕",
    "腹痛",
    "腹泻",
    "恶心",
    "过敏",
    "高血压",
    "糖尿病",
    "外伤",
    "咽痛",
    "胃痛",
    "哮喘",
    "血压",
    "疼痛",
]


if __name__ == "__main__":
    raise SystemExit(main())
