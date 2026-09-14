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
