# executable_clinical_v1 speaker-role baseline

- dataset_version: `executable_clinical_v1`
- schema_version: `executable-speaker-role-dataset-v1`
- evaluation_mode: `oracle_transcript_role_decision`
- audio_pipeline_evaluated: `False`
- evaluation_policy_override: `None`
- provider: `rules`
- product_accuracy: `True`
- sample_count: 23
- selected_split: `all`

## Metrics

| metric | value | 95% CI |
| --- | ---: | --- |
| role_accuracy | 1.0 | [0.9259, 1.0] |
| auto_accept_accuracy | 1.0 | [0.5655, 1.0] |
| auto_accept_coverage | 0.1042 | [0.0453, 0.2217] |
| manual_confirmation_rate | 0.8958 | [0.7783, 0.9547] |
| speaker_count_accuracy | 1.0 | [0.8569, 1.0] |
| mixed_utterance_rate | 0.0541 | [0.025, 0.1129] |
| keyword_recall | 0.9697 | [0.8961, 0.9917] |
| high_confidence_error_count | 0 | - |

## Scenario coverage

- `interruption`: 1
- `noise_interruption_overlap`: 1
- `noisy_background`: 2
- `overlap`: 1
- `single_reader_counterexample`: 3
- `three_party_family`: 5
- `two_party`: 10

## Split coverage

- `calibration`: 12
- `test`: 11
