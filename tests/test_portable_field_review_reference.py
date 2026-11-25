"""Exercise the bootstrapping used by the synthetic Windows field-review trial."""

import runpy
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.main import app
from tests.auth_helpers import login_as_admin

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "experiments/course-defense-20261118/field-review-trial/prepare_reference.py"
REFERENCE = ROOT / "data/knowledge/review/outpatient-information-page/six-clauses.json"


@pytest.mark.parametrize("disable_while_interrupted", [False, True])
def test_recover_unfinished_import_and_respect_admin_disable(tmp_path, monkeypatch, disable_while_interrupted):
    """The previous package returned 503 with an empty database and a missing fallback library."""
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "合成就诊.sqlite3"))
    frozen = tmp_path / "固定素材/六条文书释义.json"
    frozen.parent.mkdir()
    frozen.write_bytes(REFERENCE.read_bytes().replace(b"\r\n", b"\n"))
    prepare = runpy.run_path(str(RECIPE), init_globals={"HERE": tmp_path})["prepare_reference"]

    with TestClient(app) as client:
        login_as_admin(client)

        def api(method, path, data=None):
            result = client.request(method, path, json=data)
            assert result.is_success, (path, result.status_code)
            return result.json()

        def lose_import_reply(method, path, data=None):
            reply = api(method, path, data)
            if path == "/api/knowledge/admin/import":
                raise ConnectionError("import reply lost")
            return reply

        with pytest.raises(ConnectionError):
            prepare(tmp_path, lose_import_reply)
        documents = "/api/knowledge/admin/documents"
        [imported] = api("GET", documents)["documents"]
        document_path = documents + "/" + imported["document_id"]
        if disable_while_interrupted:
            api("POST", document_path + "/disable")

        expected = "managed" if disable_while_interrupted else "finished"
        assert prepare(tmp_path, api) == expected
        query = {"query": "过敏", "related_fields": ["allergy_history"]}
        results = api("POST", "/api/knowledge/retrieve", query)["results"]
        assert {item["source_id"] for item in results} == (
            set() if disable_while_interrupted else {"mra-review-outpatient-info-2024"}
        )
        if not disable_while_interrupted:
            api("POST", document_path + "/disable")
        assert prepare(tmp_path, api) == expected
        assert api("POST", "/api/knowledge/retrieve", query)["results"] == []
