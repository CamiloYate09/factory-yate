"""Servidor del panel: rutas, cabecera `Host`, métodos, solo lectura, SSE y página."""

from __future__ import annotations

import http.client
import json
import re
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import make_feature, write_features

from factory.cli import main
from factory.panel import PanelError
from factory.panel.hooks import LOG
from factory.panel.server import PanelServer, host_allowed, page
from factory.panel.tokens import slug
from factory.state import RunState, RunStore


@pytest.fixture
def panel(tmp_path: Path) -> Iterator[PanelServer]:
    root = tmp_path / "repo"
    root.mkdir()
    write_features(root, make_feature("a"))
    server = PanelServer(root, tmp_path / "projects", port=0, interval=0.05)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(
    server: PanelServer, method: str, path: str, host: str | None = None
) -> tuple[int, dict[str, str], bytes]:
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", host if host is not None else f"127.0.0.1:{port}")
    conn.endheaders()
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, {k.lower(): v for k, v in response.getheaders()}, body


def test_pagina_principal(panel: PanelServer):
    status, headers, body = request(panel, "GET", "/")
    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert b"<html" in body.lower()
    assert headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "access-control-allow-origin" not in headers


def test_instantanea(panel: PanelServer):
    status, headers, body = request(panel, "GET", "/api/snapshot?x=1")
    assert status == 200 and headers["content-type"].startswith("application/json")
    snap = json.loads(body)
    assert snap["tasks"]["features"][0]["id"] == "a"
    assert headers["cache-control"] == "no-store"


@pytest.mark.parametrize("host", ["localhost:8765", "[::1]:8765", "LOCALHOST", "127.0.0.1"])
def test_hosts_de_loopback(panel: PanelServer, host: str):
    assert request(panel, "GET", "/api/snapshot", host)[0] == 200


@pytest.mark.parametrize(
    "host", ["atacante.example", "atacante.example:8765", "127.0.0.1.nip.io", "", "0.0.0.0"]
)
def test_host_ajeno(panel: PanelServer, host: str):
    status, _, body = request(panel, "GET", "/api/snapshot", host)
    assert status == 403
    assert b"features" not in body


def test_host_allowed():
    assert host_allowed("127.0.0.1:1") and host_allowed("[::1]")
    assert host_allowed(" 127.0.0.1 ")  # los espacios exteriores se ignoran
    for bad in (None, "[::1].evil", "::1x", "localhost.evil", "127.0.0.1:80:80", "127.0.0.1:"):
        assert not host_allowed(bad)


@pytest.mark.parametrize(
    "method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "INVENTADO"]
)
def test_escritura(panel: PanelServer, method: str):
    status, headers, _ = request(panel, method, "/api/snapshot")
    assert status == 405
    assert headers["allow"] == "GET, HEAD"
    assert headers["x-content-type-options"] == "nosniff"


def test_head_y_404(panel: PanelServer):
    status, headers, body = request(panel, "HEAD", "/api/snapshot")
    assert status == 200 and body == b"" and int(headers["content-length"]) > 0
    assert request(panel, "GET", "/../feature_list.json")[0] == 404
    assert request(panel, "GET", "/static/index.html")[0] == 404
    status, headers, body = request(panel, "HEAD", "/api/stream")
    assert status == 200 and body == b"" and headers["content-type"].startswith("text/event-stream")


def test_instantanea_sin_efectos(panel: PanelServer):
    root = panel.root
    state = root / ".factory"
    (state / "hooks").mkdir(parents=True)
    (state / LOG).write_text('{"event": "PreToolUse", "review": true}\n', encoding="utf-8")
    run = RunState(run_id="20261029-100000-demo-aaaa", goal_id="demo", objective="x")
    RunStore(state).save(run)
    agent = {"type": "agent", "role": "maker", "model": "m", "cost_usd": 0.1, "num_turns": 2}
    agent["usage"] = {"input_tokens": 5, "output_tokens": 7}
    (state / "runs" / run.run_id / "events.jsonl").write_text(json.dumps(agent) + "\n")
    usage = {"input_tokens": 2, "cache_read_input_tokens": 9, "output_tokens": 4}
    row = {"type": "assistant", "timestamp": "2026-10-29T11:00:00Z", "sessionId": "s1"}
    row["message"] = {"id": "m1", "model": "claude-opus-5-5", "usage": usage, "content": []}
    transcript = panel.projects / slug(root) / "s1.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(json.dumps(row) + "\n", encoding="utf-8")
    files = [p for p in panel.root.parent.rglob("*") if p.is_file()]
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files}
    for _ in range(3):  # la segunda y la tercera pasan por la caché incremental
        status, _, body = request(panel, "GET", "/api/snapshot")
        assert status == 200
        snap = json.loads(body)
        assert snap["tokens"]["sessions"]["sessions"] and snap["tokens"]["loops"]["runs"]
        assert snap["reviews"] and snap["tasks"]["runs"]
    after = {
        p: (p.stat().st_mtime_ns, p.read_bytes())
        for p in panel.root.parent.rglob("*")
        if p.is_file()
    }
    assert before == after


