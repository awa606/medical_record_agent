"""Exercise the classroom response filter on synthetic data in a separate database."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def check(bundle, actions):
    sys.path.insert(0, str(bundle.resolve() / "运行源"))
    from app.services import privacy

    with TemporaryDirectory(prefix="classroom-filter-") as work:
        os.environ.update(MRA_ANONYMIZE="1", MEDICAL_RECORD_AGENT_DB=str(Path(work) / "test.sqlite3"))
        source = privacy._connection
        calls = 0

        def counted():
            nonlocal calls
            calls += 1
            return source()

        privacy._connection = counted
        scalar_fields = {"content_hash": "f" * 64, "n": 4, "ready": False, "empty": "", "rows": [None, {}]}
        assert privacy.anonymize_payload(scalar_fields) == scalar_fields
        assert calls == 0
        record = json.loads(actions.read_text(encoding="utf-8").splitlines()[0])["json"]["fields"]
        assert privacy.anonymize_payload(record) == record
        field_reads = calls
        sample_name = "虚构甲"
        email = "demo@example.invalid"
        opaque = hashlib.sha256(b"synthetic revision").hexdigest()
        payload = [{"patient_name": sample_name, "note": f"{sample_name} 复核 {email}"},
                   {"followup": sample_name, "content_hash": opaque}, None, False, 3]
        result = privacy.anonymize_payload(payload)
        alias = result[0]["patient_name"]
        redacted_mail = result[0]["note"].split()[-1]
        assert alias.startswith("患者-") and redacted_mail.startswith("[已脱敏-联系方式-")
        assert result[0]["note"] == f"{alias} 复核 {redacted_mail}"
        assert result[1] == {"followup": alias, "content_hash": opaque}
        assert result[2:] == [None, False, 3]
        assert privacy.anonymize_payload([sample_name, email]) == [alias, redacted_mail]
        return {"schema": "classroom-filter-check-v1", "field_tree_identity_connections": field_reads,
                "opaque_and_empty_values_need_no_database": True,
                "ordinary_fields_intact": True, "name_and_email_redacted": True,
                "repeated_identity_consistent": True, "revision_digest_intact": True,
                "scalar_types_intact": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("actions", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.bundle, args.actions), indent=2))
