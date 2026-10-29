# Tasks

> Del grupo 2 al 5, cada grupo es una feature de `feature_list.json`: se inicia con `factory features start <id>` y se cierra con `factory features verify <id>`. Los tests usan el vault sintético de `tests/fixtures/vault/` y nunca la ruta real de redPDF.

## 1. Preparación

- [x] 1.1 Añadir la sección `[brain]` a `config.py` (`principal_dir`, `daily_dir`, `inject_max_tokens` y `search_limit`), con rutas resueltas en absoluto desde la raíz del repo principal, y documentarla en el `factory.toml` del repo. Verificar con `pytest tests/test_config.py` (valores por defecto, rutas relativas y absolutas, y error con valores no positivos).
- [x] 1.2 Crear el vault sintético `tests/fixtures/vault/`:
  - 2 libros y 5 notas con frontmatter real;
  - `_catalog.jsonl`, `_books.json`, `llms.txt` y `AGENTS.md`;
  - `.obsidian/`, un `*.pdf` ficticio y `_build/`.

  Añadir a `feature_list.json` las features `main-brain`, `daily-brain`, `brain-captures` y `brain-retrieval` con sus comandos `pytest`. Verificar que `factory features validate` y `factory doctor` pasan.

## 2. Cerebro principal (`main-brain`)

- [x] 2.1 Implementar `brain/importer.py`:
  - copia filtrada a un directorio temporal: solo `*.md` e índices, sin ocultos, `_build/` ni PDFs;
  - validación del catálogo, `.factory-import.json` con metadatos y huella;
  - sustitución atómica con limpieza ante fallos;
  - garantía de `.gitignore` cuando el destino está dentro del repo.

  Verificar con `pytest tests/test_brain_import.py`. Escenarios:
  - "Importar un vault" (el origen no cambia: mismas huellas antes y después);
  - "Catálogo con rutas inexistentes";
  - "Origen sin catálogo";
  - "Refresco tras regenerar el vault";
  - "Importación interrumpida" (fallo simulado en la copia);
  - "Primera importación dentro del repo".
- [x] 2.2 Implementar `factory brain import <origen>` y `factory brain status`. Añadir a `doctor` la comprobación crítica "cerebro principal no versionado" y las recomendadas (importado, catálogo válido, sin restos `.tmp-`/`.old-`). Verificar con `pytest tests/test_brain_import.py tests/test_doctor.py`, escenarios "Estado del cerebro principal" y "Cerebro principal versionado por error".
- [x] 2.3 Implementar la huella de integridad de un cerebro (sha256 del catálogo más tamaños y fechas de modificación de las notas). Verificar con `pytest tests/test_brain_import.py`: la huella cambia al editar una nota y se mantiene sin cambios. Documentar el cerebro principal en `docs/harness/cerebros.md`, que debe enlazarse desde `AGENTS.md`, y cerrar con `factory features verify main-brain`.

## 3. Cerebro diario (`daily-brain`)

- [x] 3.1 Implementar `brain/daily.py`:
  - escritor único de notas `AAAA/MM/AAAA-MM-DD-<slug>.md` con el frontmatter de D6 (palabras clave y resumen deterministas, tokens = caracteres / 4);
  - regeneración de `_catalog.jsonl`, `AGENTS.md` y `llms.txt`;
  - `reindex`, que informa de las notas inválidas.

  Verificar con `pytest tests/test_brain_daily.py`, escenarios "Primera nota", "Nota editada a mano" y "Nota con frontmatter roto".
- [x] 3.2 Implementar `factory brain learn ("<texto>" | --file F) [--kind] [--title] [--tags]` y `factory brain reindex`. Verificar con `pytest tests/test_brain_daily.py`, escenario "Aprendizaje manual".
- [x] 3.3 Añadir `<daily_dir>/**` al `deny` efectivo de todo objetivo en el motor, sin que pueda configurarse. Verificar con `pytest tests/test_brain_daily.py`, escenario "El maker escribe en el cerebro diario" (`FakeRunner` crea una nota en el worktree y la ronda se revierte).
- [x] 3.4 Implementar `factory brain commit [-m]`:
  - hace commit solo de `<daily_dir>`, con la identidad del usuario o la de reserva con aviso, y sin push;
  - `factory status` avisa de cambios sin commitear en el diario;
  - el rechazo de `land` sugiere `factory brain commit` cuando los cambios sucios están en el diario.

  Verificar con `pytest tests/test_brain_daily.py tests/test_land.py`, escenarios "Commit con otros cambios en el checkout" y "Aviso de cambios pendientes". Documentarlo en `docs/harness/cerebros.md` y cerrar con `factory features verify daily-brain`.

## 4. Capturas (`daily-brain`)

