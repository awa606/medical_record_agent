"""Loopback-published HTTP bridge to the internal-only offline application.

The bridge has no model or runtime volume. Streaming preserves task events and
audio uploads without buffering clinical request bodies in this process.
"""

from __future__ import annotations

import os
import socket
import struct

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask


app = FastAPI()
client = httpx.AsyncClient(base_url="http://app:8000", timeout=httpx.Timeout(10, read=None))
REQUEST_HOP_HEADERS = {"connection", "host", "content-length", "transfer-encoding"}
RESPONSE_HOP_HEADERS = REQUEST_HOP_HEADERS | {"content-encoding"}


def restrict_gateway_egress() -> None:
    """Drop the Docker frontend default route before accepting requests.

    The gateway keeps its directly connected frontend and internal subnets, so
    the host can reach the published loopback port and the app remains
    reachable. A missing NET_ADMIN capability or an IPv6 default route stops
    startup instead of silently exposing an online gateway.
    """
    request = struct.pack("IHHII", 28, 25, 5, 1, 0) + struct.pack(
        "BBBBBBBBI", socket.AF_INET, 0, 0, 0, 254, 0, 0, 0, 0
    )
    with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, socket.NETLINK_ROUTE) as route:
        route.bind((0, 0))
        route.send(request)
        response = route.recv(65535)
    if len(response) < 20:
        raise RuntimeError("gateway route deletion returned an incomplete response")
    _length, kind, _flags, _seq, _pid = struct.unpack_from("IHHII", response)
    error = struct.unpack_from("i", response, 16)[0]
    if kind != 2 or error != 0:
        raise RuntimeError(f"gateway default route deletion failed: type={kind}, errno={error}")

    with open("/proc/net/route", encoding="ascii") as routes:
        if any(parts[1] == "00000000" and parts[7] == "00000000"
               for line in list(routes)[1:] if len(parts := line.split()) > 7):
            raise RuntimeError("gateway still has an IPv4 default route")
    with open("/proc/net/ipv6_route", encoding="ascii") as routes:
        if any(parts[0] == "0" * 32 and parts[1] == "00" and parts[-1] != "lo"
               for line in routes if len(parts := line.split()) >= 10):
            raise RuntimeError("gateway still has an IPv6 default route")

    os.setgroups([])
    os.setgid(999)
    os.setuid(999)


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

    restrict_gateway_egress()
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
