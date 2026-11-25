"""Serve only this synthetic prototype on loopback, with consistent module MIME."""
import argparse
import functools
import http.server
from pathlib import Path
import webbrowser

VERSION = "0.1.0"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".mjs": "text/javascript", ".js": "text/javascript",
                      ".css": "text/css"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description="MediListen synthetic frontend prototype")
    parser.add_argument("--port", type=int, default=23709)
    parser.add_argument("--open", action="store_true", help="Open the local preview")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()
    directory = str(Path(__file__).resolve().parent)
    handler = functools.partial(Handler, directory=directory)
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as error:
        parser.exit(1, f"Cannot start preview on port {args.port}: {error}\n")
    url = f"http://127.0.0.1:{args.port}/"
    print(f"MediListen prototype {VERSION}: {url}\nCtrl+C to stop.", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
