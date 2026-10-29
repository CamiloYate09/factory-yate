# main-brain Specification

## Purpose

Mantiene una copia local, refrescable y de solo lectura de la biblioteca técnica principal (vault de libros convertidos a notas con catálogo). Así los agentes pueden consultarla sin modificar el origen y sin que su contenido entre nunca en el control de versiones.

## Requirements

### Requirement: Importación desde un vault
`factory brain import <ruta-del-vault>` SHALL copiar a la ruta configurada del cerebro principal las notas `.md`, el catálogo `_catalog.jsonl` y los índices del vault (`_books.json`, `llms.txt`, `AGENTS.md`, `CLAUDE.md` e `Index.md` cuando existan). MUST excluir `.obsidian/`, `_build/`, los PDF y cualquier otro archivo que no sea Markdown ni índice. El origen MUST quedar sin modificar.

#### Scenario: Importar un vault
- **WHEN** se importa un vault que contiene notas, catálogo, `.obsidian/`, un PDF y `_build/`
- **THEN** la copia contiene las notas, el catálogo y los índices, no contiene `.obsidian/`, PDF ni `_build/`, y ningún archivo del origen cambia

### Requirement: Validación del catálogo
La importación SHALL validar que el origen tiene `_catalog.jsonl` y que cada ruta del catálogo existe entre las notas copiadas. Si la validación falla, la importación MUST terminar con código distinto de cero y la copia anterior del cerebro principal MUST quedar intacta.

#### Scenario: Catálogo con rutas inexistentes
- **WHEN** el catálogo del origen referencia una nota que no existe
- **THEN** la importación falla, nombra la ruta que falta y el cerebro principal sigue siendo el de la importación anterior

#### Scenario: Origen sin catálogo
- **WHEN** se importa una carpeta sin `_catalog.jsonl`
- **THEN** la importación falla indicando que el origen no es un vault con catálogo y no se crea ni modifica nada

### Requirement: Refresco atómico
Repetir la importación SHALL reemplazar la copia completa de forma atómica: primero construye la copia nueva en un directorio temporal y después la sustituye. Las notas que ya no existen en el origen MUST desaparecer de la copia. Una importación interrumpida MUST dejar intacta la copia anterior.

#### Scenario: Refresco tras regenerar el vault
- **WHEN** el vault se regeneró con notas nuevas y alguna eliminada, y se repite la importación
- **THEN** la copia contiene las notas nuevas, ya no contiene las eliminadas y su catálogo coincide con el del origen

#### Scenario: Importación interrumpida
- **WHEN** la importación falla a mitad de la copia
- **THEN** la ruta del cerebro principal conserva la copia anterior completa y no quedan directorios temporales a la vista de los agentes

### Requirement: Registro de la importación
Cada importación correcta SHALL registrar sus metadatos junto a la copia: ruta de origen, fecha, número de notas, número de libros, tokens totales y huella del catálogo. `factory brain status` MUST mostrarlos.

#### Scenario: Estado del cerebro principal
- **WHEN** se ejecuta `factory brain status` tras una importación
- **THEN** se muestran el origen, la fecha, el número de notas, el número de libros, los tokens totales y la huella del catálogo

### Requirement: Fuera del control de versiones
Si la ruta del cerebro principal está dentro del repositorio, la importación SHALL asegurarse de que está ignorada por git. `factory doctor` MUST marcar como fallo crítico cualquier archivo del cerebro principal que esté versionado.

#### Scenario: Primera importación dentro del repo
- **WHEN** se importa por primera vez a `brain-principal/` dentro del repositorio
- **THEN** `brain-principal/` queda en `.gitignore` y `git status` no muestra ninguno de sus archivos

#### Scenario: Cerebro principal versionado por error
- **WHEN** algún archivo bajo la ruta del cerebro principal está en el índice de git
- **THEN** `factory doctor` falla con una comprobación crítica que nombra el archivo y explica cómo sacarlo del índice

### Requirement: Solo lectura durante los loops
Ningún comando de factory SHALL modificar el cerebro principal salvo la importación. Al terminar cada ejecución de loop, el orquestador MUST comparar la huella del catálogo y de las notas con la del inicio. Si cambió, debe registrar un aviso en el estado de la ejecución y en la bandeja.

#### Scenario: Cambio en el cerebro principal durante una ejecución
- **WHEN** la huella del cerebro principal difiere entre el inicio y el final de una ejecución
- **THEN** `decision.md` y la entrada de la bandeja incluyen un aviso de integridad que recomienda reimportar
