from scripts.run_evt_checkpoint import build_matrix


def _clinical_report() -> dict:
    fields = {
        "chief_complaint": "complete",
        "present_illness": "complete",
        "previous_treatment": "missing",
        "accompanying_symptoms": "missing",
        "past_history": "missing",
        "allergy_history": "missing",
        "physical_exam": "missing",
    }
    return {
        "provider_mode": "demo_mock_default",
        "audio_pipeline_evaluated": False,
        "metrics": {
            "unsupported_content_count": 0,
            "forbidden_candidate_count": 0,
            "confirmed_diagnosis_phrase_count": 0,
        },
        "cases": [{"case_id": f"c{i}", "split": "final_check", "actual": {"field_status": fields}} for i in range(20)],
    }


def test_build_matrix_keeps_mock_results_partial_and_hardware_blocked() -> None:
    checks = {
        name: {"status": "PASS"}
        for name in ("workflow_gate", "role_gate", "recovery", "knowledge_demo")
    }
    dependencies = {"modules": {}, "cuda": {"available": True}}

    matrix = {item["id"]: item for item in build_matrix(_clinical_report(), dependencies, checks)}

    assert len(matrix) == 13
    assert matrix["T01"]["status"] == "PARTIAL"
    assert matrix["T02"]["status"] == "PARTIAL"
    assert matrix["T08"]["status"] == "HARDWARE BLOCKED"
    assert matrix["T09"]["status"] == "BLOCKED"
    assert matrix["T12"]["status"] == "BLOCKED"


def test_build_matrix_uses_real_supplemental_evidence_without_promoting_development_sets() -> None:
    checks = {
        name: {"status": "PASS"}
        for name in ("workflow_gate", "role_gate", "recovery", "knowledge_demo")
    }
    asr_audit = {
        "unique_duration_minutes": 15.3,
        "benchmarks": [
            {
                "engine": "sensevoice-small",
                "macro_cer": 0.16695,
                "macro_keyword_recall": 0.73333,
                "max_rtf": 0.161,
                "t09_gate": "FAIL",
            }
        ],
    }
    knowledge = {
        "metrics": {
            "query_count": 20,
            "recall_at_5": 0.95,
            "citation_completeness": 1.0,
            "source_less_citation_count": 0,
            "retrieval_modes": ["hybrid_v1"],
        }
    }
    semantic = {"frozen_test": {"lora": {"schema_complete_rate": 1.0, "unsupported_fact_count": 16}}}

    matrix = {
        item["id"]: item
        for item in build_matrix(
            _clinical_report(),
            {"modules": {}, "cuda": {"available": True}},
            checks,
            asr_audit=asr_audit,
            knowledge_report=knowledge,
            semantic_report=semantic,
        )
    }

    assert matrix["T09"]["status"] == "FAIL"
    assert matrix["T11"]["status"] == "PARTIAL"
    assert matrix["T02"]["status"] == "PARTIAL"
    assert matrix["T02"]["measured"]["rejected_lora_unsupported_fact_count"] == 16
