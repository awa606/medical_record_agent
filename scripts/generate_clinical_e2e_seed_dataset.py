from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path("data/clinical_e2e/field_disease_pack_v1")
CASE_DIR = ROOT / "cases"
FEVER_PACK = "fever_respiratory_v1"


def segs(*items: tuple[str, str] | tuple[str, str, str]) -> list[dict[str, Any]]:
    result = []
    for index, item in enumerate(items, 1):
        if len(item) == 2:
            role, text = item
            speaker = {"医生": "spk-doctor", "患者": "spk-patient", "家属": "spk-family"}.get(role, f"spk-{index}")
        else:
            role, speaker, text = item
        result.append({"segment_id": f"seg-{index}", "speaker_id": speaker, "role": role, "text": text})
    return result


def fact(type_: str, name: str, assertion: str = "present", value: str | None = None, unit: str | None = None) -> dict[str, Any]:
    payload = {"type": type_, "name": name, "assertion": assertion}
    if value is not None:
        payload["value"] = value
    if unit is not None:
        payload["unit"] = unit
    return payload


def candidate(name: str, rule_id: str | None = None) -> dict[str, Any]:
    payload = {"name": name, "requires_evidence": True}
    if rule_id:
        payload["rule_id"] = rule_id
    return payload


def required(target: str, *contains: str) -> dict[str, Any]:
    return {"target": target, "contains": list(contains)}


def risk(name: str, *keywords: str) -> dict[str, Any]:
    return {"name": name, "warning_keywords": list(keywords)}


def text_of(segments: list[dict[str, Any]]) -> str:
    return "\n".join(str(segment["text"]) for segment in segments)


def default_forbidden(segments: list[dict[str, Any]], extra: list[str] | None = None) -> list[str]:
    text = text_of(segments)
    phrases = ["3天前淋雨受凉", "铁锈色痰", "当地卫生院", "食欲不佳", "既往体健", "肺结核"]
    for phrase in ["布洛芬", "淋雨", "咳嗽、咳痰"]:
        if phrase not in text:
            phrases.append(phrase)
    if extra:
        phrases.extend(extra)
    return list(dict.fromkeys(phrases))


def expected(
    *,
    facts: list[dict[str, Any]] | None = None,
    field_status: dict[str, str] | None = None,
    required_content: list[dict[str, Any]] | None = None,
    forbidden_content: list[str] | None = None,
    candidate_diagnoses: list[dict[str, Any]] | None = None,
    forbidden_candidate_diagnoses: list[str] | None = None,
    follow_up_questions_any: list[str] | None = None,
    risk_signals: list[dict[str, Any]] | None = None,
    applicable_packs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "facts": facts or [],
        "field_status": field_status or {},
        "required_content": required_content or [],
        "forbidden_content": forbidden_content or [],
        "candidate_diagnoses": candidate_diagnoses or [],
        "forbidden_candidate_diagnoses": forbidden_candidate_diagnoses or [],
        "follow_up_questions_any": follow_up_questions_any or [],
        "risk_signals": risk_signals or [],
        "applicable_packs": applicable_packs or [],
    }


def fever_expected(
    segments: list[dict[str, Any]],
    *,
    facts: list[dict[str, Any]],
    field_status: dict[str, str],
    required_content: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    followups: list[str] | None = None,
    risks: list[dict[str, Any]] | None = None,
    forbidden_extra: list[str] | None = None,
) -> dict[str, Any]:
    return expected(
        facts=facts,
        field_status=field_status,
        required_content=required_content,
        forbidden_content=default_forbidden(segments, forbidden_extra),
        candidate_diagnoses=candidates,
        follow_up_questions_any=followups or [],
        risk_signals=risks or [],
        applicable_packs=[FEVER_PACK],
    )


