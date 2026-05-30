"""A tiny localhost HTTP server that serves the wall and exits on demand.

Bound to 127.0.0.1 only (never exposed to the network). Two routes:
  GET /        -> the full-screen page
  GET /exit    -> acknowledge, then shut the whole controller down

The exit handler returns immediately and performs the shutdown on a separate
thread so the HTTP response can flush before the server socket closes.
"""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, self.server.html_bytes, "text/html; charset=utf-8")
        elif path == "/exit":
            self._send(200, b'{"ok":true}', "application/json")
            threading.Thread(target=self.server.trigger_exit, daemon=True).start()
        elif path == "/favicon.ico":
            self._send(204)
        else:
            self._send(404, b"not found")

    def log_message(self, *_args):  # keep the terminal clean
        return


class WallServer(ThreadingHTTPServer):
    daemon_threads = True            # never block exit on a stuck request
    allow_reuse_address = True

    def __init__(self, html: str, on_exit: Optional[Callable] = None):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.html_bytes = html.encode("utf-8")
        self._on_exit = on_exit
        self._exiting = False

    @property
    def url(self) -> str:
        host, port = self.server_address
        return f"http://127.0.0.1:{port}/"

    def trigger_exit(self):
        if self._exiting:
            return
        self._exiting = True
        time.sleep(0.3)              # let the /exit response flush
        if self._on_exit:
            try:
                self._on_exit()
            except Exception:
                pass
        self.shutdown()              # unblocks serve_forever() in the main thread
