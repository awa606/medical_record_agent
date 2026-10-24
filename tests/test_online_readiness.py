from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app.api import runtime
from app.services.llm import factory, online_readiness


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    monkeypatch.setattr(online_readiness, "_cached_result", None)
    monkeypatch.setattr(online_readiness, "_cached_key", None)
    monkeypatch.setattr(online_readiness, "_expires_at", 0)


def provider(ok=True, error=None):
    calls = []
    def probe(**kwargs):
        calls.append(kwargs)
        return {"reachable": ok, "error_code": error}
    return SimpleNamespace(endpoint="https://api.deepseek.com/chat/completions",
                           model="deepseek-flash", api_key="test-only", probe=probe), calls


def test_readiness_probes_without_paid_generation_and_shares_concurrent_result():
    p, calls = provider()
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: online_readiness.check(p), range(4)))
    assert all(r["ok"] and r["inference_called"] is False for r in results)
    assert calls == [{"timeout_seconds": 5}]


def test_expired_or_changed_credentials_do_not_reuse_success(monkeypatch):
    p, calls = provider()
    assert online_readiness.check(p)["ok"]
    p.api_key = "changed-test-only"
    online_readiness.check(p)
    monkeypatch.setattr(online_readiness, "_expires_at", 0)
    online_readiness.check(p)
    assert len(calls) == 3


@pytest.mark.parametrize("code", ["HTTP_401", "MODEL_NOT_AVAILABLE", "NETWORK_UNAVAILABLE"])
def test_live_ready_blocks_connection_failure(monkeypatch, code):
    p, calls = provider(False, code)
    monkeypatch.setenv("ONLINE_LLM_PROFILE", "deepseek_demo")
    monkeypatch.setattr(runtime, "get_llm_status", lambda **kw: {
        "mode": "live", "provider": "online", "configured": True, "fallback": False})
    monkeypatch.setattr(factory, "create_llm_provider", lambda **kw: p)
    result = runtime._check_provider()
    assert result["ok"] is False
    assert result["error"] == code
    assert result["status"]["checked"] is True
    assert len(calls) == 1


def test_network_exception_does_not_leak_exception_body():
    p, _ = provider()
    def broken(**kwargs):
        raise RuntimeError("private-value-must-not-appear")
    p.probe = broken
    result = online_readiness.check(p)
    assert result["ok"] is False
    assert "private-value" not in str(result)


def test_live_online_success_is_connection_only(monkeypatch):
    p, _ = provider()
    monkeypatch.setenv("ONLINE_LLM_PROFILE", "deepseek_demo")
    monkeypatch.setattr(runtime, "get_llm_status", lambda **kw: {
        "mode": "live", "provider": "online", "configured": True, "fallback": False})
    monkeypatch.setattr(factory, "create_llm_provider", lambda **kw: p)
    result = runtime._check_provider()
    assert result["ok"] is True
    assert result["status"]["runtime_probe"]["scope"] == "authenticated_model_availability"


@pytest.mark.parametrize("profile", ["", "unknown"])
def test_live_online_config_alone_is_not_readiness(monkeypatch, profile):
    monkeypatch.setenv("ONLINE_LLM_PROFILE", profile)
    monkeypatch.setattr(runtime, "get_llm_status", lambda **kw: {
        "mode": "live", "provider": "online", "configured": True, "fallback": False})
    result = runtime._check_provider()
    assert result["ok"] is False
    assert result["error"] == "ONLINE_READINESS_PROFILE_REQUIRED"
