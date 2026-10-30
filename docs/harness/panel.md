# Panel de observabilidad

`factory panel` abre un panel gráfico local con tres vistas:

- **consumo de tokens** de los loops y de las sesiones de Claude Code;
- **revisiones en tiempo real**, capturadas con hooks;
- **estado de implementación** de features, cambios OpenSpec y ejecuciones.

No necesita red ni dependencias y no llama a la API: lee los archivos que ya dejan factory, OpenSpec y Claude Code. Requisitos y diseño: cambio OpenSpec `add-panel`.

## Uso

```bash
.venv/bin/factory panel                 # sirve http://127.0.0.1:8765 hasta Ctrl+C
.venv/bin/factory panel --open          # además, abre el navegador
.venv/bin/factory panel --port 9000     # otro puerto
.venv/bin/factory panel --json          # imprime la instantánea JSON y termina
.venv/bin/factory panel --projects-dir DIR   # transcripciones en otro sitio
```

La página tiene tres pestañas: **Tokens**, **Revisiones** y **Tareas**. Encima de ellas, una fila de indicadores:

- tokens de hoy y totales;
- proporción de caché;
- USD registrado por los loops;
- revisiones en curso;
- feature activa y bandeja.

El punto «En vivo» indica que el navegador recibe los avisos del servidor. Si se corta, la página se reconecta sola.

**Fuentes que lee** (también desde un worktree, porque resuelve siempre el repo principal):

| Sección | Archivos |
|---|---|
| `tokens` | `.factory/runs/*/events.jsonl` y transcripciones de Claude Code del proyecto |
| `reviews` | `.factory/hooks/events.jsonl` y `.factory/runs/*/state.json` |
| `tasks` | `feature_list.json`, `openspec/changes/*/tasks.md` (sin `archive/`), `.factory/runs/*/state.json` y `.factory/inbox/` |

Si un archivo falta, su parte queda vacía sin más: un repo sin ejecuciones ni hooks es normal. Si existe pero no se puede leer, también queda vacía y el problema aparece en `warnings`, arriba de la página.

## Consumo de tokens

La sección `tokens` de la instantánea tiene dos partes.

### `loops`: ejecuciones de factory

- **Fuente:** los eventos `agent` de `.factory/runs/*/events.jsonl` (ver [observabilidad](observabilidad.md)).
- **Medidas:** tokens de entrada y de salida, turnos, llamadas y **USD registrado**.
- **Agrupación:** por ejecución (con desglose por rol y modelo), por rol, por modelo y por día.
- **Línea no válida:** se ignora.

### `sessions`: sesiones de Claude Code

- **Fuente:** las transcripciones locales de Claude Code, en `--projects-dir`, si no `$CLAUDE_CONFIG_DIR/projects` y, si no, `~/.claude/projects`.
- **Directorios que cuentan:**
  - el del repo principal;
  - los de sus worktrees `.claude/worktrees/*` (el equipo), con sus subagentes.

  Los worktrees de los loops (`<repo>.factory-worktrees/…`) quedan fuera, porque ya cuentan en `loops`.
- **Medidas:** entrada, escritura de caché, lectura de caché, salida y mensajes.
- **Agrupación:**
  - por día (UTC);
  - por modelo;
  - por **tipo de agente**: `principal`, el `agentType` del subagente (`checker`, `Explore`, jugadores…) o `subagente` si no consta;
  - por sesión, con sus subagentes.
- **Proporción de caché:** lectura de caché ÷ entrada total.
- **Coste:** solo tokens, **sin USD**. Las transcripciones no traen coste y el panel no estima precios.

**Deduplicación.** Claude Code escribe una fila por bloque de contenido de cada respuesta y repite en todas el mismo `usage`. El panel cuenta cada mensaje una sola vez, por `message.id`. Si falta, usa `requestId` y, si también falta, `uuid`.

**Privacidad.** De cada fila solo se leen modelo, `usage`, marca de tiempo e identificadores. De los subagentes, además, el tipo y la descripción de su `meta.json`. El texto de los mensajes, las entradas de las herramientas y sus resultados nunca salen del parser.

