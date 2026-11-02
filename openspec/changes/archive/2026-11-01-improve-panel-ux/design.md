# Design

## Context

Motivación: ver `proposal.md`. Requisitos: ver `specs/observability-panel`.

**Estado actual (observado el 2026-11-01 en este repo):**
- Toda la interfaz está en `src/factory/panel/static/index.html`: unas 790 líneas de HTML, CSS y JS en línea, sin dependencias.
  - Los nodos se crean con `h()` y `s()`, y los datos entran siempre con `textContent`.
  - `tests/test_panel_server.py` comprueba que no hay `innerHTML` ni recursos externos.
- La CSP del servidor admite scripts y estilos en línea del propio origen (`'unsafe-inline'`), así que no hace falta tocar `server.py`.
- Hallazgos de las capturas con Chrome headless y de la lectura del código:
  - `selectTab` dibuja Tokens con `state.snap || {}` antes de la primera instantánea (línea 681). De ahí sale el mensaje «No hay transcripciones…».
  - `renderKpis` toma el día de hoy con `toISOString()`, que es UTC.
  - `reviewItem` muestra `severityText()` también para `sin_veredicto` (línea 537).
  - No hay ningún listener de `hashchange` ni ninguna llamada a `scrollIntoView`.
  - `state.fetchedAt` se guarda pero nunca se muestra.
  - Los chips de los filtros son `<span>`.
- Datos reales en ese momento: 29 features (28 `passing`), 19 revisiones (10 `sin_cierre` o `sin_veredicto`) y un 97,8 % de lectura de caché.
- Estados finales de una ejecución (`state.py`): `completed`, `stalled`, `max_rounds`, `budget_exhausted`, `blocked`, `agent_error` e `interrupted`. `factory goal rework` no admite `completed`, que se integra con `factory land` (`docs/harness/revision.md`).

## Goals / Non-Goals

**Goals:**
- Un cambio contenido en `index.html`: ni el servidor ni la instantánea cambian de forma.
- Mantener las garantías de seguridad de la página: `textContent`, sin recursos externos y sin peticiones distintas de `GET`.
- Que cada control que parezca accionable lo sea, y que sea accesible con teclado.

**Non-Goals:**
- Pasar la página a un framework o partirla en varios archivos.
- Guardar en el servidor las preferencias (tema, filtros): solo `localStorage`, como ya se hace con la pestaña.
- Cambiar la agregación por día de `token-usage`.

## Decisions

### D1. Solo cliente, en el mismo `index.html`

Todo se resuelve en la página con los datos que ya trae `/api/snapshot`.

**Alternativa descartada:** servir un `panel.js` aparte para poder testearlo. Habría que cambiar `server.py` y el empaquetado, solo para tener tests de JS. Ver D11.

### D2. El `#hash` es la fuente de verdad de la navegación

- Los clics en pestañas, tarjetas, indicadores y «Cerrar» solo asignan `location.hash`.
- Un único listener de `hashchange` (y la carga inicial) interpreta `#<pestaña>[/<id>]` y llama a `selectTab` y al render.
- Atrás y Adelante funcionan sin código extra, y no hay dos caminos que actualicen el estado.

Los filtros del feed no van en el hash, para no llenar el historial de entradas. El indicador «Revisiones en curso» fija el filtro `en_curso` en el estado y después cambia el hash.

**Alternativa descartada:** `history.pushState` con estado propio. Es más código, y el formato `#tareas/<id>` ya está documentado en `panel.md`.

### D3. Estado de carga sin tocar los renders

`render()` y `selectTab()` no llaman a las vistas mientras `state.snap` sea `null`. En su lugar, cada vista muestra un `<p class="empty">Cargando…</p>`. El error de la primera carga reutiliza el aviso `warn-conn` y sustituye el «Cargando…».

### D4. Fechas: rotular UTC y rellenar los huecos en el cliente

- Los indicadores y el eje dicen «UTC» de forma explícita.
- Los días vacíos se generan en la página, entre el mínimo y el máximo de `by_day`, que vienen en formato `YYYY-MM-DD`. Cada día faltante entra con ceros.

**Alternativa descartada:** agregar por día local en `tokens.py`. Cambiaría el requisito de `token-usage`, que aún no está archivado, y las cifras ya documentadas en `panel.md`. Si se pide más adelante, irá en un cambio aparte.

### D5. Controles reales y accesibles

- **Pestañas:** `aria-controls`, `aria-labelledby` y *roving tabindex*. Las flechas, Inicio y Fin cambian de pestaña.
- **Chips del feed:** pasan a ser `<button aria-pressed>`. Varios activos se combinan con «o». Ninguno activo equivale a «todos».
- **Interruptor «Ocultar sin cierre / sin veredicto»:** `<input type="checkbox">`, recordado en `localStorage`.
- **Indicadores con destino:** `<a href="#…">`, con estilo de tarjeta y foco visible. Los que no tienen destino siguen siendo `<div>`.
- **Tema:** un solo botón que cicla Sistema → Claro → Oscuro.
  - La etiqueta dice «Tema: <posición>».
  - En Sistema se borra `data-theme`, de modo que vuelve a mandar `prefers-color-scheme`.
  - Se guarda en `panel-theme`, con el valor `system`, `light` o `dark`.

### D6. Detalle visible

Después de dibujar el detalle se llama a `scrollIntoView({block: "start"})` y se da el foco al título del detalle (`tabindex="-1"`). Con `prefers-reduced-motion`, sin animación.

