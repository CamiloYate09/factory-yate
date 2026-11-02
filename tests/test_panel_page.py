"""Página del panel: comprobaciones estáticas de `static/index.html` (improve-panel-ux, D11).

El repo no ejecuta JS en sus tests: el comportamiento se comprueba además en el navegador y se
registra en `progress.md`.
"""

from __future__ import annotations

import re

import pytest

from factory.cli import REWORKABLE
from factory.panel.server import page


@pytest.fixture(scope="module")
def html() -> str:
    return page().decode("utf-8")


def test_la_pagina_empaquetada_se_lee(html: str):
    assert html.startswith("<!doctype html>")


# --- panel-ux-fixes ----------------------------------------------------------------------


def test_no_dibuja_vistas_sin_instantanea(html: str):
    assert 'placeholder("Cargando…")' in html
    assert "state.snap || {}" not in html
    assert 'if (tab === "tokens" && state.snap) withOpen' in html
    assert "if (!state.snap) placeholder(" in html


def test_dia_utc_explicito_y_continuo(html: str):
    assert "`${today} UTC`" in html
    assert "stackedColumns(el, continuousDays(days), series)" in html
    assert 'unit.textContent = "UTC"' in html


def test_sin_veredicto_no_se_presenta_como_limpia(html: str):
    assert 'r.status === "sin_veredicto" ? "—" : severityText(r.severities)' in html


def test_navegacion_con_el_historial(html: str):
    assert 'addEventListener("hashchange", applyHash)' in html
    assert "history.replaceState" in html
    # Los clics solo cambian el hash: `applyHash` es el único camino que selecciona la pestaña.
    assert html.count("selectTab(") == 2


@pytest.mark.parametrize("tab", ["tokens", "revisiones", "tareas"])
def test_pestanas_accesibles(html: str, tab: str):
    assert f'id="tab-{tab}" aria-controls="view-{tab}"' in html
    assert f'id="view-{tab}" role="tabpanel" aria-labelledby="tab-{tab}"' in html


def test_flechas_del_teclado(html: str):
    assert "ArrowRight" in html and "ArrowLeft" in html
    assert "Home" in html and "End" in html
    assert "button.tabIndex = selected ? 0 : -1" in html


def test_detalle_visible_y_foco_de_vuelta(html: str):
    assert "scrollIntoView" in html
    assert 'id: "detail-title", tabindex: "-1"' in html
    assert "state.focusCard = previous" in html
    assert "scroll-padding-top" in html


# --- panel-ux-actions --------------------------------------------------------------------


def test_tema_de_tres_posiciones(html: str):
    assert 'const THEMES = { system: "Sistema", light: "Claro", dark: "Oscuro" }' in html
    assert "delete document.documentElement.dataset.theme" in html
    # Un valor guardado desconocido equivale a `system`.
    assert 'Object.hasOwn(THEMES, savedTheme ?? "") ? savedTheme : "system"' in html


def test_los_chips_del_feed_son_filtros(html: str):
    assert 'h("button", { class: "chip", type: "button"' in html
    assert '"aria-pressed": String(state.statuses.has(status))' in html
    assert 'const UNFINISHED = ["sin_cierre", "sin_veredicto"]' in html
    assert '"panel-hide-unfinished"' in html
    assert "ordered.map(([k, v]) => statusFilter(k, v))" in html
    assert "button.chip:focus-visible" in html


def test_indicadores_enlazables(html: str):
    assert 'h(link ? "a" : "div"' in html
    assert '{ href: "#tareas", onclick: showRuns }' in html
    assert '{ href: "#revisiones", onclick: showRunning }' in html
    assert "{ href: `#${featureHash(active[0])}` }" in html


def test_frescura_y_refresco_manual(html: str):
    assert "`Actualizado hace ${" in html
    assert 'getElementById("refresh").addEventListener("click", () => refresh())' in html


def test_comandos_copiables(html: str):
    assert 'const CLI = ".venv/bin/factory"' in html
    assert "`${CLI} features verify ${id}`" in html
    assert "`${CLI} land ${run.run_id} --dry-run`" in html
    # El comando termina sin respuesta: ejecutarlo sin completar falla sin lanzar un loop.
    assert "`${CLI} goal rework ${run.run_id} --answer `" in html
    assert "const SAFE_ID = /^[A-Za-z0-9._-]+$/" in html
    assert "navigator.clipboard.writeText(command)" in html


def test_reworkable_igual_que_en_la_cli(html: str):
    found = re.search(r"const REWORKABLE = \[(.*?)\];", html)
    assert found
    assert tuple(re.findall(r'"(\w+)"', found.group(1))) == REWORKABLE


def test_la_pagina_sigue_sin_escribir(html: str):
    assert "execCommand" not in html
    assert not re.search(r"\bmethod\s*:", html)
    assert not re.search(r"\b(POST|PUT|PATCH|DELETE)\b", html)
    assert "sendBeacon" not in html


# --- panel-ux-views ----------------------------------------------------------------------


def test_lectura_de_cache_excluida_por_defecto(html: str):
    assert 'cacheRead: safeStorage("get", "panel-cache-read") === "1"' in html
    assert 'state.cacheRead ? STACK : STACK.filter((k) => k.key !== "cache_read")' in html
    assert "`Lectura de caché oculta: ${" in html
    # «Ver tabla» sigue con las cuatro columnas.
    assert "...STACK.map((k) => ({ label: k.label, num: true" in html


def test_terminadas_plegadas_con_buscador(html: str):
    assert '"data-key": "board:passing"' in html
    assert "open: Boolean(query)" in html
    assert 'type: "search"' in html
    assert "e.isComposing" in html
    # Abrirla por una búsqueda no cambia la preferencia del usuario.
    assert "el.dataset.forced) return" in html


def test_codigo_en_linea_sin_html(html: str):
    assert 'h("code", { text: match[1] })' in html
    assert "richText(g.title)" in html and "richText(t.text)" in html


@pytest.mark.parametrize(
    ("raw", "label"),
    [("pass", "aprobado"), ("pass_with_minor", "aprobado con menores"), ("fail", "fallido")],
)
def test_estados_en_espanol(html: str, raw: str, label: str):
    assert re.search(rf'\b{raw}: \{{ tone: "\w+", icon: "[^"]+", label: "{label}" \}}', html)
    assert "title: status" in html


def test_etiquetas_recortadas_con_texto_completo(html: str):
    assert 's("title")' in html
    assert "full: (r) => r.run_id" in html


def test_columna_proyecto_solo_si_informa(html: str):
    assert "new Set(top.map((row) => row.project)).size > 1" in html
