"""Opt-in local transport and field contract; all requests use local test doubles."""
from io import BytesIO
import hashlib
import json
import os
import ssl
from urllib.error import URLError
from unittest.mock import Mock, patch

import pytest

from app.services.llm import deepseek_provider as dp
from app.services.llm.ollama_provider import numbered_source


TEXT = "患者：发热两天，没有胸痛。"
PROXY = "http://127.0.0.1:57777"
KEY = "never-print-test-key"


def provider(tmp_path, **settings):
    return dp.DeepSeekDemoProvider(api_key=KEY, output=tmp_path / "diagnostics",
        ledger=dp.BudgetLedger(tmp_path / "ledger.json"), single_use=True, **settings)


def configured_env(tmp_path):
    return {"MRA_ANONYMIZE": "1", "ONLINE_LLM_API_BASE": "https://api.deepseek.com",
        "ONLINE_LLM_MODEL": dp.MODEL, "ONLINE_LLM_API_KEY_FILE": "", "ONLINE_LLM_API_KEY": KEY,
        "ONLINE_LLM_BUDGET_LEDGER": str(tmp_path / "ledger.json"),
        "ONLINE_LLM_DIAGNOSTICS_DIR": str(tmp_path / "diagnostics"),
        "ONLINE_LLM_PROXY_URL": "", "ONLINE_LLM_FIELD_CONTRACT": "legacy",
        "MEDICAL_RECORD_AGENT_DB": str(tmp_path / "identity.sqlite3")}


def response(payload):
    return BytesIO(json.dumps(payload, ensure_ascii=False).encode())


def completion():
    return {"id": "local-test", "model": dp.MODEL,
        "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50}}


@pytest.mark.parametrize("url", [PROXY, "http://localhost:8080", "http://host.docker.internal:57777"])
def test_explicit_local_proxy_is_opt_in_and_preserves_verified_https(tmp_path, url):
    p = provider(tmp_path, https_proxy_url=url)
    original = dp.request.build_opener
    with patch.object(dp.request, "build_opener", wraps=original) as build:
        opener = p._opener()
    args = build.call_args.args
    assert len(args) == 2 and isinstance(args[0], dp.request.ProxyHandler)
    assert args[0].proxies == {"https": url}
    assert isinstance(args[1], dp.NoRedirect)
    handlers = [item for item in opener.handlers if isinstance(item, dp.request.HTTPSHandler)]
    assert len(handlers) == 1
    context = handlers[0]._context
    assert context is None or (context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname)
    assert any(isinstance(item, dp.NoRedirect) for item in opener.handlers)


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:57777", "http://remote.example:8080", "http://127.0.0.2:8080",
    "http://127.0.0.1.evil.example:57777", "http://127.0.0.1:57777/",
    "http://127.0.0.1:57777/path", "http://127.0.0.1:57777?x=1",
    "http://127.0.0.1:57777?", "http://127.0.0.1:57777#fragment",
    "http://user:password@127.0.0.1:57777", "http://@localhost:57777",
    "http://127.0.0.1", "http://127.0.0.1:0", "http://127.0.0.1:65536",
    "http://127.0.0.1:57777\n", " http://127.0.0.1:57777", "http://[::1]:57777",
])
def test_proxy_validation_rejects_nonlocal_or_credential_bearing_routes_before_io(tmp_path, url):
    with patch.object(dp.request, "build_opener") as build:
        with pytest.raises(dp.SpikeError, match="^DEEPSEEK_PROXY_NOT_ALLOWED$"):
            provider(tmp_path, https_proxy_url=url)
    build.assert_not_called()
    assert not (tmp_path / "ledger.json").exists()
    assert not (tmp_path / "diagnostics").exists()


def test_default_route_ignores_global_proxy_environment(tmp_path):
    p = provider(tmp_path)
    with patch.dict(os.environ, {"HTTPS_PROXY": "http://remote.example:9999", "HTTP_PROXY": "http://remote.example:9999",
                                "ALL_PROXY": "socks5://remote.example:9999", "NO_PROXY": ""}), \
         patch.object(dp.request, "build_opener", return_value=Mock()) as build:
        p._opener()
    assert build.call_args.args[0].proxies == {}
    assert p.https_proxy_url == "" and p.field_contract == "legacy"


def test_global_no_proxy_cannot_bypass_the_explicit_https_connect_route(tmp_path):
    p = provider(tmp_path, https_proxy_url=PROXY)
    opener = p._opener()
    handler = next(item for item in opener.handlers if isinstance(item, dp.request.ProxyHandler))
    req = dp.request.Request(dp.ENDPOINT)
    with patch.dict(os.environ, {"NO_PROXY": "*", "no_proxy": "*"}):
        handler.https_open(req)
    assert req.type == "https"
    assert req.host == "127.0.0.1:57777"
    assert req._tunnel_host == "api.deepseek.com"


def test_environment_explicit_options_are_read_without_global_proxy_inheritance(tmp_path):
    env = configured_env(tmp_path)
    env.update(ONLINE_LLM_PROXY_URL=PROXY, ONLINE_LLM_FIELD_CONTRACT="clause_v1",
               HTTPS_PROXY="http://unapproved-global.example:9999")
    with patch.dict(os.environ, env):
        p = dp.DeepSeekDemoProvider.from_environment()
    assert p.https_proxy_url == PROXY and p.field_contract == "clause_v1"
    assert not (tmp_path / "ledger.json").exists()


@pytest.mark.parametrize("contract", ["clause-v1", "future", "CLAUSE_V1", " legacy"])
def test_unknown_contract_is_rejected_without_silently_using_legacy(tmp_path, contract):
    with pytest.raises(dp.SpikeError, match="^DEEPSEEK_FIELD_CONTRACT_NOT_ALLOWED$"):
        provider(tmp_path, field_contract=contract)
    assert not (tmp_path / "ledger.json").exists()


