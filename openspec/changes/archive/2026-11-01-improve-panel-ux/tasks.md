# Tasks

> Los grupos 2 a 4 son cada uno una feature de `feature_list.json`, y se trabajan con WIP=1:
> 1. `factory features start <id>`;
> 2. las tareas del grupo;
> 3. la prueba de humo en el navegador (design D11);
> 4. `factory features verify <id>`;
> 5. la siguiente feature.
>
> No se empieza hasta que `strands-runner` deje de estar `in_progress`. Solo se edita `src/factory/panel/static/index.html`, más los tests y la documentación. Los tests de la página usan la página servida o empaquetada, nunca el `.factory/` real.

## 1. Preparación

- [x] 1.1 Añadir a `feature_list.json` las features `panel-ux-fixes` (30), `panel-ux-actions` (31) y `panel-ux-views` (32), en `not_started`, con `evidence: []` y el comando `python -m pytest -q tests/test_panel_page.py tests/test_panel_server.py`. Crear `tests/test_panel_page.py` con un helper que lea la página empaquetada (como `page()` en `test_panel_server.py`). Verificar que `factory features validate` y `./scripts/check.sh` pasan.

## 2. Correcciones y navegación (`panel-ux-fixes`)

- [x] 2.1 Estado de carga (D3): mientras no haya instantánea, cada vista muestra «Cargando…». El error de la primera carga sustituye ese texto. Verificar con `pytest tests/test_panel_page.py`, que comprueba que `selectTab` no dibuja vistas sin instantánea y que existe el texto «Cargando…». Verificar también en el navegador, escenarios "Primera carga lenta" y "Primera carga fallida" (con el servidor parado).
- [x] 2.2 Día UTC explícito y huecos (D4): rotular «UTC» en el indicador y en el eje, y rellenar con ceros los días que faltan entre el mínimo y el máximo de `by_day`. Verificar con `pytest tests/test_panel_page.py` y, en el navegador, con el escenario "Días sin actividad" sobre los datos reales.
- [x] 2.3 Revisión sin veredicto: mostrar «—» en lugar de `severityText()` para `sin_veredicto`. Verificar con `pytest tests/test_panel_page.py` y, en el navegador, con el escenario "Revisor que no dio veredicto".
- [x] 2.4 Navegación con el historial y pestañas accesibles (D2, D5): un único listener de `hashchange`, clics que solo asignan `location.hash`, `aria-controls`, `aria-labelledby`, *roving tabindex* y teclas de flecha, Inicio y Fin. Verificar con `pytest tests/test_panel_page.py`: listener de `hashchange` y atributos ARIA. Verificar en el navegador los escenarios "Botón Atrás", "Enlace a una feature" y "Flecha derecha".
- [x] 2.5 Detalle visible (D6): desplazar hasta el detalle y darle el foco al abrirlo, y devolver el foco a la tarjeta al cerrarlo. Verificar en el navegador los escenarios "Feature al final del tablero" y "Cerrar el detalle".
- [x] 2.6 Documentar en `docs/harness/panel.md` la carga, el día UTC del gráfico, la navegación con el historial y el teclado. Pasar `./scripts/check.sh` (código 0), registrar la prueba de humo en `progress.md` y ejecutar `factory features verify panel-ux-fixes`.

## 3. Botones y acciones (`panel-ux-actions`)

