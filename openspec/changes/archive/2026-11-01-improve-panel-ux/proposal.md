# Proposal

## Why

Revisamos `factory panel` con capturas reales de las tres pestañas y leyendo `static/index.html`. El panel funciona, pero en varios puntos lleva a error:

- mientras carga, dice que no hay datos;
- «Tokens de hoy» usa el día UTC sin avisarlo;
- una revisión sin veredicto aparece como «sin hallazgos»;
- al pulsar una feature, el detalle se pinta fuera de la vista;
- los botones Atrás y Adelante del navegador cambian la URL, pero no la vista.

Además, hay controles que parecen accionables y no lo son: los chips de estado y las tarjetas de indicadores. Y el panel no ayuda a dar el siguiente paso: no dice qué comando ejecutar ante una feature o una ejecución.

## What Changes

**Correcciones (lo que hoy engaña)**
- Estado «Cargando…» hasta la primera instantánea, en lugar de los mensajes de vacío.
- El día de «Tokens de hoy» y el eje del gráfico se rotulan como UTC. Los días sin datos aparecen como hueco, no se omiten.
- Una revisión sin veredicto muestra «—» en lugar de «sin hallazgos».
- Al abrir una feature, la página se desplaza a su detalle y le da el foco. «Cerrar» devuelve el foco a la tarjeta.

**Navegación y botones**
- El `#hash` manda: Atrás y Adelante cambian de pestaña y de feature. Las pestañas se recorren con las flechas del teclado.
- El botón de tema muestra el tema activo y tiene tres posiciones: Sistema, Claro y Oscuro.
- Los chips de estado del feed de revisiones pasan a ser filtros. Se añade un interruptor para ocultar las revisiones `sin_cierre` y `sin_veredicto`.
- Las tarjetas de indicadores llevan a su vista: la feature en curso, el feed de revisiones en curso y las ejecuciones.
- Se muestra «Actualizado hace N s» y hay un botón para refrescar a mano.
- Botones **«Copiar comando»**, que solo usan el portapapeles del navegador:
  - `factory features verify <id>` en el detalle de una feature;
  - `factory goal rework <run> --answer ` en una ejecución terminada sin éxito, con la respuesta por escribir;
  - `factory land <run> --dry-run` en una ejecución `completed`.

  El panel nunca ejecuta nada.

**Legibilidad de las vistas**
- Tokens:
  - un interruptor para excluir la lectura de caché del gráfico por día, que hoy es el 98 % y tapa la entrada, la salida y la escritura de caché;
  - la columna «Proyecto» se oculta si todas las filas dicen lo mismo;
  - las etiquetas recortadas muestran el texto completo al pasar el ratón.
- Revisiones: estados en español («aprobado con menores»), con el valor original como título.
- Tareas:
  - la columna «Terminadas» queda plegada por defecto;
  - un buscador por id y título;
  - el texto entre comillas invertidas de OpenSpec se muestra como código.

**Fuera de alcance**
- Ejecutar comandos o escribir desde el panel. Sigue siendo de solo lectura: solo `GET` y `HEAD`.
- Cambiar el servidor, la instantánea o la agregación por día UTC de `token-usage`.
- Agrupar el feed de revisiones por feature o por cambio.
- El diseño en pantallas estrechas: no se pudo comprobar con fiabilidad en esta revisión.

## Capabilities

### New Capabilities
<!-- Ninguna. -->

### Modified Capabilities
- `observability-panel`: nuevos requisitos de la página: estado de carga, navegación por `#hash`, filtros, indicadores enlazables, frescura, comandos copiables y legibilidad.

  La capacidad la introduce el cambio `add-panel`, aún sin archivar. Por eso el delta solo usa `ADDED`, y hay que archivar `add-panel` antes que este cambio.

## Impact

- **Código:** solo `src/factory/panel/static/index.html`. No cambian `server.py`, `snapshot.py` ni la forma de la instantánea.
- **Tests:** uno nuevo, `tests/test_panel_page.py`, con comprobaciones estáticas de la página, más una prueba de humo en el navegador, registrada en `progress.md`. Siguen en vigor los tests de `test_panel_server.py`: sin `innerHTML` y sin recursos externos.
- **Documentación:** `docs/harness/panel.md` (pestañas, filtros, comandos copiables y tema).
- **Features:** tres nuevas en `feature_list.json`: `panel-ux-fixes`, `panel-ux-actions` y `panel-ux-views`. Esperan a que termine `strands-runner`, porque solo puede haber una feature en curso (WIP=1).
- **Dependencias:** ninguna.
- **Seguridad:**
  - el portapapeles exige un contexto seguro, y `127.0.0.1` lo es;
  - los comandos copiables solo se ofrecen con identificadores seguros, sin metacaracteres de shell.
