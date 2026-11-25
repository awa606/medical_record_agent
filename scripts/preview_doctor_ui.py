"""Local, read-only UI preview: explicit static overlay, GET-only upstream.

No database/session copies or model processes. Mutations fail closed with 405.
Run only against an already authorized local MediListen instance.
"""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATIC = {f"/static/{name}" for name in (
    "doctor.html", "doctor.js", "doctor.css", "doctor-ui-v2.css",
    "doctor-workspace.css", "deployment.json",
)}


def serve(port=26321, upstream="http://127.0.0.1:26320"):
    if urlsplit(upstream).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Preview upstream must be loopback")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log cookies, query strings or clinical content.

        def respond(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in STATIC:
                file = ROOT / path.lstrip("/")
                if path.endswith("deployment.json"):
                    data = json.loads(file.read_text(encoding="utf-8"))
                    data["label"] = "界面只读候选"
                    body = json.dumps(data, ensure_ascii=False).encode()
                else:
                    body = file.read_bytes()
                self.respond(200, body, (mimetypes.guess_type(path)[0] or "application/octet-stream") + "; charset=utf-8")
                return
            if not path.startswith(("/api/", "/static/")) and path not in {"/health", "/ready"}:
                self.respond(404, b"Not found", "text/plain")
                return
            request = Request(upstream + self.path, headers={"Cookie": self.headers.get("Cookie", "")})
            try:
                with urlopen(request, timeout=15) as response:
                    self.respond(response.status, response.read(), response.headers.get("Content-Type", "application/json"))
            except HTTPError as error:
                self.respond(error.code, error.read(), error.headers.get("Content-Type", "application/json"))
            except Exception:
                self.respond(502, b'{"detail":"preview_upstream_unavailable"}', "application/json")

        def reject_write(self):
            self.respond(405, json.dumps({"detail": "这是只读界面候选；保存、审核、生成及导出写操作未启用。"}, ensure_ascii=False).encode(), "application/json")

        do_POST = do_PUT = do_PATCH = do_DELETE = reject_write

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=26321)
    parser.add_argument("--upstream", default="http://127.0.0.1:26320")
    args = parser.parse_args()
    serve(args.port, args.upstream)
