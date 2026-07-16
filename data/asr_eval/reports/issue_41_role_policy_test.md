# executable_clinical_v1 speaker-role baseline

- dataset_version: `executable_clinical_v1`
- schema_version: `executable-speaker-role-dataset-v1`
- evaluation_mode: `oracle_transcript_role_decision`
- audio_pipeline_evaluated: `False`
- evaluation_policy_override: `{'auto_accept_threshold': 0.82}`
- provider: `rules`
- product_accuracy: `True`
- sample_count: 11
- selected_split: `test`

## Metrics

| metric | value | 95% CI |
| --- | ---: | --- |
| role_accuracy | 1.0 | [0.8513, 1.0] |
| auto_accept_accuracy | 1.0 | [0.8318, 1.0] |
| auto_accept_coverage | 0.8636 | [0.6666, 0.9525] |
| manual_confirmation_rate | 0.1364 | [0.0475, 0.3334] |
| speaker_count_accuracy | 1.0 | [0.7412, 1.0] |
| mixed_utterance_rate | 0.0588 | [0.0202, 0.1592] |
| keyword_recall | 0.9333 | [0.7868, 0.9815] |
| high_confidence_error_count | 0 | - |

## Scenario coverage

- `noise_interruption_overlap`: 1
- `noisy_background`: 1
- `single_reader_counterexample`: 2
- `three_party_family`: 2
- `two_party`: 5

## Split coverage

- `test`: 11
