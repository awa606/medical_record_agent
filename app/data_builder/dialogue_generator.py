"""根据证候、症状和问诊模板生成模拟医患对话。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data_builder.kb_builder import load_or_build_knowledge_base
from app.data_builder.paths import OUTPUT_DIR, ensure_data_builder_dirs


ANSWER_BANK: dict[str, str] = {
    "SYM_FEVER": "有发热，自己感觉身上发热。",
    "SYM_MILD_FEVER": "发热不算特别重，像低热。",
    "SYM_HIGHER_FEVER": "发热比较明显，感觉体温上来了。",
    "SYM_CHILLS": "怕冷挺明显，盖被子也想缩着。",
    "SYM_SLIGHT_CHILLS": "只是有点怕风，不算特别怕冷。",
    "SYM_NO_SWEAT": "基本不出汗，感觉汗出不来。",
    "SYM_SPONTANEOUS_SWEAT": "容易自己出汗，稍微活动就出汗。",
    "SYM_HEADACHE": "有点头痛。",
    "SYM_HEAVY_HEAD": "头昏沉，身体也觉得沉重。",
    "SYM_BODY_ACHE": "全身有些酸痛。",
    "SYM_SORE_THROAT": "嗓子疼，吞咽时更明显。",
    "SYM_CLEAR_NASAL_DISCHARGE": "鼻涕是清的，比较稀。",
    "SYM_YELLOW_NASAL_DISCHARGE": "鼻涕偏黄，也有点黏。",
    "SYM_COUGH": "有点咳嗽。",
    "SYM_YELLOW_SPUTUM": "有痰，颜色偏黄。",
    "SYM_FATIGUE": "这两天没劲，容易累。",
    "SYM_SHORT_BREATH": "说话多了觉得气不太够。",
    "SYM_RECURRENT_COLD": "平时确实比较容易感冒。",
    "SYM_CHEST_OPPRESSION": "胸口有点闷。",
    "SYM_NAUSEA": "胃里不舒服，有点想吐。",
    "SYM_THIN_WHITE_COATING": "医生查体提示舌苔薄白。",
    "SYM_THIN_YELLOW_COATING": "医生查体提示舌苔薄黄。",
    "SYM_GREASY_COATING": "医生查体提示舌苔偏腻。",
    "SYM_PALE_TONGUE": "医生查体提示舌质偏淡。",
    "SYM_FLOAT_TIGHT_PULSE": "医生查体提示脉浮紧。",
    "SYM_FLOAT_RAPID_PULSE": "医生查体提示脉浮数。",
    "SYM_SOFT_RAPID_PULSE": "医生查体提示脉濡数。",
    "SYM_FLOAT_WEAK_PULSE": "医生查体提示脉浮无力。",
}


NEGATIVE_ANSWER_BY_FIELD: dict[str, str] = {
    "发热": "没有特别明显的高热。",
    "恶寒/怕风": "怕冷不算明显。",
    "出汗": "出汗情况没有特别异常。",
    "咽喉": "咽喉没有明显疼痛。",
    "鼻部症状": "鼻部症状不明显。",
    "咳嗽咳痰": "咳嗽咳痰不明显。",
    "头身不适": "头痛和全身酸痛不明显。",
    "脘腹/恶心": "没有明显胸闷或恶心。",
    "既往易感": "平时没有特别频繁感冒。",
    "舌脉": "舌脉需要医生查体后补充。",
}


def _index_by(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    """把列表按指定字段建索引，便于快速查找。"""

    return {str(item[key]): item for item in items if item.get(key)}


def _find_rule_for_syndrome(rules: list[dict[str, Any]], syndrome_id: str) -> dict[str, Any]:
    """为一个证候找到第一条匹配规则。"""

    for rule in rules:
        if rule.get("syndrome_id") == syndrome_id:
            return rule
    return {}


def _build_chief_complaint(syndrome_name: str, positive_symptom_ids: list[str], symptom_index: dict[str, dict[str, Any]]) -> str:
    """根据阳性症状合成模拟主诉。"""

    symptom_names = [
        symptom_index[symptom_id]["symptom_name"]
        for symptom_id in positive_symptom_ids[:3]
        if symptom_id in symptom_index
    ]
    joined = "、".join(symptom_names) if symptom_names else "感冒样不适"
    return f"{joined}2天，拟{syndrome_name}模拟病例"


def generate_dialogues(output_path: Path = OUTPUT_DIR / "generated_dialogues.json") -> list[dict[str, Any]]:
    """生成模拟医患对话测试集。

    生成逻辑尽量保持确定性，便于课堂演示和测试复现：每个证候生成一例，
    问诊问题来自 question_template，患者回答来自症状词典和规则库。
    """

    ensure_data_builder_dirs()
    kb = load_or_build_knowledge_base()
    tables = kb["tables"]
    syndromes = tables["syndrome"]
    symptoms = tables["symptom"]
    questions = sorted(tables["question_template"], key=lambda item: item.get("question_order") or 0)
    rules = tables["rule_base"]

    symptom_index = _index_by(symptoms, "symptom_id")
    cases: list[dict[str, Any]] = []

    for index, syndrome in enumerate(syndromes, start=1):
        syndrome_id = syndrome["syndrome_id"]
        rule = _find_rule_for_syndrome(rules, syndrome_id)
        positive_symptom_ids = list(rule.get("positive_symptom_ids") or syndrome.get("key_symptoms") or [])
        chief_complaint = _build_chief_complaint(
            syndrome["syndrome_name"],
            positive_symptom_ids,
            symptom_index,
        )

        dialogue_turns: list[dict[str, str]] = []
        dialogue_turns.append({"speaker": "医生", "text": "这次主要哪里不舒服？大概持续多久了？"})
        dialogue_turns.append({"speaker": "患者", "text": chief_complaint})

        for question in questions:
            if question["question_id"] == "Q_CHIEF":
                continue

            mapped_symptoms = set(question.get("maps_to_symptom_ids") or [])
            matched_symptoms = [sid for sid in positive_symptom_ids if sid in mapped_symptoms]

            # 舌脉属于医生查体信息，模拟对话中只提示待补充，避免把问诊当作真实查体。
            if question["target_field"] == "舌脉":
                dialogue_turns.append({"speaker": "医生", "text": question["question_text"]})
                dialogue_turns.append({"speaker": "患者", "text": "舌象和脉象请医生查体后记录。"})
                continue

            if matched_symptoms:
                patient_answer = "；".join(ANSWER_BANK.get(symptom_id, symptom_id) for symptom_id in matched_symptoms)
            else:
                patient_answer = NEGATIVE_ANSWER_BY_FIELD.get(question["target_field"], "这一项不明显。")

            dialogue_turns.append({"speaker": "医生", "text": question["question_text"]})
            dialogue_turns.append({"speaker": "患者", "text": patient_answer})

        dialogue_text = "\n".join(f"{turn['speaker']}：{turn['text']}" for turn in dialogue_turns)
        expected_fields = {
            "主诉": chief_complaint,
            "候选证候": syndrome["syndrome_name"],
            "阳性症状": [
                symptom_index[symptom_id]["symptom_name"]
                for symptom_id in positive_symptom_ids
                if symptom_id in symptom_index
            ],
            "待补充": ["舌象", "脉象", "过敏史"],
            "数据说明": "模拟病例，不包含真实个人身份信息",
        }

        cases.append(
            {
                "case_id": f"GEN_COLD_{index:03d}",
                "disease_id": syndrome["disease_id"],
                "expected_syndrome_id": syndrome_id,
                "expected_syndrome_name": syndrome["syndrome_name"],
                "chief_complaint": chief_complaint,
                "dialogue_turns": dialogue_turns,
                "dialogue_text": dialogue_text,
                "expected_symptom_ids": positive_symptom_ids,
                "expected_fields": expected_fields,
                "simulation_notice": "本病例由规则和模板自动生成，仅用于课程测试。",
            }
        )

    payload = {
        "meta": {
            "name": "感冒模拟医患对话测试集",
            "data_scope": "全部为模拟数据，不包含真实患者隐私信息",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "cases": cases,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cases
