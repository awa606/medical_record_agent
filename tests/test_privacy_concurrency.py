"""Privacy I/O must not monopolize the ASGI event loop."""
import asyncio
import json
import threading

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.services import privacy


@pytest.mark.parametrize("kind", ["json", "sse", "sse_tail"])
def test_other_requests_complete_while_privacy_io_is_pending(tmp_path, monkeypatch, kind):
    monkeypatch.setenv("MRA_ANONYMIZE", "1")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "privacy.sqlite3"))
    entered, release = threading.Event(), threading.Event()
    sanitizer_threads = []
    original = privacy.anonymize_payload

    def blocked(value):
        if isinstance(value, dict) and value.get("marker") == "slow":
            sanitizer_threads.append(threading.get_ident())
            entered.set()
            release.wait(timeout=2)
        return original(value)

    monkeypatch.setattr(privacy, "anonymize_payload", blocked)
    app = FastAPI()
    app.add_middleware(privacy.AnonymousResponses)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/private")
    async def data():
        payload = {"marker": "slow", "text": "联系电话13800130000"}
        if kind == "json":
            return payload

        async def parts():
            frame = ("data: " + json.dumps(payload) + ("\n\n" if kind == "sse" else "")).encode()
            for offset in range(0, len(frame), 7):
                yield frame[offset:offset + 7]
        return StreamingResponse(parts(), media_type="text/event-stream")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            pending = asyncio.create_task(client.get("/private"))
            try:
                async with asyncio.timeout(5):
                    while not entered.is_set():
                        await asyncio.sleep(.001)
                    health = await client.get("/health")
                assert health.json() == {"status": "ok"}
                assert not pending.done(), "Privacy I/O delayed the independent request"
                assert len(sanitizer_threads) == 1
                assert sanitizer_threads[0] != threading.get_ident()
            finally:
                release.set()
                response = await pending
            assert response.status_code == 200
            assert "13800130000" not in response.text

    asyncio.run(scenario())


@pytest.mark.parametrize("body", [b'{"text":', b'\xff'])
def test_invalid_json_fails_closed_after_offload(tmp_path, monkeypatch, body):
    monkeypatch.setenv("MRA_ANONYMIZE", "1")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "privacy.sqlite3"))

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json"), (b"etag", b"unsafe")]})
        await send({"type": "http.response.body", "body": body})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=privacy.AnonymousResponses(app)), base_url="http://test") as client:
            response = await client.get("/")
            assert response.status_code == 500
            assert response.json() == {"detail": "anonymous response serialization failed"}
            assert "etag" not in response.headers

    asyncio.run(scenario())
