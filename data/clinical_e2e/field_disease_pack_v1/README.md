# field_disease_pack_v1 clinical E2E evaluation

This dataset evaluates synthetic text/role segments through clinical fact extraction, medical record fields, and the fever/respiratory disease pack.

- It does not evaluate ASR, diarization, browser recording, role thresholds, or edge deployment.
- `development` cases may be inspected while fixing product behavior.
- `final_check` cases are a frozen check split and must not be used to tune rules after freezing.
- All cases are synthetic and contain no real patient data.
