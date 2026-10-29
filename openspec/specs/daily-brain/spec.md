# daily-brain Specification

## Purpose

Acumula el conocimiento que se aprende en el día a día, a mano o a partir de lo que ocurre en los loops, como notas Markdown versionables y compatibles con cualquier LLM. Toda captura automática pasa por una revisión humana antes de formar parte del cerebro.

## Requirements

### Requirement: Notas diarias compatibles con cualquier LLM
Cada aprendizaje SHALL guardarse como una nota Markdown en `<cerebro-diario>/AAAA/MM/AAAA-MM-DD-<slug>.md`. Su frontmatter MUST incluir `id`, `type`, `title`, `date`, `tags`, `keywords`, `abstract`, `source` y `tokens`, con el mismo significado que en el cerebro principal. El cerebro diario MUST mantener `_catalog.jsonl` (una línea por nota), `AGENTS.md` y `llms.txt`.

#### Scenario: Primera nota
- **WHEN** se añade la primera nota a un cerebro diario vacío
- **THEN** existe la nota en la carpeta de su fecha, `_catalog.jsonl` tiene una línea con su ruta, título, palabras clave, resumen y tokens, y `llms.txt` y `AGENTS.md` explican cómo consultarlo

### Requirement: Alta manual
`factory brain learn "<texto>"` o `--file <archivo>` SHALL crear una nota con el tipo indicado (`learning`, `decision`, `gotcha` o `pattern`; por defecto `learning`). Admite título y etiquetas opcionales y registra `source: manual`. El catálogo y los índices MUST actualizarse en la misma operación.

#### Scenario: Aprendizaje manual
- **WHEN** se ejecuta `factory brain learn "En macOS no existe timeout; usar el de la herramienta" --kind gotcha --tags macos,shell`
- **THEN** se crea una nota `type: gotcha` con esas etiquetas y `source: manual`, y aparece en el catálogo

### Requirement: Catálogo regenerable
`factory brain reindex` SHALL reconstruir el catálogo y los índices del cerebro diario a partir de las notas existentes, para reflejar también las ediciones hechas a mano. Una nota con frontmatter inválido MUST reportarse con su ruta y quedar fuera del catálogo, sin abortar el resto.

#### Scenario: Nota editada a mano
- **WHEN** se corrige a mano el título de una nota y se ejecuta `factory brain reindex`
- **THEN** el catálogo refleja el título nuevo

#### Scenario: Nota con frontmatter roto
- **WHEN** una nota tiene YAML inválido y se ejecuta `factory brain reindex`
- **THEN** el comando informa la ruta de la nota inválida, el resto de notas siguen en el catálogo y el comando termina con código distinto de cero

### Requirement: Capturas propuestas desde los loops
Al terminar cada ejecución, el orquestador SHALL proponer capturas generadas con plantillas deterministas a partir de los datos estructurados de la ejecución, sin invocar modelos:
- hallazgos `critical` o `medium` de una ronda que ya no aparecen en la ronda aprobada;
- la pregunta del maker junto con la respuesta humana de un retrabajo;
- la firma de un estancamiento.

#### Scenario: Hallazgo corregido
- **WHEN** una ejecución termina `completed` después de que el checker señalara un hallazgo `medium` que se corrigió en la ronda siguiente
- **THEN** existe una captura pendiente con la descripción del hallazgo, su corrección y la referencia a la ejecución, y el cerebro diario no cambió

#### Scenario: Ejecución sin nada que capturar
- **WHEN** una ejecución termina `completed` en la primera ronda sin hallazgos
- **THEN** no se crea ninguna captura pendiente

### Requirement: Las capturas quedan pendientes y sin texto de libros
Toda captura propuesta SHALL guardarse como pendiente en `.factory/brain/pending/`, fuera del control de versiones. Nunca MUST entrar directamente al cerebro diario, y su contenido MUST NOT incluir texto del cerebro principal, aunque se haya inyectado en la ejecución.

#### Scenario: Ejecución con conocimiento inyectado
- **WHEN** una ejecución que recibió notas del cerebro principal produce una captura
- **THEN** la captura queda en `.factory/brain/pending/` y no contiene texto de esas notas, como mucho su cita

### Requirement: Revisión de capturas
`factory brain pending` SHALL listar las capturas pendientes. `factory brain accept <id>` MUST convertir una captura en nota del cerebro diario, con `source` igual a la ejecución de origen. `factory brain reject <id>` MUST descartarla dejando constancia del descarte. Ninguna captura entra al cerebro diario sin uno de estos comandos.

#### Scenario: Aceptar una captura
- **WHEN** se ejecuta `factory brain accept <id>` sobre una captura pendiente
- **THEN** se crea la nota correspondiente en el cerebro diario, aparece en el catálogo y la captura deja de estar pendiente

#### Scenario: Rechazar una captura
- **WHEN** se ejecuta `factory brain reject <id>`
- **THEN** la captura deja de estar pendiente, no se crea ninguna nota y el descarte queda registrado

### Requirement: Protección frente a los loops
La ruta del cerebro diario SHALL tratarse en todo objetivo como ruta prohibida (`scope.deny`), igual que `feature_list.json`. Cualquier ronda que cree, modifique o borre archivos en ella MUST revertirse. Ni `factory.toml` ni `goal.md` pueden levantar esa prohibición.

#### Scenario: El maker escribe en el cerebro diario
- **WHEN** una ronda crea o modifica un archivo bajo la ruta del cerebro diario en el worktree
- **THEN** la ronda se revierte por violación de alcance y la retroalimentación nombra el archivo

### Requirement: Commit explícito del cerebro diario
Los comandos del cerebro diario y la importación SHALL escribir los archivos sin hacer commit. `factory brain commit` MUST hacer un commit solo de los cambios bajo la ruta del cerebro diario y la del mapa de la biblioteca, y dejar sin tocar cualquier otro cambio del checkout. `factory status` MUST avisar si el cerebro diario o el mapa tienen cambios sin commitear.

#### Scenario: Commit con otros cambios en el checkout
- **WHEN** hay notas nuevas en el cerebro diario y además un archivo de código modificado, y se ejecuta `factory brain commit`
- **THEN** el commit contiene solo los archivos del cerebro diario y el archivo de código sigue modificado sin commitear

#### Scenario: Aviso de cambios pendientes
- **WHEN** el cerebro diario tiene notas sin commitear
- **THEN** `factory status` muestra un aviso que sugiere `factory brain commit`

#### Scenario: Mapa regenerado por una importación
- **WHEN** una importación regenera el mapa y se ejecuta `factory brain commit`
- **THEN** el commit incluye los cambios del mapa y ningún archivo del cerebro principal
