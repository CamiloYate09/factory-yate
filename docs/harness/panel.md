# Panel de observabilidad

`factory panel` abre un panel gráfico local con tres vistas:

- **consumo de tokens** de los loops y de las sesiones de Claude Code;
- **revisiones en tiempo real**, capturadas con hooks;
- **estado de implementación** de features, cambios OpenSpec y ejecuciones.

> Esbozo. El cambio OpenSpec `add-panel` completa este documento a medida que avanza (ver `openspec/changes/add-panel/`).

```bash
.venv/bin/factory panel            # sirve http://127.0.0.1:8765 hasta Ctrl+C
.venv/bin/factory panel --json     # imprime la instantánea y termina
```

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
- se toma la primera palabra `pass_with_minor`, `pass` o `fail` tras una cabecera `Veredicto`, con el formato del `checker`;
- si no hay cabecera, una clave JSON `"verdict"`;
- si no aparece ninguna, queda como `sin_veredicto`.

Las severidades se cuentan en los títulos y viñetas de hallazgo (`[critical]`, `[medium]`, `[minor]`, `[low]`).

**Feed:**
- une cada inicio con su fin por `tool_use_id` o, si falta, por el último inicio abierto de la misma sesión y tipo;
- muestra `en_curso` con el tiempo transcurrido;
- añade el veredicto del checker de cada ronda de los loops (`state.json`).

**Latencia** (2026-10-29, 10 repeticiones): unos 68 ms por evento, incluido un `SubagentStop` que lee una transcripción de 412 KB.

**Desactivar:** quita las dos entradas de `.claude/settings.json`, o usa `/hooks`. Para borrar el histórico, elimina `.factory/hooks/`.

> Un `settings.json` nuevo puede no cargarse en una sesión ya abierta. Abre `/hooks` una vez o reinicia la sesión.
