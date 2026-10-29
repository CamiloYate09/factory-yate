# Cerebros de conocimiento

factory usa dos "cerebros" en Markdown, compatibles con cualquier LLM. Cualquiera de los dos se puede abrir en Obsidian o leer con `cat` y `grep`.

| | Cerebro principal | Cerebro diario |
|---|---|---|
| Qué es | tu biblioteca técnica (libros convertidos a notas atómicas) | lo que aprendes en el día a día |
| Ruta (`[brain]` en `factory.toml`) | `principal_dir = "brain-principal"` | `daily_dir = "brain-diario"` |
| Git | **nunca** se versiona (libros de terceros) | se versiona (es conocimiento tuyo) |
| Quién escribe | solo `factory brain import` | `factory brain learn` y las capturas que aceptes |
| Los loops | solo lectura | solo lectura (ruta prohibida en todo objetivo) |

Solo se trabaja con archivos **`.md`** y con los índices que los describen (`_catalog.jsonl`, `_books.json`, `llms.txt`). Los PDF nunca se importan y `.gitignore` los descarta (`*.pdf`).

## Cerebro principal

```bash
.venv/bin/factory brain import /ruta/redPDF/book/obsidian-vault   # copia solo .md + índices
.venv/bin/factory brain status                                    # origen, fecha, notas, libros, tokens
```

- **Copia filtrada.** Se copian las notas `.md`, `_catalog.jsonl`, `_books.json`, `llms.txt` y las guías (`AGENTS.md`, `CLAUDE.md`, `Index.md`). Se excluyen `.obsidian/`, `_build/`, los PDF y cualquier otro archivo. El origen no se modifica nunca.
- **Validación.** Cada ruta de `_catalog.jsonl` debe existir. Si falta alguna, la importación falla y la copia anterior queda intacta.
- **Refresco atómico.** Tras regenerar el vault (por ejemplo con `vault_builder.py`), basta con repetir `import`: la copia nueva se construye aparte y sustituye a la anterior de golpe, y las notas eliminadas desaparecen. Si la importación se interrumpe, se conserva la copia anterior.
- **Registro.** `brain-principal/.factory-import.json` guarda el origen, la fecha, el número de notas y libros, los tokens y la huella del catálogo.
- **Fuera de git.** Si el destino está dentro del repo, `import` lo añade a `.gitignore`. `factory doctor` falla (crítica) si algún archivo del cerebro principal llega al índice de git.
- **Integridad.** factory guarda una huella del cerebro y la compara al terminar cada ejecución de loop. Si un agente lo modificara, la ejecución lo avisa en `decision.md` y en la bandeja.

## Cerebro diario

```bash
.venv/bin/factory brain learn "En macOS no existe timeout; usar el de la herramienta" --kind gotcha --tags macos,shell
.venv/bin/factory brain learn --file aprendizaje.md --kind decision --title "Por qué worktrees fuera del repo"
.venv/bin/factory brain reindex              # tras editar notas a mano
.venv/bin/factory brain commit -m "notas"    # commit SOLO de brain-diario/ (sin push)
```

- **Formato.** Cada aprendizaje es `brain-diario/AAAA/MM/AAAA-MM-DD-<slug>.md`. Su frontmatter lleva `id`, `type` (`learning`, `decision`, `gotcha` o `pattern`), `title`, `date`, `tags`, `keywords`, `abstract`, `source` (`manual`, `run:<id>` o `intake:<id>`) y `tokens`, con el mismo formato que el principal.
- **Índices.** factory regenera `_catalog.jsonl`, `AGENTS.md` y `llms.txt` en cada alta. `reindex` los reconstruye tras editar notas a mano e informa de las que tienen el frontmatter roto.
- **Protegido de los loops.** `brain-diario/**` es una ruta prohibida en **todo** objetivo: si una ronda crea, modifica o borra algo ahí, se revierte. Ni `factory.toml` ni `goal.md` pueden levantar la prohibición.
- **Commit explícito.** Nada se commitea solo. `factory brain commit` hace un commit únicamente de `brain-diario/` y deja intactos el resto de cambios. `factory status` avisa de las notas sin commitear, y si `factory land` rechaza un checkout con notas pendientes, sugiere `factory brain commit`.

## Capturas desde los loops

Al terminar cada ejecución, factory **propone** aprendizajes a partir de lo que ocurrió. No usa modelos: aplica plantillas a los datos de la ejecución.

| Fuente | Tipo de nota |
|---|---|
| hallazgo `critical`/`medium` del checker que se corrigió antes de la ronda aprobada | `gotcha` |
| pregunta del maker + tu respuesta en un `factory goal rework` | `decision` |
| ejecución `stalled` (firma de fallo repetida) | `gotcha` |