- [x] 4.1 Implementar `brain/captures.py` con las plantillas de D7: hallazgo corregido, pregunta y respuesta de un retrabajo, y estancamiento. Las capturas se guardan pendientes en `.factory/brain/pending/` y se invocan al final de `engine._finalize`. Verificar con `pytest tests/test_brain_captures.py`, escenarios "Hallazgo corregido" y "Ejecución sin nada que capturar", más un caso de retrabajo y uno de estancamiento.
- [x] 4.2 Implementar la salvaguarda de n-gramas (8 palabras) contra el texto inyectado registrado en el evento `knowledge`. Verificar con `pytest tests/test_brain_captures.py`, escenario "Ejecución con conocimiento inyectado": un hallazgo que copia una frase del libro queda con la cita en lugar del texto.
- [x] 4.3 Implementar `factory brain pending | accept <id> | reject <id>`. `accept` usa el escritor del diario con `source: run:<id>`; `reject` mueve la captura a `.factory/brain/rejected/`. `factory status` muestra cuántas capturas hay pendientes. Verificar con `pytest tests/test_brain_captures.py`, escenarios "Aceptar una captura" y "Rechazar una captura". Documentar las capturas en `docs/harness/cerebros.md` y cerrar con `factory features verify brain-captures`.

## 5. Recuperación (`brain-retrieval`)

- [x] 5.1 Implementar `brain/catalog.py` y `brain/search.py`:
  - carga de los catálogos con caché;
  - tokenización sin acentos y sin palabras vacías en español e inglés;
  - puntuación ponderada de D3 y citas para el principal y el diario.

  Implementar también `factory brain search "<consulta>" [--brain] [--limit] [--json]`. Verificar con `pytest tests/test_brain_search.py`, escenarios "Consulta con resultados", "Consulta sin resultados" (sugiere términos en inglés) y "Cerebro no configurado o vacío".
- [x] 5.2 Añadir `knowledge.queries` y `knowledge.enabled` a `goal.py`, y `knowledge_queries` al esquema y a los borradores del intake (`render_draft`); actualizar `prompts/intake.md` para pedir consultas en inglés. Verificar con `pytest tests/test_brain_search.py tests/test_intake.py`, escenarios "Objetivo con consultas declaradas", "Borrador del intake" e "Inyección desactivada".
- [x] 5.3 Implementar en el motor la selección una vez por ejecución (D4):
  - el bloque citado y delimitado en el prompt de usuario del maker, después de "Estado del loop";
  - el presupuesto `inject_max_tokens` (texto completo, y luego solo cita);
  - el evento `knowledge`, también con 0 resultados.

  Verificar con `pytest tests/test_brain_inject.py`. Escenarios:
  - "Presupuesto respetado";
  - "Sin resultados";
  - "Nota con texto imperativo" (el prompt de sistema no contiene la nota);
  - "Ronda con inyección en el maker" (el prompt del checker no tiene sección de conocimiento).
- [x] 5.4 Inyectar en el intake las notas del diario relevantes para la petición y las rutas absolutas de los catálogos. Verificar con `pytest tests/test_brain_inject.py`, escenario "Petición relacionada con un aprendizaje previo".
- [x] 5.5 Implementar el acceso de lectura:
  - `AgentRequest.add_dirs` y `--add-dir` en `build_argv`;
  - denegaciones obligatorias `Edit/Write(<cerebro>/**)` para todos los roles (implementadas como `config.brain_denials`, añadidas en cada invocación después de los overrides de `factory.toml` y `goal.md`, que así no pueden quitarlas);
  - huella de ambos cerebros al inicio y al final de cada ejecución, con aviso en `blockers`, `decision.md` y la bandeja si cambian.

  Verificar con `pytest tests/test_brain_inject.py tests/test_claude_runner.py`, escenarios "Petición del maker con acceso a los cerebros" y "Cambio en el cerebro principal durante una ejecución". Documentar la recuperación en `docs/harness/cerebros.md` y en `loops.md` (`knowledge.queries`), y cerrar con `factory features verify brain-retrieval`.

## 6. Integración y validación

- [x] 6.1 Verificar que `./scripts/check.sh` termina en 0, que `factory doctor` no tiene fallos críticos, que `openspec validate add-knowledge-brains --strict` es válido y que las cuatro features nuevas están en `passing`. Añadir al README un paso G, "Cerebros de conocimiento" (importar, buscar, aprender, revisar capturas y commitear), con el aviso de que los libros no se versionan.
- [x] 6.2 Importar el vault real (`factory brain import /Users/camiloyateyara/PycharmProjects/redPDF/book/obsidian-vault`) sin coste de API y comprobar:
  - `factory brain status` muestra 11.245 notas y 82 libros;
  - `git status` no muestra nada de `brain-principal/`;
  - `factory brain search "rate limiting"` devuelve citas de *Defending APIs* o *Continuous API Management*.

  Registrar la evidencia en `progress.md`.
- [x] 6.3 **Con aprobación del usuario para el gasto** (0,50 USD o menos): con una invocación real de `claude -p` usando `--add-dir`, confirmar la sintaxis de las denegaciones absolutas (un intento de escritura en el cerebro debe ser denegado) y comprobar si se carga el `CLAUDE.md` del vault. Ajustar la sintaxis si hace falta y registrar la evidencia.

## Workflow follow-up

- Archivar con `/opsx:archive add-knowledge-brains` y sincronizar las specs `main-brain`, `daily-brain` y `brain-retrieval`.
- Posibles cambios futuros: búsqueda semántica con embeddings, resúmenes de capturas con LLM y uso compartido del cerebro diario entre proyectos.
