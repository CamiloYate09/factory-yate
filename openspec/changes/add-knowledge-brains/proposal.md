# Proposal

## Why

El harness y factory ya hacen fiables y autónomas las ejecuciones, pero cada agente arranca sin el conocimiento acumulado de su dueño. Hay dos fuentes de ese conocimiento:

- **Biblioteca técnica.** En `redPDF/book/obsidian-vault` hay 82 libros convertidos a 11.245 notas atómicas (unos 13 millones de tokens), con un catálogo legible por cualquier LLM. Hoy los agentes de factory no la usan.
- **Aprendizajes del día a día.** Lo que sale de los loops (hallazgos del checker, respuestas de retrabajo, decisiones del intake) se queda en `.factory/` y no vuelve a usarse.

Queremos dos "cerebros": uno principal, estable y de solo lectura, y uno diario que se alimente con el uso. Los agentes deben poder consultarlos de forma acotada y segura.

## What Changes

**Cerebro principal**
- `factory brain import <vault>` importa la biblioteca a una ruta configurable (por defecto `brain-principal/`).
  - Copia solo las notas `.md`, el catálogo y los índices; excluye `.obsidian/`, `_build/` y los PDFs.
  - Escribe primero en un directorio temporal y lo sustituye de golpe, así que la copia nunca queda a medias.
  - Valida el catálogo y nunca modifica el origen.
  - Repetirlo refresca la copia tras regenerar el vault.
- La copia queda **fuera de git**: son libros comerciales. `factory doctor` falla si se versiona.

**Cerebro diario**
- Notas Markdown en una carpeta versionable (por defecto `brain-diario/`), organizadas por fecha.
  - Usan el mismo formato de frontmatter y de `_catalog.jsonl` que el principal, más `AGENTS.md` y `llms.txt`, para que cualquier LLM las use.
  - `factory brain learn "…"` añade una nota.
- **Capturas automáticas para revisar.** Al terminar cada ejecución, factory propone capturas con plantillas deterministas a partir de los datos de la ejecución: hallazgos corregidos, preguntas y respuestas humanas, firmas de estancamiento.
  - Quedan pendientes en `.factory/` hasta `factory brain accept` o `reject`.
  - Nunca capturan texto de libros.
- El cerebro diario es **siempre protegido** frente a los loops: ningún maker puede editarlo.
- Los cambios en él no se commitean solos. `factory brain commit` hace un commit explícito, solo de esa carpeta.

**Recuperación**
- `factory brain search "<consulta>"` busca por palabras clave en el catálogo de ambos cerebros, sin dependencias ni embeddings, y cita libro, capítulo y páginas.
- **Inyección acotada en los prompts del maker y del intake.** El checker queda sin cambios: juzga solo criterios, diff y verificación.
  - Va dentro de un presupuesto de tokens y como **dato citado**, nunca como instrucciones.
  - Con cero resultados no se inyecta nada y queda registrado.
- **Consultas en inglés.** El vault está en inglés y los objetivos en español: una consulta como "rutas protegidas" da 0 resultados. Por eso las consultas al cerebro principal se declaran en inglés:
  - en `knowledge.queries` del `goal.md`;
  - propuestas por el intake en sus borradores;
  - el objetivo solo se usa como último recurso.
- **Lectura directa.** Los agentes pueden leer ambos cerebros mediante `--add-dir`, con denegaciones obligatorias de escritura. Al cerrar la ejecución, una comprobación de integridad detecta cualquier cambio en el cerebro principal.

**Fuera de alcance**
- Embeddings o bases vectoriales.
- Resúmenes de capturas generados por un LLM.
- Edición del cerebro principal.
- Sincronización entre máquinas.
- Inyección en el checker.
- Integración con Obsidian más allá del formato de archivos.

## Capabilities

### New Capabilities
- `main-brain`: importación, refresco, validación y protección de la biblioteca de conocimiento principal (solo lectura, fuera de git).
- `daily-brain`: notas de aprendizaje diario versionables, compatibles con cualquier LLM; alta manual, capturas pendientes de revisión, protección frente a los loops y commit explícito.
- `brain-retrieval`: búsqueda en ambos cerebros, consultas de conocimiento declaradas, inyección acotada y citada en los prompts del maker y del intake, y acceso de lectura seguro para los agentes.

### Modified Capabilities
<!-- Ninguna. La inyección no toca al checker, así que "Roles maker y checker independientes" (maker-checker-loop) no cambia. Las claves nuevas de goal.md y del esquema del intake se definen como requisitos ADDED de brain-retrieval. -->

## Impact

- **Código:**
  - módulos nuevos `src/factory/brain/`: importación, catálogo, notas diarias, capturas y búsqueda;
  - `config.py` (`[brain]`), `goal.py` (`knowledge.queries`);
  - `engine.py`: inyección en el maker, capturas al cerrar y comprobación de integridad;
  - `intake.py` y `schemas.py` (`knowledge_queries`), `agents/` (`--add-dir`);
  - `protection.py` (cerebro diario como ruta crítica), `doctor.py` y CLI (`factory brain …`).
- **Archivos:**
  - `brain-principal/`, en `.gitignore`;
  - `brain-diario/`, versionado, con `AGENTS.md`, `llms.txt` y `_catalog.jsonl`;
  - `.factory/brain/pending/`.
- **Datos:** el cerebro principal ocupa unos 110 MB en disco y no se versiona.
- **Dependencias:** ninguna nueva; la búsqueda usa solo la biblioteca estándar.
- **Coste:** sin llamadas extra a modelos. La inyección añade tokens de entrada, limitados por `[brain] inject_max_tokens`.
- **Licencias:** los libros son de sus autores. factory solo los copia localmente para uso personal y nunca los versiona ni los captura en el cerebro diario.
