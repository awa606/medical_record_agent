from scripts.experiments.realtime_demo_spike import BUDGET, arm_summary, resource_violation


def test_resource_preflight_reserves_new_model_allocation_and_free_memory():
    assert resource_violation({"linux_available_mib": 2990, "process_peak_rss_mib": 100}, before_new_model=True)
    assert resource_violation({"linux_available_mib": 8000, "process_peak_rss_mib": 100}, before_new_model=True) is None
    assert resource_violation({"linux_available_mib": 3000, "process_peak_rss_mib": 5200}) == "SPIKE_PROCESS_PEAK_EXCEEDED"
    assert resource_violation({"linux_available_mib": 2000, "process_peak_rss_mib": 4000}) == "SPIKE_AVAILABLE_MEMORY_LOW"
    assert BUDGET["process_peak_rss_mib_max"] == 5120


def test_small_latency_does_not_hide_missing_first_text_or_wrong_order():
    rows = [{"sequence": 0, "processing_seconds": .1, "chunk_end_latency_seconds": .1}]
    assert not arm_summary(rows, None, 60)["engineering_targets_met"]
    assert arm_summary(rows, 2.1, 60)["engineering_targets_met"]
    rows.append({"sequence": 0, "processing_seconds": .1, "chunk_end_latency_seconds": .1})
    assert not arm_summary(rows, 2.1, 60)["engineering_targets_met"]


def test_engineering_latency_success_never_claims_microphone_role_or_cer():
    result = arm_summary([{"sequence": 0, "processing_seconds": .1, "chunk_end_latency_seconds": .1}], 2.1, 60)
    assert all(result[key] == "NOT_TESTED" for key in ("physical_microphone", "role_accuracy", "cer", "browser_sse_delivery"))
