import json

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.services.privacy import AnonymousResponses


DEPLOYMENT_SHA = "13051498552e7383206c7410bc10c4a7d612c62e"
PHONE = "13800130000"


def response_for(tmp_path, monkeypatch, path, payload):
    monkeypatch.setenv("MRA_ANONYMIZE", "1")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "privacy.sqlite3"))
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "deployment.json").write_text(json.dumps(payload), encoding="utf-8")
    app = FastAPI()
    app.add_middleware(AnonymousResponses)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/api/deployment.json")
    def business_data():
        return payload

    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


def test_deployment_git_sha_survives_while_other_fields_are_anonymized(tmp_path, monkeypatch):
    result = response_for(tmp_path, monkeypatch, "/static/deployment.json", {
        "version": DEPLOYMENT_SHA,
        "patient_name": "测试患者",
        "contact": PHONE,
        "nested": {"version": DEPLOYMENT_SHA, "contact": PHONE},
    })
    assert result["version"] == DEPLOYMENT_SHA
    assert result["patient_name"] != "测试患者"
    assert PHONE not in result["contact"]
    assert result["nested"]["version"] != DEPLOYMENT_SHA
    assert PHONE not in result["nested"]["contact"]


@pytest.mark.parametrize("version", [PHONE, "prefix-" + DEPLOYMENT_SHA, DEPLOYMENT_SHA + "f", DEPLOYMENT_SHA[:-1] + "g"])
def test_deployment_version_requires_a_complete_git_sha(tmp_path, monkeypatch, version):
    result = response_for(tmp_path, monkeypatch, "/static/deployment.json", {"version": version})
    assert result["version"] != version


@pytest.mark.parametrize("version", [PHONE, DEPLOYMENT_SHA])
def test_business_version_values_still_receive_anonymization(tmp_path, monkeypatch, version):
    result = response_for(tmp_path, monkeypatch, "/api/deployment.json", {"version": version})
    assert result["version"] != version
