"""Loopback-published HTTP bridge to the internal-only offline application.

The bridge has no model or runtime volume. Streaming preserves task events and
audio uploads without buffering clinical request bodies in this process.
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask


app = FastAPI()
client = httpx.AsyncClient(base_url="http://app:8000", timeout=httpx.Timeout(10, read=None))
REQUEST_HOP_HEADERS = {"connection", "host", "content-length", "transfer-encoding"}
RESPONSE_HOP_HEADERS = REQUEST_HOP_HEADERS | {"content-encoding"}


@app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def forward(path: str, request: Request):
    url = "/" + path
    if request.url.query:
        url += "?" + request.url.query
    headers = {key: value for key, value in request.headers.items() if key.lower() not in REQUEST_HOP_HEADERS}
    try:
        upstream_request = client.build_request(
            request.method, url, headers=headers, content=request.stream()
        )
        response = await client.send(upstream_request, stream=True)
    except httpx.RequestError:
        return JSONResponse({"detail": "Application is starting or unavailable"}, status_code=503)
    response_headers = {
        key: value for key, value in response.headers.items() if key.lower() not in RESPONSE_HOP_HEADERS
    }
    return StreamingResponse(
        response.aiter_bytes(),
        status_code=response.status_code,
        headers=response_headers,
        background=BackgroundTask(response.aclose),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