**Caché incremental.** Con el panel abierto, cada archivo se lee una vez y después solo lo añadido. Si un archivo encoge o se sustituye, se relee entero.

Medida en este repo (2026-10-29, sin coste de API):

| Dato | Valor |
|---|---|
| Transcripciones | 25 (43,3 MB) |
| Agregación completa | 131 ms |
| Refresco incremental sin cambios | 4 ms |
| Contraste independiente de la mayor (recuento por `message.id`) | 629 mensajes y 870.292 tokens de salida, iguales a los del panel |

## Revisiones en tiempo real (hooks)

`.claude/settings.json` registra dos hooks de Claude Code. Los dos ejecutan `.claude/hooks/panel-hook.sh`:

| Evento | Matcher | Qué registra |
|---|---|---|
| `PreToolUse` | `Agent\|Task` | lanzamiento de un subagente: tipo, descripción, `tool_use_id` y si es revisor. **Nunca el prompt** |
| `SubagentStop` | (todos) | fin de un subagente. Si es revisor, también el veredicto, los hallazgos por severidad y un extracto de 4.000 caracteres como máximo de su última respuesta |

**Cómo funciona el script:**
- busca el repo principal con `git rev-parse --git-common-dir`, así que también funciona desde un worktree de `.claude/worktrees/`;
- ejecuta el módulo del hook con el `.venv` del repo principal;
- añade una línea a `.factory/hooks/events.jsonl`, bajo un bloqueo para las escrituras concurrentes.

El mismo código está disponible como `factory hook`, que lee el JSON del hook por stdin.

**Garantías:**
- el hook siempre termina en 0 y no escribe en stdout, así que nunca bloquea ni controla la herramienta;
- los errores van a stderr, visible con `claude --debug`;
- en `settings.json` va con `async: true`, de modo que la sesión no lo espera;
- sin `.venv` en el repo principal, no hace nada.

**¿Qué cuenta como revisión?** El `checker` (árbitro) y cualquier agente de `.claude/agents/` con `tipo: revisor` en su frontmatter, como los jugadores revisores del [equipo](equipo.md). Los demás subagentes (`Explore`, constructores…) se registran sin veredicto ni extracto y no salen en el feed.

**Veredicto:**
- se lee de la respuesta final del revisor: el `message` de su llamada a `SubagentHandback` (así entrega la respuesta esta versión de Claude Code); si no la hay, su último texto, o `last_assistant_message` del payload si la transcripción aún no la tiene;
- se toma la primera palabra `pass_with_minor`, `pass` o `fail` tras una cabecera `Veredicto`, con el formato del `checker`;
- si no hay cabecera, una clave JSON `"verdict"`;
- si no aparece ninguna, queda como `sin_veredicto`.

Las severidades se cuentan en los títulos y viñetas de hallazgo (`[critical]`, `[medium]`, `[minor]`, `[low]`) de la sección `Hallazgos`, si la hay. Así no se suman los hallazgos anteriores que repasa una segunda revisión. Límite conocido: una sub-viñeta que cite una severidad entre corchetes (`- … el [medium] anterior …`) cuenta como otro hallazgo.

**Feed:**
- une cada inicio con su fin por `tool_use_id` o, si falta, por el último inicio abierto de la misma sesión y tipo;
- muestra `en_curso` con el tiempo transcurrido. Pasadas 2 horas sin fin, muestra `sin_cierre`. Pasa si la sesión se cerró con el revisor trabajando, o si el lanzamiento falló y no llegó a haber subagente (por ejemplo, un tipo de agente creado después de abrir la sesión, que esta aún no conoce);
- añade el veredicto del checker de cada ronda de los loops (`state.json`).

**Latencia** (2026-10-29, 10 repeticiones): unos 68 ms por evento, incluido un `SubagentStop` que lee una transcripción de 412 KB.

**Desactivar:** quita las dos entradas de `.claude/settings.json`, o usa `/hooks`. Para borrar el histórico, elimina `.factory/hooks/`.

> Un `settings.json` nuevo puede no cargarse en una sesión ya abierta. Abre `/hooks` una vez o reinicia la sesión.

## Estado de implementación