- [x] 3.1 Selector de tema de tres posiciones (D5). Verificar con `pytest tests/test_panel_page.py`: los valores `system`, `light` y `dark`, y que un valor desconocido equivale a `system`. Verificar en el navegador el escenario "Volver al tema del sistema".
- [x] 3.2 Filtros del feed: los chips pasan a ser `<button aria-pressed>`, más el interruptor «Ocultar sin cierre / sin veredicto», recordado en `localStorage` (D5). Verificar con `pytest tests/test_panel_page.py` y, en el navegador, con los escenarios "Filtrar por fallidas" y "Ocultar revisiones sin cierre".
- [x] 3.3 Indicadores enlazables: «Feature en curso», «Revisiones en curso» (con el filtro `en_curso`) y «Coste registrado» pasan a ser `<a href="#…">` con foco visible. Verificar en el navegador el escenario "Ir a la feature en curso".
- [x] 3.4 Frescura: «Actualizado hace N s» con el temporizador que ya existe, y un botón de refresco que llama a `refresh()`. Verificar en el navegador el escenario "Refresco manual".
- [x] 3.5 Comandos copiables (D7): la regex `^[A-Za-z0-9._-]+$`, los tres comandos con el prefijo `.venv/bin/factory` según el estado de la ejecución, la confirmación «Copiado» y el respaldo con `<code>` seleccionado. Verificar con `pytest tests/test_panel_page.py`:
  - la regex y los tres comandos aparecen en la página;
  - no hay `execCommand`;
  - no hay `fetch` con un método distinto de `GET`.

  Verificar también `pytest tests/test_panel_server.py` (escenario "Escritura" sigue con 405). En el navegador, verificar los escenarios "Copiar la verificación", "Ejecución integrable" e "Identificador con metacaracteres". Este último, con un `feature_list.json` de un repo temporal servido con `--root`.
- [x] 3.6 Documentar en `docs/harness/panel.md` el tema, los filtros, los indicadores enlazables y los comandos copiables, y dejar claro que el panel no ejecuta nada. Pasar `./scripts/check.sh` (código 0), registrar la prueba de humo en `progress.md` y ejecutar `factory features verify panel-ux-actions`.

## 4. Legibilidad de las vistas (`panel-ux-views`)

- [x] 4.1 Interruptor de lectura de caché, desactivado por defecto y recordado en `panel-cache-read`, con una nota de lo oculto. «Ver tabla» sigue con las cuatro columnas (D8). Verificar en el navegador el escenario "Vista por defecto" y que la suma de la nota coincide con la columna de la tabla.
- [x] 4.2 Tablero compacto (D9): «Terminadas» plegada en un `<details>` con clave estable, más un buscador que sobrevive a los refrescos y abre «Terminadas» mientras tiene texto. Verificar en el navegador el escenario "Buscar una feature terminada", y que un refresco por SSE (por ejemplo, `touch feature_list.json`) no cierra el plegable ni borra la búsqueda.
- [x] 4.3 Texto legible (D10):
  - `richText()` para los títulos y las tareas de OpenSpec;
  - estados en español con el `title` original;
  - `<title>` en las etiquetas recortadas del SVG;
  - la columna «Proyecto» oculta si no aporta.

  Verificar con `pytest tests/test_panel_page.py`: `richText` crea `<code>` sin `innerHTML`, y está el mapa de estados en español. En el navegador, verificar los escenarios "Grupo con id entre comillas invertidas", "Estado traducido" y "Todas las sesiones en el repo principal".
- [x] 4.4 Documentar en `docs/harness/panel.md` el interruptor de caché, el tablero plegado y el buscador. Pasar `./scripts/check.sh` (código 0), registrar la prueba de humo en `progress.md` y ejecutar `factory features verify panel-ux-views`.

## 5. Integración

- [x] 5.1 Validar el cambio con `openspec validate improve-panel-ux --strict` y pasar `./scripts/check.sh` (código 0). Hacer una prueba de humo completa sobre los datos reales con `factory panel --open`:
  - recorrer las tres pestañas en tema claro y oscuro;
  - comprobar que una revisión nueva aparece sin recargar y respeta los filtros activos.

  Registrarla en `progress.md`.

## Workflow follow-up

- Pedir la revisión independiente del `checker` con el diff y estos criterios, y corregir los hallazgos `critical` y `medium` hasta que no quede ninguno abierto.
- Archivar primero `add-panel` y después este cambio con `/opsx:archive`, sincronizando la spec `observability-panel`.
