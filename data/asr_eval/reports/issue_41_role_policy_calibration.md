# executable_clinical_v1 speaker-role baseline

- dataset_version: `executable_clinical_v1`
- schema_version: `executable-speaker-role-dataset-v1`
- evaluation_mode: `oracle_transcript_role_decision`
- audio_pipeline_evaluated: `False`
- evaluation_policy_override: `None`
- provider: `rules`
- product_accuracy: `True`
- sample_count: 12
- selected_split: `calibration`

## Metrics

| metric | value | 95% CI |
| --- | ---: | --- |
| role_accuracy | 1.0 | [0.8713, 1.0] |
| auto_accept_accuracy | 1.0 | [0.4385, 1.0] |
| auto_accept_coverage | 0.1154 | [0.04, 0.2898] |
| manual_confirmation_rate | 0.8846 | [0.7102, 0.96] |
| speaker_count_accuracy | 1.0 | [0.7575, 1.0] |
| mixed_utterance_rate | 0.05 | [0.0171, 0.137] |
| keyword_recall | 1.0 | [0.9036, 1.0] |
| high_confidence_error_count | 0 | - |

## Scenario coverage

- `interruption`: 1
- `noisy_background`: 1
- `overlap`: 1
- `single_reader_counterexample`: 1
- `three_party_family`: 3
- `two_party`: 5

## Split coverage

- `calibration`: 12
