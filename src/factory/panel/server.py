"""Servidor local del panel: página, instantánea y SSE. Solo lectura y solo loopback.

- Solo escucha en 127.0.0.1 y rechaza (403) una cabecera `Host` que no sea de loopback,
  para que una web ajena no lea el panel mediante *DNS rebinding*.
- Solo `GET` y `HEAD`; cualquier otro método recibe 405.
- `/api/stream` avisa con `event: change` cuando cambia la huella de alguna sección; el
  navegador vuelve a pedir `/api/snapshot`.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from factory.panel import PanelError, snapshot, state_dir
from factory.panel.hooks import LOG
from factory.panel.tasks import CHANGES_DIR, FEATURES_FILE
from factory.panel.tokens import TranscriptReader, transcript_files

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
LOOPBACK_HOST = re.compile(r"(127\.0\.0\.1|localhost|\[::1\])(:\d{1,5})?")
POLL_S = 1.0
PING_S = 15.0
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
    ),
}


def page() -> bytes:
    return (resources.files("factory.panel") / "static" / "index.html").read_bytes()


def host_allowed(header: str | None) -> bool:
    """`Host` de loopback, con o sin puerto (`127.0.0.1:8765`, `localhost`, `[::1]:8765`)."""
    return bool(header) and LOOPBACK_HOST.fullmatch(header.strip().lower()) is not None


class Watcher:
    """Huella `(ruta, mtime_ns, tamaño)` por sección; avisa a cada cliente de lo que cambia."""

    def __init__(self, root: Path, state_dir: Path, projects: Path) -> None:
        self.root = root
        self.state_dir = state_dir
        self.projects = projects
        self._clients: set[queue.Queue] = set()
        self._lock = threading.Lock()
        self._last = self.fingerprints()

    def _files(self) -> dict[str, list[Path]]:
        runs = self.state_dir / "runs"
        states = sorted(runs.glob("*/state.json"))
        return {
            "tasks": [
                self.root / FEATURES_FILE,
                *sorted((self.root / CHANGES_DIR).glob("*/tasks.md")),
                *states,
                *sorted((self.state_dir / "inbox").glob("*.md")),
            ],
            "reviews": [self.state_dir / LOG, *states],
            "tokens": [
                *sorted(runs.glob("*/events.jsonl")),
                *(t.path for t in transcript_files(self.projects, self.root)),
            ],
        }

    def fingerprints(self) -> dict[str, tuple]:
        prints = {}
        for section, paths in self._files().items():
            entries = []
            for path in paths:
                try:
                    stat = path.stat()
                except OSError:
                    continue
                entries.append((str(path), stat.st_mtime_ns, stat.st_size))
            prints[section] = tuple(entries)
        return prints

    def check(self) -> list[str]:
        """Secciones cuya huella cambió desde la última comprobación."""
        current = self.fingerprints()
        changed = [s for s in snapshot.SECTIONS if current.get(s) != self._last.get(s)]
        self._last = current
        return changed

    def subscribe(self) -> queue.Queue:
        client: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._clients.add(client)
        return client

    def unsubscribe(self, client: queue.Queue) -> None:
        with self._lock:
            self._clients.discard(client)

    def broadcast(self, sections: list[str]) -> None:
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.put_nowait({"sections": sections})
            except queue.Full:  # un cliente que no lee no frena a los demás
                pass

    def run(self, stop: threading.Event, interval: float) -> None:
        while not stop.wait(interval):
            try:
                changed = self.check()
            except Exception:  # un error al sondear no debe parar el vigilante
                continue
            if changed:
                self.broadcast(changed)


class PanelServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, root: Path, projects: Path, port: int = DEFAULT_PORT, interval: float = POLL_S
    ) -> None:
        self.root = root
        self.projects = projects
        self.reader = TranscriptReader()
        self.build_lock = threading.Lock()
        self.stopping = threading.Event()
        self.state_dir = state_dir(root)
        self.watcher = Watcher(root, self.state_dir, projects)
        self._watch = threading.Thread(
            target=self.watcher.run, args=(self.stopping, interval), daemon=True
        )
        try:
            super().__init__((HOST, port), PanelHandler)
        except (OSError, OverflowError) as exc:  # OverflowError: puerto fuera de 0-65535
            raise PanelError(f"No se pudo escuchar en {HOST}:{port}: {exc}") from exc
        self._watch.start()

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.server_address[1]}/"

    def snapshot(self) -> dict[str, Any]:
        with self.build_lock:  # el lector incremental no es seguro entre hilos
            return snapshot.build(self.root, self.projects, self.reader)

    def server_close(self) -> None:
        self.stopping.set()
        super().server_close()


class PanelHandler(BaseHTTPRequestHandler):
    server: PanelServer
    server_version = "factory-panel"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        pass  # el panel no ensucia la terminal con una línea por petición

    def _send(self, status: int, body: bytes, content_type: str, head: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _text(self, status: HTTPStatus, head: bool = False) -> None:
        self._send(status, f"{status.value} {status.phrase}\n".encode(), "text/plain", head)

    def _route(self, head: bool) -> None:
        if not host_allowed(self.headers.get("Host")):
            self._text(HTTPStatus.FORBIDDEN, head)
            return
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._send(HTTPStatus.OK, page(), "text/html; charset=utf-8", head)
        elif path == "/api/snapshot":
            body = snapshot.to_json(self.server.snapshot()).encode("utf-8")
            self._send(HTTPStatus.OK, body, "application/json; charset=utf-8", head)
        elif path == "/api/stream":
            if head:
                self._send(HTTPStatus.OK, b"", "text/event-stream; charset=utf-8", head)
            else:
                self._stream()
        else:
            self._text(HTTPStatus.NOT_FOUND, head)

    def do_GET(self) -> None:
        self._route(head=False)

    def do_HEAD(self) -> None:
        self._route(head=True)

    def _not_allowed(self) -> None:
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()

    def __getattr__(self, name: str) -> Any:
        # Cualquier método distinto de GET y HEAD (también TRACE o uno inventado) recibe 405,
        # nunca el 501 sin cabeceras de seguridad de BaseHTTPRequestHandler.
        if name.startswith("do_"):
            return self._not_allowed
        raise AttributeError(name)

    def _event(self, name: str, data: dict[str, Any]) -> None:
        self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
        self.wfile.flush()

    def _stream(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        client = self.server.watcher.subscribe()
        last_ping = time.monotonic()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self._event("hello", {"sections": list(snapshot.SECTIONS)})
            while not self.server.stopping.is_set():
                try:
                    message = client.get(timeout=0.5)
                except queue.Empty:
                    if time.monotonic() - last_ping >= PING_S:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        last_ping = time.monotonic()
                    continue
                self._event("change", message)
        except (BrokenPipeError, ConnectionResetError):
            pass  # el navegador cerró la pestaña
        finally:
            self.server.watcher.unsubscribe(client)
            self.close_connection = True


def serve(root: Path, projects: Path, port: int = DEFAULT_PORT, open_browser: bool = False) -> int:
    """Sirve el panel hasta Ctrl+C."""
    server = PanelServer(root, projects, port)
    print(f"Panel de factory en {server.url} (Ctrl+C para salir)", flush=True)
    if open_browser:
        import webbrowser

        webbrowser.open(server.url)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nPanel detenido.")
    finally:
        server.server_close()
    return 0