Al cerrar, se busca la tarjeta por `data-id` y se le da el foco. Hace falta, porque el tablero se vuelve a dibujar.

### D7. Comandos copiables

- Se escribe con `navigator.clipboard.writeText`. El panel solo se sirve en loopback, que es un contexto seguro.
- Si el portapapeles no está disponible o falla, el botón muestra el comando seleccionado en un `<code>`, para copiarlo a mano. No se usa `document.execCommand`.
- El texto del botón confirma la copia durante unos 2 s («Copiado»).
- Los comandos llevan el prefijo `.venv/bin/factory`, como en `AGENTS.md`.
- Qué se ofrece en cada caso:

  | Dónde | Comando |
  |---|---|
  | Detalle de feature | `features verify <id>` |
  | Ejecución con estado en `REWORKABLE` (`cli.py`) | `goal rework <run> --answer ` |
  | Ejecución `completed` | `land <run> --dry-run` |
  | Ejecución `running` | nada |

- Antes de construir un comando, el id debe casar con `^[A-Za-z0-9._-]+$`. Si no casa, no hay botón.

**Por qué `rework` termina en `--answer `:** el comando exige una respuesta humana. Sin `--answer` fallaría siempre, y con un texto de ejemplo, pegarlo lanzaría un loop de pago con una respuesta falsa. Así, ejecutarlo sin completar falla sin hacer nada (`argparse`: falta el argumento). La lista `REWORKABLE` se copia en la página, y un test comprueba que coincide con `cli.py`.

**Por qué `land --dry-run` y no `land`:** integrar es una decisión humana (`AGENTS.md`). El panel sugiere el paso que comprueba sin cambiar nada.

**Alternativa descartada:** endpoints `POST` para ejecutar. Romperían el requisito «Panel de solo lectura» y el 405 del servidor.

### D8. Gráfico de tokens

- La serie de lectura de caché se filtra de `STACK` cuando el interruptor está desactivado, que es su valor por defecto.
- La nota junto a la leyenda dice cuánto suma lo oculto («Lectura de caché oculta: 537 M»).
- La tabla «Ver tabla» sigue mostrando las cuatro columnas.
- El valor del interruptor se guarda en `panel-cache-read`.

### D9. Tablero

- «Terminadas (passing)» va dentro de un `<details>` cerrado por defecto. Su clave estable usa el mecanismo `state.open` que ya existe, para que el refresco no lo cierre.
- El buscador es un `<input type="search">` encima del tablero:
  - filtra por subcadena, sin distinguir mayúsculas, sobre el id y el título;
  - mientras tenga texto, abre «Terminadas»;
  - su valor vive en el estado y sobrevive a los refrescos.

### D10. Texto legible

- **`richText(text)`:** parte el texto por comillas invertidas emparejadas y devuelve nodos de texto y `<code>`, todos creados con `textContent`. Una comilla sin pareja queda como texto literal.
- **Estados:** la etiqueta en español va en `STATUS[...].label`, y el valor original en el `title` del chip.
- **Etiquetas recortadas del SVG:** llevan un `<title>` hijo con el texto completo, además del tooltip que ya existe.
- **Columna «Proyecto»:** se omite si `new Set(rows.map(r => r.project)).size <= 1`.

### D11. Verificación

El repo no ejecuta JS en sus tests, y `scripts/check.sh` no se puede cambiar sin una petición explícita. Por eso:

1. **`tests/test_panel_page.py`:** tests estáticos de pytest sobre la página servida. Comprueban:
   - el listener de `hashchange`;
   - los atributos ARIA de las pestañas;
   - que los chips son `<button>`;
   - la regex de ids seguros y los tres comandos copiables con su prefijo;
   - que «sin hallazgos» no aparece para `sin_veredicto`;
   - el texto «Cargando…»;
   - que no se usa `document.execCommand`;
   - que siguen en vigor las comprobaciones de `test_panel_server.py`.
2. **Prueba de humo en el navegador:** con el panel sobre los datos reales, recorrer cada escenario de la spec y registrar el resultado en `progress.md`. Las capturas no se versionan. Se hace con Claude in Chrome si la extensión está conectada; si no, con Chrome headless, como en la revisión que originó este cambio.

**Alternativa descartada:** tests de JS con `node`, que está instalado. Habría que añadirlo a `check.sh` o saltar los tests cuando falte, y lo primero exige una petición explícita.

## Risks / Trade-offs

- [`index.html` crece unas 250–350 líneas] → Agrupar las funciones nuevas en secciones con cabecera, como las actuales. Revisar la complejidad con `factory complexity`, que solo cubre Python, así que la revisión del `checker` debe mirar el JS a mano.
- [Los tests estáticos no prueban el comportamiento] → La prueba de humo en el navegador es obligatoria para promover cada feature, y su resultado queda en `progress.md`.
- [El rehacer el tablero en cada refresco pierde el foco del buscador] → El buscador queda fuera del contenedor que se vuelve a dibujar, o se restaura el foco y la selección tras el render.
- [Atrás y Adelante con un `#tareas/<id>` de una feature que ya no existe] → Se muestra la pestaña Tareas sin detalle, igual que hoy con un hash desconocido.
- [Cambiar el valor guardado de `panel-theme`] → `light` y `dark` se conservan. Un valor desconocido se trata como `system`.

## Migration Plan

No hay migración de datos. Las preferencias antiguas de `localStorage` siguen siendo válidas. Para volver atrás, basta con revertir `index.html`.

**Orden de archivado:** primero `add-panel`, que crea la spec `observability-panel`, y después este cambio, que solo le añade requisitos.
