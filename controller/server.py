"""A tiny localhost HTTP server that serves the wall, streams per-language
results as they complete, and exits on demand.

Bound to 127.0.0.1 only (never exposed to the network). Three routes:
  GET /        -> the full-screen page (placeholders for every tile)
  GET /events  -> Server-Sent Events stream of language results
  GET /exit    -> acknowledge, then shut the whole controller down

The exit handler returns immediately and performs the shutdown on a separate
thread so the HTTP response can flush before the server socket closes.
"""

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, List, Optional, Tuple


# ----------------------------------------------------------------------------
# SSE broker: a tiny pub/sub with replay
# ----------------------------------------------------------------------------

class SSEBroker:
    """A simple publish/subscribe broker for Server-Sent Events.

    `publish(event_type, payload)` records the event and fans it out to every
    current subscriber. A late subscriber gets every event that was already
    published, then continues receiving live ones — important because the
    page may finish loading after the first few results have streamed.
    `signal_done()` closes every subscriber's stream cleanly.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._subs: List[queue.Queue] = []
        self._log: List[Tuple[str, dict]] = []
        self._done = False

    def publish(self, event_type: str, payload: dict) -> None:
        with self._lock:
            evt = (event_type, payload)
            self._log.append(evt)
            for q in self._subs:
                q.put(evt)

    def signal_done(self) -> None:
        with self._lock:
            self._done = True
            for q in self._subs:
                q.put(None)

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            for evt in self._log:
                q.put(evt)
            if self._done:
                q.put(None)
            else:
                self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)


# ----------------------------------------------------------------------------
# HTTP handler + server
# ----------------------------------------------------------------------------

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
        elif path == "/events":
            self._stream_events()
        elif path == "/exit":
            self._send(200, b'{"ok":true}', "application/json")
            threading.Thread(target=self.server.trigger_exit, daemon=True).start()
        elif path == "/favicon.ico":
            self._send(204)
        else:
            self._send(404, b"not found")

    def _stream_events(self):
        """Hold the connection open and write SSE events as they arrive."""
        broker: Optional[SSEBroker] = getattr(self.server, "broker", None)
        if broker is None:
            self._send(503, b"no broker")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")  # disable any proxy buffering
        self.end_headers()
        q = broker.subscribe()
        try:
            # initial comment-line ping so the client knows we're alive
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                item = q.get()
                if item is None:
                    self.wfile.write(b"event: done\ndata: {}\n\n")
                    self.wfile.flush()
                    return
                event_type, payload = item
                line = (f"event: {event_type}\n"
                        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        ).encode("utf-8")
                self.wfile.write(line)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            broker.unsubscribe(q)

    def log_message(self, *_args):  # keep the terminal clean
        return


class WallServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, html: str, broker: Optional[SSEBroker] = None,
                 on_exit: Optional[Callable] = None):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.html_bytes = html.encode("utf-8")
        self.broker = broker
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
