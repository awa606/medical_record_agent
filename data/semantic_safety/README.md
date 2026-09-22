# Clinical Assertion Safety Set v1

This directory contains 240 deterministic, synthetic Chinese sentences for Alpha
engineering regression. It covers allergy and respiratory symptom assertion,
experiencer, temporality, certainty, clinician questions, and temperature units.

The set contains no patient data. It is not a clinical validation set, must not be
used as treatment supervision, and does not establish product safety or efficacy.
Regenerate it with:

```powershell
python -X utf8 scripts/build_semantic_safety_set.py
```

Evaluate it with:

```powershell
python -X utf8 scripts/evaluate_semantic_safety.py `
  data/semantic_safety/clinical_assertion_v1.jsonl
```