def non_fever_expected(
    segments: list[dict[str, Any]],
    *,
    facts: list[dict[str, Any]] | None = None,
    field_status: dict[str, str] | None = None,
    required_content: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return expected(
        facts=facts or [],
        field_status=field_status or {},
        required_content=required_content or [],
        forbidden_content=default_forbidden(segments),
        candidate_diagnoses=[],
        forbidden_candidate_diagnoses=["发热待查", "流感样症状参考", "肺部感染待排"],
        applicable_packs=[],
    )


def add(
    cases: list[dict[str, Any]],
    case_id: str,
    split: str,
    scenario: str,
    segments: list[dict[str, Any]],
    exp: dict[str, Any],
    title: str,
) -> None:
    cases.append(
        {
            "case_id": case_id,
            "split": split,
            "scenario_type": scenario,
            "title": title,
            "privacy": {
                "synthetic": True,
                "contains_real_patient_data": False,
                "note": "Synthetic classroom evaluation case; no real patient data.",
            },
            "segments": segments,
            "expected": exp,
        }
    )


def development_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    items: list[tuple[str, str, list[dict[str, Any]], dict[str, Any], str]] = []

    def fcase(
        case_id: str,
        scenario: str,
        segments: list[dict[str, Any]],
        facts: list[dict[str, Any]],
        statuses: dict[str, str],
        required_items: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        title: str,
        followups: list[str] | None = None,
        risks: list[dict[str, Any]] | None = None,
        forbidden_extra: list[str] | None = None,
    ) -> None:
        if risks is None and scenario == "danger_signal":
            risks = [risk("danger_signal", "持续高热", "胸痛", "气促")]
        items.append(
            (
                case_id,
                scenario,
                segments,
                fever_expected(
                    segments,
                    facts=facts,
                    field_status=statuses,
                    required_content=required_items,
                    candidates=candidates,
                    followups=followups,
                    risks=risks,
                    forbidden_extra=forbidden_extra,
                ),
                title,
            )
        )

    def ncase(
        case_id: str,
        scenario: str,
        segments: list[dict[str, Any]],
        facts: list[dict[str, Any]],
        statuses: dict[str, str],
        required_items: list[dict[str, Any]],
        title: str,
    ) -> None:
        items.append(
            (
                case_id,
                scenario,
                segments,
                non_fever_expected(
                    segments,
                    facts=facts,
                    field_status=statuses,
                    required_content=required_items,
                ),
                title,
            )
        )

    fcase(
        "ce2e_v1_001_short_fever_temp",
        "short_fever_temp",
        segs(("患者", "我发烧39°C。")),
        [fact("symptom", "发热"), fact("measurement", "体温", value="39℃", unit="℃")],
        {"chief_complaint": "partial", "present_illness": "partial"},
        [required("chief_complaint", "发热", "39℃"), required("present_illness", "体温约39℃")],
        [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")],
        "短句发热和体温",
        followups=["症状持续多久了？"],
    )
    fcase(
        "ce2e_v1_002_short_fever_headache",
        "short_fever_headache",
        segs(("患者", "我感觉我发烧了，头很痛，39°C。")),
        [fact("symptom", "发热"), fact("symptom", "头痛"), fact("measurement", "体温", value="39℃", unit="℃")],
        {"chief_complaint": "partial", "present_illness": "partial", "accompanying_symptoms": "partial"},
        [required("chief_complaint", "发热伴头痛"), required("present_illness", "发热、头痛"), required("accompanying_symptoms", "头痛")],
        [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("流感样症状参考", "FEVER_RESP_V1_INFLUENZA_LIKE")],
        "短句发热伴头痛",
        followups=["症状持续多久了？"],
    )
    fcase(
        "ce2e_v1_003_fever_duration",
        "duration",
        segs(("患者", "发热三天。")),
        [fact("symptom", "发热"), fact("duration", "病程", value="三天")],
        {"chief_complaint": "complete", "present_illness": "partial"},
        [required("chief_complaint", "发热三天"), required("present_illness", "发热三天")],
        [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")],
        "发热伴明确病程",
    )
    ncase(
        "ce2e_v1_004_cough_duration_only",
        "respiratory_no_fever",
        segs(("患者", "昨天开始咳嗽。")),
        [fact("symptom", "咳嗽"), fact("duration", "病程", value="昨天开始")],
        {"chief_complaint": "complete", "present_illness": "partial"},
        [required("chief_complaint", "咳嗽", "昨天开始")],
        "单纯咳嗽未进入发热包",
    )
    ncase(
        "ce2e_v1_005_absent_fever_headache",
        "negation",
        segs(("患者", "我没有发烧，只是头痛。")),
        [fact("symptom", "发热", "absent"), fact("symptom", "头痛")],
        {"chief_complaint": "partial", "present_illness": "partial"},
        [required("chief_complaint", "头痛"), required("present_illness", "否认发热")],
        "否认发热但存在头痛",
    )
    ncase(
        "ce2e_v1_006_question_answer_absent_fever",
        "doctor_question_negation",
        segs(("患者", "医生：有没有发热？患者：没有。")),
        [fact("symptom", "发热", "absent")],
        {"chief_complaint": "missing", "present_illness": "complete"},
        [required("present_illness", "否认发热")],
        "医生询问后患者否认发热",
    )
    fcase(
        "ce2e_v1_007_resolved_fever",
        "resolved",
        segs(("患者", "昨天发烧，今天已经退了。")),
        [fact("symptom", "发热", "resolved")],
        {"chief_complaint": "partial", "present_illness": "partial"},
        [required("chief_complaint", "曾有发热"), required("present_illness", "目前已缓解")],
        [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")],
        "既往发热当前缓解",
        followups=["目前还有发热或其他不适吗？"],
    )
    fcase(
        "ce2e_v1_008_ibuprofen_defervescence",
        "treatment_effect",
        segs(("患者", "吃了布洛芬以后体温降下来了。")),
        [fact("treatment", "既往处理", value="服用布洛芬后体温下降"), fact("symptom", "发热", "resolved")],
        {"chief_complaint": "partial", "present_illness": "partial", "previous_treatment": "partial"},
        [required("previous_treatment", "布洛芬"), required("present_illness", "体温下降")],
        [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")],
        "退热药后体温下降",
    )
    fcase(
        "ce2e_v1_009_fever_cough",
        "fever_cough",
        segs(("患者", "昨天开始咳嗽，发热39度。")),
        [fact("symptom", "咳嗽"), fact("symptom", "发热"), fact("measurement", "体温", value="39℃"), fact("duration", "病程", value="昨天开始")],
        {"chief_complaint": "complete", "present_illness": "partial"},
        [required("chief_complaint", "发热", "咳嗽"), required("present_illness", "体温约39℃")],
        [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("肺部感染待排", "FEVER_RESP_V1_PULMONARY_INFECTION")],
        "发热伴咳嗽",
    )
    fcase(
        "ce2e_v1_010_fever_headache_duration",
        "fever_headache",
        segs(("患者", "头痛，发热两天，体温38.5度。")),
        [fact("symptom", "头痛"), fact("symptom", "发热"), fact("duration", "病程", value="两天"), fact("measurement", "体温", value="38.5℃")],
        {"chief_complaint": "complete", "present_illness": "partial", "accompanying_symptoms": "partial"},
        [required("chief_complaint", "发热伴头痛", "两天"), required("present_illness", "38.5℃")],
        [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("流感样症状参考", "FEVER_RESP_V1_INFLUENZA_LIKE")],
        "发热头痛伴病程",
    )

    remaining_specs = [
        ("ce2e_v1_011_three_party_child_fever", "three_party", segs(("医生", "哪里不舒服？"), ("家属", "她发烧39度，还说头痛。"), ("患者", "头痛。")), [fact("symptom", "发热"), fact("symptom", "头痛"), fact("measurement", "体温", value="39℃")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热伴头痛")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("流感样症状参考", "FEVER_RESP_V1_INFLUENZA_LIKE")], "三人问诊家属描述发热"),
        ("ce2e_v1_012_family_medication_effect", "three_party_treatment", segs(("家属", "刚吃了布洛芬，体温降到37.8度。")), [fact("treatment", "既往处理", value="服用布洛芬后体温下降"), fact("measurement", "体温", value="37.8℃"), fact("symptom", "发热")], {"chief_complaint": "partial", "present_illness": "partial", "previous_treatment": "partial"}, [required("previous_treatment", "布洛芬"), required("present_illness", "37.8℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "家属描述用药和体温"),
        ("ce2e_v1_015_asr_typo_fever", "asr_typo", segs(("患者", "我发少39度。")), [fact("measurement", "体温", value="39℃"), fact("symptom", "发热")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "39℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "ASR错字但保留体温"),
        ("ce2e_v1_016_asr_cough_temp", "asr_typo", segs(("患者", "我一直咳，体温三十九度。")), [fact("symptom", "咳嗽"), fact("measurement", "体温", value="39℃"), fact("symptom", "发热")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("present_illness", "体温约39℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("肺部感染待排", "FEVER_RESP_V1_PULMONARY_INFECTION")], "ASR口语咳和中文温度"),
        ("ce2e_v1_017_fever_duration_temp_cough", "complete_dialogue_fragment", segs(("患者", "我发热三天，体温39度，有咳嗽。")), [fact("symptom", "发热"), fact("duration", "病程", value="三天"), fact("measurement", "体温", value="39℃"), fact("symptom", "咳嗽")], {"chief_complaint": "complete", "present_illness": "partial"}, [required("chief_complaint", "发热", "三天"), required("present_illness", "咳嗽")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("肺部感染待排", "FEVER_RESP_V1_PULMONARY_INFECTION")], "发热咳嗽完整片段"),
        ("ce2e_v1_018_negative_cough_context", "negation", segs(("患者", "我发烧一天，最高39度，没有咳嗽。")), [fact("symptom", "发热"), fact("duration", "病程", value="一天"), fact("measurement", "体温", value="39℃"), fact("symptom", "咳嗽", "absent")], {"chief_complaint": "complete", "present_illness": "partial"}, [required("chief_complaint", "发热", "一天")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "发热但否认咳嗽"),
        ("ce2e_v1_019_resolved_after_antipyretic", "resolved_treatment", segs(("患者", "昨晚发烧，吃了退烧药后退了。")), [fact("symptom", "发热", "resolved"), fact("treatment", "既往处理", value="服用退烧药")], {"chief_complaint": "partial", "present_illness": "partial", "previous_treatment": "partial"}, [required("present_illness", "目前已缓解"), required("previous_treatment", "退烧药")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "退烧药后退热"),
        ("ce2e_v1_020_fever_chest_tightness", "danger_signal", segs(("患者", "发热39度，有点胸闷。")), [fact("symptom", "发热"), fact("measurement", "体温", value="39℃"), fact("symptom", "胸闷")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "发热伴胸闷危险信号"),
        ("ce2e_v1_021_flu_like", "flu_like", segs(("患者", "发烧39度，头痛乏力。")), [fact("symptom", "发热"), fact("symptom", "头痛"), fact("measurement", "体温", value="39℃"), fact("symptom", "乏力")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热伴头痛")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("流感样症状参考", "FEVER_RESP_V1_INFLUENZA_LIKE")], "流感样症状"),
        ("ce2e_v1_022_pulmonary_reference", "pulmonary_reference", segs(("患者", "发热39度，一直咳。")), [fact("symptom", "发热"), fact("measurement", "体温", value="39℃"), fact("symptom", "咳嗽")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热"), required("present_illness", "咳嗽")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("肺部感染待排", "FEVER_RESP_V1_PULMONARY_INFECTION")], "肺部感染待排线索"),
        ("ce2e_v1_025_temperature_only", "temperature_only", segs(("患者", "体温三十九度。")), [fact("measurement", "体温", value="39℃"), fact("symptom", "发热")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "体温39℃"), required("present_illness", "体温约39℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "只有体温数值"),
        ("ce2e_v1_028_numeric_duration", "duration", segs(("患者", "发烧5天，体温38度。")), [fact("symptom", "发热"), fact("duration", "病程", value="5天"), fact("measurement", "体温", value="38℃")], {"chief_complaint": "complete", "present_illness": "partial"}, [required("chief_complaint", "发热", "5天"), required("present_illness", "38℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "数字病程"),
        ("ce2e_v1_029_high_fever", "danger_signal", segs(("患者", "发热40度。")), [fact("symptom", "发热"), fact("measurement", "体温", value="40℃")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "40℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "高热危险信号"),
        ("ce2e_v1_030_fever_headache_cough", "fever_cough_headache", segs(("患者", "发热39度，头痛，也有点咳。")), [fact("symptom", "发热"), fact("symptom", "头痛"), fact("symptom", "咳嗽"), fact("measurement", "体温", value="39℃")], {"chief_complaint": "partial", "present_illness": "partial", "accompanying_symptoms": "partial"}, [required("chief_complaint", "发热伴头痛"), required("present_illness", "咳嗽")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("流感样症状参考", "FEVER_RESP_V1_INFLUENZA_LIKE"), candidate("肺部感染待排", "FEVER_RESP_V1_PULMONARY_INFECTION")], "发热头痛咳嗽"),
        ("ce2e_v1_031_family_describes_elder", "three_party", segs(("医生", "孩子哪里不舒服？"), ("家属", "我妈妈发烧了，头很痛。")), [fact("symptom", "发热"), fact("symptom", "头痛")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热伴头痛")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("流感样症状参考", "FEVER_RESP_V1_INFLUENZA_LIKE")], "家属描述老人发热头痛"),
        ("ce2e_v1_032_two_party_structured", "two_party_dialogue", segs(("医生", "哪里不舒服？"), ("患者", "我发热三天。"), ("医生", "体温多少？"), ("患者", "39度。")), [fact("symptom", "发热"), fact("duration", "病程", value="三天"), fact("measurement", "体温", value="39℃")], {"chief_complaint": "complete", "present_illness": "partial"}, [required("chief_complaint", "发热", "三天"), required("present_illness", "39℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "两人结构化问诊"),
        ("ce2e_v1_037_resolved_fever_current_cough", "resolved_current_symptom", segs(("患者", "昨天发烧今天退了，现在咳嗽。")), [fact("symptom", "发热", "resolved"), fact("symptom", "咳嗽")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("present_illness", "目前已缓解"), required("chief_complaint", "咳嗽")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "退热后仍咳嗽"),
        ("ce2e_v1_038_low_grade_temp_cough", "low_grade_fever_cough", segs(("患者", "体温37.8度，咳嗽两天。")), [fact("measurement", "体温", value="37.8℃"), fact("symptom", "发热"), fact("symptom", "咳嗽"), fact("duration", "病程", value="两天")], {"chief_complaint": "complete", "present_illness": "partial"}, [required("chief_complaint", "咳嗽", "两天"), required("present_illness", "37.8℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("肺部感染待排", "FEVER_RESP_V1_PULMONARY_INFECTION")], "低热伴咳嗽"),
        ("ce2e_v1_039_fever_no_temperature", "missing_measurement", segs(("患者", "发烧，没量体温。")), [fact("symptom", "发热")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")], "发热但未测体温"),
    ]
    for spec in remaining_specs:
        case_id, scenario, segments, facts, statuses, required_items, candidates, title = spec
        fcase(case_id, scenario, segments, facts, statuses, required_items, candidates, title)

    non_fever_specs = [
        ("ce2e_v1_013_insufficient_hot", "insufficient", segs(("患者", "不舒服，有点热。")), [fact("symptom", "发热", "uncertain")], {"chief_complaint": "missing", "present_illness": "missing"}, [], "信息不足的发热口语"),
        ("ce2e_v1_014_out_of_scope_abdominal", "out_of_scope", segs(("患者", "我肚子痛，没有发烧。")), [fact("symptom", "发热", "absent"), fact("symptom", "腹痛")], {"chief_complaint": "missing", "present_illness": "complete"}, [required("present_illness", "否认发热")], "腹痛且否认发热"),
        ("ce2e_v1_023_insufficient_general", "insufficient", segs(("患者", "今天有点不舒服。")), [], {"chief_complaint": "missing", "present_illness": "missing"}, [], "一般不适信息不足"),
        ("ce2e_v1_024_unspecified_treatment", "treatment_without_symptom", segs(("患者", "吃了药以后好多了。")), [fact("treatment", "既往处理")], {"previous_treatment": "partial", "chief_complaint": "missing"}, [required("previous_treatment", "处理")], "只有不明用药"),
        ("ce2e_v1_026_absent_fever_cough", "negation", segs(("患者", "没有发热，也没有咳嗽。")), [fact("symptom", "发热", "absent"), fact("symptom", "咳嗽", "absent")], {"chief_complaint": "missing", "present_illness": "complete"}, [required("present_illness", "否认发热")], "否认发热和咳嗽"),
        ("ce2e_v1_027_self_correction_absent", "self_correction", segs(("患者", "刚才说发烧，其实没有发热。")), [fact("symptom", "发热", "absent")], {"chief_complaint": "missing", "present_illness": "complete"}, [required("present_illness", "否认发热")], "自我纠正否认发热"),
        ("ce2e_v1_033_out_of_scope_hypertension", "out_of_scope", segs(("患者", "我血压高，头晕。")), [fact("symptom", "头晕"), fact("condition", "高血压")], {"chief_complaint": "missing", "present_illness": "missing"}, [], "高血压头晕不属发热包"),
        ("ce2e_v1_034_out_of_scope_bite", "out_of_scope", segs(("患者", "左手被咬了两个小时，局部肿痛。")), [fact("injury", "咬伤"), fact("symptom", "肿痛"), fact("duration", "病程", value="两个小时")], {"chief_complaint": "complete", "present_illness": "complete"}, [], "咬伤病例不属发热包"),
        ("ce2e_v1_035_allergy_fact", "out_of_scope", segs(("患者", "青霉素过敏。")), [fact("allergy", "青霉素过敏")], {"allergy_history": "complete"}, [required("allergy_history", "青霉素")], "过敏史事实"),
        ("ce2e_v1_036_absent_fever_synonym_headache", "negation_synonym", segs(("患者", "没有发烧，脑袋疼。")), [fact("symptom", "发热", "absent"), fact("symptom", "头痛")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "头痛"), required("present_illness", "否认发热")], "否认发烧和头痛同义词"),
        ("ce2e_v1_040_question_style_absent", "doctor_question_negation", segs(("患者", "医生问发热吗，患者说没有。")), [fact("symptom", "发热", "absent")], {"chief_complaint": "missing", "present_illness": "complete"}, [required("present_illness", "否认发热")], "转述式否认发热"),
    ]
    for case_id, scenario, segments, facts, statuses, required_items, title in non_fever_specs:
        ncase(case_id, scenario, segments, facts, statuses, required_items, title)

    for case_id, scenario, segments, exp, title in items:
        add(cases, case_id, "development", scenario, segments, exp, title)
    return cases


def final_check_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    specs = [
        ("041_final_short_fever", "short_fever_temp", segs(("患者", "发烧38.5度。")), [fact("symptom", "发热"), fact("measurement", "体温", value="38.5℃")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热", "38.5℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")]),
        ("042_final_headache_temp", "short_fever_headache", segs(("患者", "头很痛，体温39度。")), [fact("symptom", "头痛"), fact("measurement", "体温", value="39℃"), fact("symptom", "发热")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热伴头痛")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("流感样症状参考", "FEVER_RESP_V1_INFLUENZA_LIKE")]),
        ("043_final_fever_two_days", "duration", segs(("患者", "发热两天。")), [fact("symptom", "发热"), fact("duration", "病程", value="两天")], {"chief_complaint": "complete", "present_illness": "partial"}, [required("chief_complaint", "发热两天")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")]),
        ("044_final_negative_fever", "negation", segs(("患者", "没有发烧，只有头疼。")), [fact("symptom", "发热", "absent"), fact("symptom", "头痛")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "头痛")], []),
        ("045_final_resolved", "resolved", segs(("患者", "前面发烧，现在不烧了。")), [fact("symptom", "发热", "resolved")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("present_illness", "目前已缓解")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")]),
        ("046_final_cough_fever", "fever_cough", segs(("患者", "咳了两天，今天体温39度。")), [fact("symptom", "咳嗽"), fact("duration", "病程", value="两天"), fact("measurement", "体温", value="39℃"), fact("symptom", "发热")], {"chief_complaint": "complete", "present_illness": "partial"}, [required("present_illness", "体温约39℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("肺部感染待排", "FEVER_RESP_V1_PULMONARY_INFECTION")]),
        ("047_final_three_party", "three_party", segs(("医生", "哪里不舒服？"), ("家属", "她昨晚开始发烧。"), ("患者", "头痛。")), [fact("symptom", "发热"), fact("duration", "病程", value="昨晚开始"), fact("symptom", "头痛")], {"chief_complaint": "complete", "present_illness": "partial"}, [required("chief_complaint", "发热伴头痛")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("流感样症状参考", "FEVER_RESP_V1_INFLUENZA_LIKE")]),
        ("048_final_ibuprofen", "treatment_effect", segs(("患者", "刚吃了布洛芬，退热了。")), [fact("treatment", "既往处理", value="服用布洛芬后体温下降"), fact("symptom", "发热", "resolved")], {"previous_treatment": "partial", "present_illness": "partial"}, [required("previous_treatment", "布洛芬")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")]),
        ("049_final_high_fever", "danger_signal", segs(("患者", "体温40度，头痛。")), [fact("measurement", "体温", value="40℃"), fact("symptom", "发热"), fact("symptom", "头痛")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "40℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("流感样症状参考", "FEVER_RESP_V1_INFLUENZA_LIKE")]),
        ("050_final_info_insufficient", "insufficient", segs(("患者", "有点难受。")), [], {"chief_complaint": "missing", "present_illness": "missing"}, [], []),
        ("051_final_out_scope_allergy", "out_of_scope", segs(("患者", "我对青霉素过敏。")), [fact("allergy", "青霉素过敏")], {"allergy_history": "complete"}, [required("allergy_history", "青霉素")], []),
        ("052_final_out_scope_abdominal", "out_of_scope", segs(("患者", "腹痛一天，没有发热。")), [fact("symptom", "腹痛"), fact("duration", "病程", value="一天"), fact("symptom", "发热", "absent")], {"chief_complaint": "complete", "present_illness": "partial"}, [required("present_illness", "否认发热")], []),
        ("053_final_asr_typo_temp", "asr_typo", segs(("患者", "体瘟三十九度。")), [fact("measurement", "体温", value="39℃"), fact("symptom", "发热")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "39℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")]),
        ("054_final_no_fever_cough", "negation", segs(("患者", "不发烧，有点咳。")), [fact("symptom", "发热", "absent"), fact("symptom", "咳嗽")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "咳嗽")], []),
        ("055_final_fever_no_course", "missing_duration", segs(("患者", "发热，体温38度。")), [fact("symptom", "发热"), fact("measurement", "体温", value="38℃")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热", "38℃")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")]),
        ("056_final_fever_cough_no_temp", "fever_cough", segs(("患者", "发烧，还一直咳。")), [fact("symptom", "发热"), fact("symptom", "咳嗽")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP"), candidate("肺部感染待排", "FEVER_RESP_V1_PULMONARY_INFECTION")]),
        ("057_final_doctor_no_answer", "doctor_question_negation", segs(("医生", "有没有发热？"), ("患者", "没有。")), [fact("symptom", "发热", "absent")], {"chief_complaint": "missing", "present_illness": "complete"}, [required("present_illness", "否认发热")], []),
        ("058_final_fever_after_medicine", "resolved_treatment", segs(("患者", "昨天发热，吃退热药后降下来了。")), [fact("symptom", "发热", "resolved"), fact("treatment", "既往处理", value="服用退热药")], {"chief_complaint": "partial", "present_illness": "partial", "previous_treatment": "partial"}, [required("previous_treatment", "退热药")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")]),
        ("059_final_fever_with_breath", "danger_signal", segs(("患者", "发热39度，还有气促。")), [fact("symptom", "发热"), fact("measurement", "体温", value="39℃"), fact("symptom", "气促")], {"chief_complaint": "partial", "present_illness": "partial"}, [required("chief_complaint", "发热")], [candidate("发热待查", "FEVER_RESP_V1_FEVER_WORKUP")]),
        ("060_final_out_scope_chest_pain", "out_of_scope", segs(("患者", "胸痛半天，没有发烧。")), [fact("symptom", "胸痛"), fact("duration", "病程", value="半天"), fact("symptom", "发热", "absent")], {"chief_complaint": "complete", "present_illness": "partial"}, [required("present_illness", "否认发热")], []),
    ]
    for suffix, scenario, segments, facts, statuses, required_items, candidates in specs:
        case_id = f"ce2e_v1_{suffix}"
        if candidates:
            exp = fever_expected(
                segments,
                facts=facts,
                field_status=statuses,
                required_content=required_items,
                candidates=candidates,
                followups=["症状持续多久了？"] if any(item["name"] == "发热待查" for item in candidates) else [],
                risks=[risk("fever_safety", "持续高热", "气促")] if scenario == "danger_signal" else None,
            )
        else:
            exp = non_fever_expected(
                segments,
                facts=facts,
                field_status=statuses,
                required_content=required_items,
            )
        add(cases, case_id, "final_check", scenario, segments, exp, f"冻结检查案例 {suffix}")
    return cases


def write_dataset() -> None:
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT.parent / "reports").mkdir(parents=True, exist_ok=True)

    cases = development_cases() + final_check_cases()
    if len(cases) != 60:
        raise RuntimeError(f"expected 60 cases, got {len(cases)}")
    if sum(1 for case in cases if case["split"] == "development") != 40:
        raise RuntimeError("expected 40 development cases")
    if sum(1 for case in cases if case["split"] == "final_check") != 20:
        raise RuntimeError("expected 20 final_check cases")

    manifest_cases = []
    for case in cases:
        case_path = CASE_DIR / f"{case['case_id']}.json"
        case_path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_cases.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "scenario_type": case["scenario_type"],
                "case_path": f"cases/{case['case_id']}.json",
            }
        )

    manifest = {
        "dataset_version": "field_disease_pack_v1",
        "schema_version": "clinical_e2e_case_v1",
        "evaluation_mode": "text_to_record_disease_pack",
        "privacy": {
            "synthetic": True,
            "contains_real_patient_data": False,
            "note": "All cases are synthetic or classroom-style examples. No real patient data is included.",
        },
        "split_policy": {
            "development": "May be inspected while fixing production behavior.",
            "final_check": "Frozen check split; do not tune rules by reading failures after freeze.",
        },
        "case_count": len(cases),
        "split_counts": {
            "development": 40,
            "final_check": 20,
        },
        "cases": manifest_cases,
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "README.md").write_text(
        "# field_disease_pack_v1 clinical E2E evaluation\n\n"
        "This dataset evaluates synthetic text/role segments through clinical fact extraction, medical record fields, and the fever/respiratory disease pack.\n\n"
        "- It does not evaluate ASR, diarization, browser recording, role thresholds, or edge deployment.\n"
        "- `development` cases may be inspected while fixing product behavior.\n"
        "- `final_check` cases are a frozen check split and must not be used to tune rules after freezing.\n"
        "- All cases are synthetic and contain no real patient data.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_dataset()
    print(json.dumps({"created_cases": 60, "root": str(ROOT)}, ensure_ascii=False))
