import json

import pytest

from scripts.alpha51_release_archive import verify_hashes, write_hashes


def test_nested_manifests_are_verified(tmp_path):
    nested = tmp_path / "data-browser" / "manifest.json"
    nested.parent.mkdir()
    nested.write_text('{"source": "synthetic"}', encoding="utf-8")
    entries = write_hashes(tmp_path)
    assert "data-browser/manifest.json" in entries
    (tmp_path / "manifest.json").write_text(json.dumps({"files": entries}), encoding="utf-8")
    verify_hashes(tmp_path)
    nested.write_text('{"source": "changed"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="archive hash mismatch"):
        verify_hashes(tmp_path)
