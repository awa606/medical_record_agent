# field_disease_pack_v1 baseline

- dataset_version: `field_disease_pack_v1`
- schema_version: `clinical_e2e_case_v1`
- evaluation_mode: `text_to_record_disease_pack`
- audio_pipeline_evaluated: `False`
- sample_count: 60
- selected_split: `all`
- provider_mode: `demo_mock_default`
- hard_gate_passed: `False`

## Metrics

| metric | value |
| --- | ---: |
| clinical_fact_accuracy | 0.8456 |
| assertion_accuracy | 0.8095 |
| field_status_accuracy | 0.808 |
| field_content_accuracy | 0.8533 |
| field_evidence_coverage | 1.0 |
| field_fact_link_coverage | 0.9106 |
| candidate_recall | 0.8036 |
| candidate_evidence_completeness | 1.0 |
| follow_up_question_recall | 0.5625 |
| danger_signal_recall | 0.5 |
| unsupported_content_count | 0 |
| candidate_without_evidence_count | 0 |
| confirmed_diagnosis_phrase_count | 0 |
| danger_signal_missed_count | 2 |
| unexpected_fever_pack_candidate_count | 2 |

## Split coverage

- `development`: 40
- `final_check`: 20

## Scenario coverage

- `asr_typo`: 3
- `complete_dialogue_fragment`: 1
- `danger_signal`: 4
- `doctor_question_negation`: 3
- `duration`: 3
- `fever_cough`: 3
- `fever_cough_headache`: 1
- `fever_headache`: 1
- `flu_like`: 1
- `insufficient`: 3
- `low_grade_fever_cough`: 1
- `missing_duration`: 1
- `missing_measurement`: 1
- `negation`: 5
- `negation_synonym`: 1
- `out_of_scope`: 7
- `pulmonary_reference`: 1
- `resolved`: 2
- `resolved_current_symptom`: 1
- `resolved_treatment`: 2
- `respiratory_no_fever`: 1
- `self_correction`: 1
- `short_fever_headache`: 2
- `short_fever_temp`: 2
- `temperature_only`: 1
- `three_party`: 3
- `three_party_treatment`: 1
- `treatment_effect`: 2
- `treatment_without_symptom`: 1
- `two_party_dialogue`: 1

## Hard Gate Failures

- `ce2e_v1_020_fever_chest_tightness`: danger_signal_missed:danger_signal
- `ce2e_v1_049_final_high_fever`: danger_signal_missed:fever_safety

## Notes

- This report evaluates text/role segments to clinical fields and disease-pack references.
- It does not evaluate ASR, diarization, speaker-role calibration, browser recording, or edge deployment.
- final_check cases are reported separately and must not be used to tune rules after freezing.