def test_legacy_contract_keeps_exact_prior_prompt_bytes(tmp_path):
    p = provider(tmp_path)
    assert p._numbered_source(TEXT) == numbered_source(TEXT)
    assert hashlib.sha256(p._numbered_source(TEXT).encode()).hexdigest() == "c482a9433fd3cd0eb5e4f06cf72fc4598a15cf1beeac9ce90adf412407cee38c"


def test_clause_contract_matches_locked_spike_bytes_and_changes_only_one_instruction(tmp_path):
    p = provider(tmp_path, field_contract="clause_v1")
    legacy = numbered_source(TEXT)
    clause = p._numbered_source(TEXT)
    marker = "每个value使用原句，保留否定、主体、时间、数值和单位，不改写。source_spans.text引用完整原句，index使用编号。"
    assert marker in legacy and marker not in clause
    assert hashlib.sha256(dp.CLAUSE_V1_CONTRACT.encode()).hexdigest() == "9ce0ea9120d0c53ff825a9fb98c3167030de97f43c34a2b02a5091d26c2c0e58"
    assert clause == legacy.replace(marker, dp.CLAUSE_V1_CONTRACT)
    assert hashlib.sha256(clause.encode()).hexdigest() == "a2a12b40ddda541b9e214349534a94e96e64300f071ad52e92b6819711cf5ba3"


def test_clause_contract_refuses_unknown_prompt_marker_without_guessing(tmp_path):
    p = provider(tmp_path, field_contract="clause_v1")
    with patch.object(dp, "numbered_source", return_value="unknown template"):
        with pytest.raises(dp.SpikeError, match="^DEEPSEEK_FIELD_CONTRACT_MARKER_MISSING$"):
            p._numbered_source(TEXT)


def test_probe_and_post_share_same_explicit_route_and_keep_payload_configuration(tmp_path):
    p = provider(tmp_path, https_proxy_url=PROXY, field_contract="clause_v1")
    routes, requests = [], []
    def build(*handlers):
        routes.append(handlers[0].proxies)
        assert isinstance(handlers[1], dp.NoRedirect)
        opener = Mock()
        def open_request(req, timeout):
            requests.append(req)
            return response({"data": [{"id": dp.MODEL}]}) if req.method == "GET" else response(completion())
        opener.open.side_effect = open_request
        return opener
    with patch.dict(os.environ, configured_env(tmp_path)), patch.object(dp.request, "build_opener", side_effect=build):
        assert p.probe()["reachable"]
        p.generate_fields_json(TEXT, timeout_seconds=1)
    assert routes == [{"https": PROXY}, {"https": PROXY}]
    assert [req.method for req in requests] == ["GET", "POST"]
    assert [req.full_url for req in requests] == ["https://api.deepseek.com/models", dp.ENDPOINT]
    payload = json.loads(requests[1].data)
    assert payload["temperature"] == 0 and payload["max_tokens"] == 4096 and payload["stream"] is False
    assert payload["model"] == dp.MODEL and payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][1]["content"] == p._numbered_source(TEXT)
    assert p.response_metadata["transport_mode"] == "explicit_local_proxy"
    assert p.response_metadata["field_contract"] == "clause_v1"
    assert PROXY not in json.dumps(p.response_metadata) and KEY not in json.dumps(p.response_metadata)
    assert len(json.loads((tmp_path / "ledger.json").read_text())["calls"]) == 1


def test_proxy_disconnect_does_not_fall_back_to_direct_or_retry(tmp_path):
    p = provider(tmp_path, https_proxy_url=PROXY, field_contract="clause_v1")
    opener = Mock()
    opener.open.side_effect = URLError(ConnectionResetError("private diagnostic text"))
    with patch.dict(os.environ, configured_env(tmp_path)), \
         patch.object(dp.request, "build_opener", return_value=opener) as build:
        with pytest.raises(dp.SpikeError, match="^TRANSPORT_CONNECTION_RESET$"):
            p.generate_fields_json(TEXT, timeout_seconds=1)
    assert build.call_count == 1 and opener.open.call_count == 1
    assert build.call_args.args[0].proxies == {"https": PROXY}
    assert p.response_metadata == {"transport_mode": "explicit_local_proxy", "field_contract": "clause_v1"}
    calls = json.loads((tmp_path / "ledger.json").read_text())["calls"]
    assert len(calls) == 1 and calls[0]["state"] == "failed_reservation_retained"
    with pytest.raises(dp.SpikeError, match="^AUTOMATIC_RETRY_FORBIDDEN$"):
        p.generate_fields_json(TEXT, timeout_seconds=1)
    files = "\n".join(path.read_text(encoding="utf8") for path in tmp_path.rglob("*.json"))
    assert KEY not in files and PROXY not in files and "private diagnostic text" not in files


def test_explicit_proxy_cannot_enable_redirects_or_change_official_endpoint(tmp_path):
    p = provider(tmp_path, https_proxy_url=PROXY)
    opener = p._opener()
    redirects = [item for item in opener.handlers if isinstance(item, dp.request.HTTPRedirectHandler)]
    assert len(redirects) == 1 and isinstance(redirects[0], dp.NoRedirect)
    with pytest.raises(dp.SpikeError, match="^HTTP_REDIRECT_REJECTED$"):
        redirects[0].redirect_request(dp.request.Request(dp.ENDPOINT), None, 307, "redirect", {}, "https://remote.example")
    with pytest.raises(dp.SpikeError, match="^ENDPOINT_NOT_ALLOWED$"):
        provider(tmp_path, https_proxy_url=PROXY, endpoint="https://unapproved.example/chat/completions")