```bash
.venv/bin/factory brain pending          # lista de capturas pendientes (también la cuenta factory status)
.venv/bin/factory brain accept <id>      # la convierte en nota del cerebro diario (source: run:<id>)
.venv/bin/factory brain reject <id>      # la descarta; queda constancia en .factory/brain/rejected/
```

- **Siempre pendientes.** Las capturas se guardan en `.factory/brain/pending/`, fuera de git, y nunca entran solas al cerebro diario.
- **Sin texto de libros.** Si un hallazgo copia 8 o más palabras seguidas de una nota inyectada del cerebro principal, ese fragmento se sustituye por `[texto de referencia omitido: ver <cita>]`.

## Recuperación e inyección

```bash
.venv/bin/factory brain search "rate limiting"                    # ambos cerebros
.venv/bin/factory brain search "token bucket" --brain principal --limit 5 --json
```

La búsqueda es local y por palabras clave sobre los catálogos (título, keywords, sección, resumen y libro), sin acentos ni palabras vacías. Cada resultado trae ruta, título, cita (`Libro · cap. N · pp. A–B` o `Cerebro diario · fecha · origen`) y tokens. **El cerebro principal está en inglés**: busca en inglés.

Declara en el objetivo qué conocimiento necesita:

```yaml
knowledge:
  queries: ["rate limiting", "api gateway"]   # en inglés; el intake las propone en sus borradores
  # enabled: false                            # sin inyección para este objetivo
```

- **Una selección por ejecución.** Al empezar, el orquestador busca con `knowledge.queries` en el principal (o con el objetivo si no hay consultas) y con las consultas más el objetivo en el diario. Intercala los resultados de cada consulta (la mejor de cada una, luego la segunda…) hasta `[brain] search_limit` notas, para que ninguna consulta se quede sin representación.
- **Presupuesto.** Incluye el texto completo, en ese orden, mientras quepa en `[brain] inject_max_tokens` (se mide el texto que de verdad se inyecta); el resto aparece solo con su cita, ruta y resumen. El maker puede leer cualquiera con sus herramientas.
- **Tolerante a fallos.** Si un catálogo está roto (por ejemplo, el del diario editado a mano), el loop y el intake siguen sin conocimiento y la ejecución lo avisa en "Bloqueos y avisos". `factory brain reindex` lo repara.
- **Dato citado, nunca instrucciones.** El bloque va en el prompt de **usuario** del maker, tras "Estado del loop", entre `----- INICIO/FIN DEL CONOCIMIENTO -----`, con cada línea citada (`>`) y un aviso de que no contiene órdenes. Nunca entra en el prompt de sistema.
- **El checker no recibe conocimiento.** Juzga solo con los criterios, el diff y la verificación.
- **Intake.** Recibe las notas del diario relevantes para la petición (mismo formato y presupuesto) y las rutas de los dos catálogos.
- **Eventos.** Cada ronda registra un evento `knowledge` en `events.jsonl`: consultas, resultados, notas inyectadas y referenciadas, y tokens. También con 0 resultados.

### Acceso de lectura seguro

Maker, checker e intake reciben `--add-dir <ruta absoluta>` por cada cerebro existente, y siempre (exista o no) las denegaciones `Edit(//<ruta>/**)` y `Write(//<ruta>/**)`. Se añaden en cada invocación, así que ni `factory.toml` ni `goal.md` pueden quitarlas. Como las listas de herramientas no son un sandbox, factory además compara la huella de ambos cerebros (notas `.md` e índices, sin archivos ocultos como `.DS_Store` u `.obsidian/`) al empezar y al terminar cada ejecución: si cambian o aparece uno nuevo, `decision.md` y la bandeja muestran un **AVISO de integridad** (en el principal, reimporta con `factory brain import`).

Comprobado con `claude -p` real (Claude Code, `acceptEdits`): un `Write` nuevo y un `Edit` sobre una nota existente del cerebro quedan en `permission_denials` sin tocar nada, y la lectura sí funciona. El `CLAUDE.md` o `AGENTS.md` de un cerebro **no** se carga en el contexto por estar en `--add-dir`: el agente solo lo ve si lo abre. Las rutas se resuelven (enlaces incluidos) para que `--add-dir` y las denegaciones usen exactamente la misma.

---
Requisitos en `openspec/specs/{main-brain,daily-brain,brain-retrieval}/`; diseño en `openspec/changes/archive/2026-10-28-add-knowledge-brains/`.
