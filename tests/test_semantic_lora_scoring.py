from scripts.semantic_scoring import score_output


def test_semantic_lora_scoring_detects_supported_and_unsupported_facts() -> None:
    target = {
        "facts": [{"type": "symptom", "name": "发热", "assertion": "present"}],
        "field_status": {"chief_complaint": "partial"},
    }
    supported = '{"facts":[{"type":"symptom","name":"发热","assertion":"present"}],"field_status":{"chief_complaint":"partial"}}'
    unsupported = '{"facts":[{"type":"symptom","name":"咳嗽","assertion":"present"}],"field_status":{"chief_complaint":"partial"}}'

    good = score_output("case-1", target, supported)
    bad = score_output("case-1", target, unsupported)

    assert good["schema_complete"] is True
    assert good["fact_recall"] == 1.0
    assert good["unsupported_fact_count"] == 0
    assert bad["fact_recall"] == 0.0
    assert bad["unsupported_fact_count"] == 1


def test_semantic_lora_scoring_rejects_non_json() -> None:
    result = score_output("case-2", {"facts": [], "field_status": {}}, "无法处理")
    assert result["valid_json"] is False
    assert result["schema_complete"] is False
