"""Minimal loopback-published TCP bridge for an internal-only offline app.

The gateway has no model or runtime volume and does not process clinical data.
Only the application and Ollama share the internal Docker network.
"""

import select
import socket
import socketserver


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        with socket.create_connection(("app", 8000), timeout=10) as upstream:
            self.request.settimeout(None)
            upstream.settimeout(None)
            peers = (self.request, upstream)
            while True:
                readable, _, _ = select.select(peers, [], [], 30)
                for source in readable:
                    chunk = source.recv(1024 * 1024)
                    if not chunk:
                        return
                    peers[1 if source is peers[0] else 0].sendall(chunk)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("0.0.0.0", 8000), Handler) as server:
        server.serve_forever()