La pestaña **Tareas** junta tres fuentes:

- **Features** de `feature_list.json`: un tablero por estado (en curso, bloqueadas, sin empezar y terminadas). Si una feature tiene tareas en un cambio OpenSpec, muestra su avance.
- **Cambios OpenSpec activos**: el avance de `tasks.md` por grupo. Solo cuenta una casilla `- [x]` del primer nivel; una subviñeta o una sección sin número, como *Workflow follow-up*, no son tareas. Un grupo se enlaza con una feature si su título la nombra entre comillas invertidas, como en ``## 2. Plantilla (`team-roster`)``.
- **Ejecuciones** de factory: estado, ronda, criterios superados, último veredicto, coste y si el proceso sigue vivo. Una ejecución `running` sin proceso aparece como huérfana.

Pulsar una feature abre su detalle, también enlazable como `#tareas/<id>`. El detalle reúne:

- el comportamiento esperado;
- los comandos de verificación;
- la última evidencia de cada comando;
- las tareas de su grupo, casilla a casilla;
- las ejecuciones y las revisiones que la mencionan.

## Tiempo real

- **Vigilancia:** el servidor sondea cada segundo la huella (`mtime` y tamaño) de los archivos de cada sección. No usa inotify ni FSEvents, que serían dependencias o código por plataforma.
- **Avisos:** si algo cambia, `/api/stream` (*server-sent events*) envía `event: change` con las secciones afectadas, y la página vuelve a pedir `/api/snapshot`.
- **Recarga:** mientras recarga, mantiene lo que ya muestra con menos opacidad, sin saltos.
- **Tiempo de las revisiones:** el de las revisiones en curso avanza en el navegador sin pedir datos.
- **Coste de cada refresco:** las transcripciones se leen de forma incremental (ver arriba), así que solo cuesta lo que se añadió.

## Privacidad

- **Todo es local:** el panel lee archivos de tu equipo y solo los sirve en `127.0.0.1`. No envía nada fuera.
- **Transcripciones:** solo modelo, `usage`, marcas de tiempo, identificadores y el tipo y la descripción de los subagentes (ver *Consumo de tokens*). Nunca el texto de los mensajes ni de las herramientas.
- **Hooks:** nunca el prompt del subagente. De los revisores, un extracto de 4.000 caracteres como máximo de su respuesta final, en `.factory/hooks/events.jsonl`, que no se versiona.

## Seguridad y solo lectura

- **Escucha:** solo en `127.0.0.1`. No hay opción para exponer el panel en la red.
- **Cabecera `Host`:** si no es `127.0.0.1`, `localhost` o `[::1]` (con o sin puerto), responde 403. Así, una web ajena no puede leer el panel con *DNS rebinding*.
- **Métodos:** solo `GET` y `HEAD`; cualquier otro recibe 405. No hay cabeceras CORS.
- **Cabeceras de respuesta:** `Content-Security-Policy` restringida al propio origen, `X-Content-Type-Options: nosniff` y `Cache-Control: no-store`.
- **Página:** no carga recursos externos (CSS, JS y gráficos SVG van en línea). Inserta todos los datos con `textContent`, nunca como HTML, porque los extractos de las revisiones vienen de agentes.
- **Solo lectura:** ni el servidor ni `--json` crean, modifican o borran archivos. La única escritura de todo el cambio es la línea que añade el hook al registro.

## Límites

- **USD:** solo el que registran los loops. Las sesiones interactivas se miden en tokens.
- **Formatos de Claude Code:** las transcripciones y los payloads de los hooks son formatos internos de Claude Code. El parser ignora lo que no entiende, y cada evento del hook guarda los nombres de los campos que llegaron (`payload_keys`, sin valores) para detectar cambios.
- **Pull requests de GitHub:** no los mira. En este repo, «revisión» es la del `checker` o la de un jugador revisor sobre un diff o una rama local.
- **Protección del hook:** `.claude/settings.json` y `.claude/hooks/**` son rutas críticas del harness desde `add-equipo-ideal` (`src/factory/protection.py`): la rama de un loop no puede modificar, borrar ni renombrar esos archivos, y ningún objetivo puede liberarlos.
