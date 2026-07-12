# Diarization Engine Comparison With Quality Gate

- Sample: `three_speaker_alimeeting_01`
- Source: AliMeeting Eval, CC BY-SA 4.0
- Boundary: AliMeeting is a public meeting sample; it is used only to test multi-speaker diarization.
- Reference speaker count: `4`
- Reference turn count: `60`
- Quality gate: mixed_utterance_rate <= `0.3`, boundary_f1 >= `0.5`, speaker_count_error <= `1`

| Engine | Status | Gate | Turns | speaker_count_error | boundary_f1 | mixed_utterance_rate | role_consistency | DER | JER | RTF | RSS peak MB | Reason |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| pyannote_community_1 | `skipped` | `blocked` | - | - | - | - | - | - | - | - | - | HF_TOKEN is required for pyannote Community-1 |

## Conclusion

- No measured engine passed the quality gate. Do not use these results for automatic doctor/patient role mapping.
- This public meeting sample is only diarization evidence. It is not medical consultation accuracy evidence.