# --- Tiempo real -------------------------------------------------------------------------


class Stream:
    def __init__(self, server: PanelServer) -> None:
        port = server.server_address[1]
        self.conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        self.conn.request("GET", "/api/stream", headers={"Host": f"127.0.0.1:{port}"})
        self.response = self.conn.getresponse()
        assert self.response.status == 200
        assert self.response.getheader("Content-Type").startswith("text/event-stream")

    def next_event(self) -> tuple[str, dict]:
        """Siguiente evento con datos; falla por timeout del socket si no llega (5 s)."""
        name = ""
        while True:
            line = self.response.fp.readline().decode().rstrip("\n")
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: ") and name:
                return name, json.loads(line.removeprefix("data: "))

    def close(self) -> None:
        self.conn.close()


def test_revision_que_termina(panel: PanelServer):
    stream = Stream(panel)
    try:
        assert stream.next_event()[0] == "hello"
        log = panel.root / ".factory" / LOG
        log.parent.mkdir(parents=True)
        log.write_text('{"event": "SubagentStop", "review": true}\n', encoding="utf-8")
        name, data = stream.next_event()
        assert name == "change"
        assert "reviews" in data["sections"]
    finally:
        stream.close()


def test_feature_promovida(panel: PanelServer):
    stream = Stream(panel)
    try:
        stream.next_event()
        write_features(panel.root, make_feature("a", "in_progress"), make_feature("b"))
        name, data = stream.next_event()
        assert name == "change" and data["sections"] == ["tasks"]
    finally:
        stream.close()


def test_cliente_que_se_va_no_rompe_el_vigilante(panel: PanelServer):
    first = Stream(panel)
    first.next_event()
    first.close()
    second = Stream(panel)
    try:
        second.next_event()
        # Otro tamaño, para que la huella cambie aunque el mtime tenga resolución de 1 s.
        write_features(panel.root, make_feature("c"), make_feature("d"))
        assert second.next_event()[0] == "change"
    finally:
        second.close()


# --- Página ------------------------------------------------------------------------------


def test_sin_recursos_externos():
    html = page().decode("utf-8")
    # El espacio de nombres SVG es un identificador de `createElementNS`, no un recurso.
    assert html.count("http://www.w3.org/2000/svg") == 1
    assert not re.search(r"https?://", html.replace("http://www.w3.org/2000/svg", ""))
    assert "@import" not in html and "url(" not in html


def test_la_pagina_no_usa_innerhtml():
    html = page().decode("utf-8")
    assert "innerHTML" not in html and "outerHTML" not in html
    assert "insertAdjacentHTML" not in html and "document.write" not in html
    assert "/api/snapshot" in html and "/api/stream" in html


@pytest.mark.parametrize("port", ["70000", "-1"])
def test_puerto_fuera_de_rango(port: str, capsys):
    with pytest.raises(SystemExit) as salida:
        main(["panel", "--port", port])
    assert salida.value.code == 2
    assert "fuera de rango" in capsys.readouterr().err


def test_puerto_fuera_de_rango_en_el_servidor(tmp_path: Path):
    with pytest.raises(PanelError):
        PanelServer(tmp_path, tmp_path / "projects", port=70000)


def test_puerto_ocupado(panel: PanelServer, tmp_path: Path, capsys):
    port = panel.server_address[1]
    assert main(["--root", str(panel.root), "panel", "--port", str(port)]) == 2
    assert "No se pudo escuchar" in capsys.readouterr().err


def test_umbral_sin_cierre_igual_en_la_pagina():
    from factory.panel.reviews import UNCLOSED_AFTER_S

    found = re.search(r"const UNCLOSED_AFTER_S = (\d+) \* (\d+);", page().decode("utf-8"))
    assert found and int(found.group(1)) * int(found.group(2)) == UNCLOSED_AFTER_S
