import httpx
from fastapi.testclient import TestClient

from scripts import alpha51_gateway as gateway


def test_sessions_do_not_cross_browser_or_anonymous_requests(monkeypatch):
    clients = []

    def upstream(request):
        if request.url.path.startswith("/login/"):
            user = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, headers=[("set-cookie", f"session={user}; Path=/; HttpOnly"),
                                                ("set-cookie", "preference=compact; Path=/")], json={"ok": True})
        cookie = request.headers.get("cookie", "")
        return httpx.Response(200 if "session=" in cookie else 401, json={"cookie": cookie})

    def factory():
        client = httpx.AsyncClient(base_url="http://app:8000", transport=httpx.MockTransport(upstream))
        clients.append(client)
        return client

    monkeypatch.setattr(gateway, "new_upstream_client", factory)
    with TestClient(gateway.app) as first, TestClient(gateway.app) as second, TestClient(gateway.app) as anonymous:
        assert len(first.post("/login/doctorA").headers.get_list("set-cookie")) == 2
        assert anonymous.get("/me").status_code == 401
        second.post("/login/doctorB")
        assert "session=doctorA" in first.get("/me").json()["cookie"]
        assert "session=doctorB" in second.get("/me").json()["cookie"]
        assert anonymous.get("/me").status_code == 401
    assert clients and all(c.is_closed for c in clients)


def test_gateway_closes_failed_upstream_and_returns_503(monkeypatch):
    def fail(request):
        raise httpx.ConnectError("unavailable", request=request)

    client = httpx.AsyncClient(base_url="http://app:8000", transport=httpx.MockTransport(fail))
    monkeypatch.setattr(gateway, "new_upstream_client", lambda: client)
    with TestClient(gateway.app) as browser:
        assert browser.get("/health").status_code == 503
    assert client.is_closed
