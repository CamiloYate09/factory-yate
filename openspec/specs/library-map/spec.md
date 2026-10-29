# library-map Specification

## Purpose

Da a cada clon del repositorio un mapa de la biblioteca técnica: qué libros, capítulos y secciones existen y dónde está cada tema. No contiene ningún texto de los libros, que solo vive fuera de git en los equipos de su dueño.

## Requirements

### Requirement: Generación del mapa en cada importación
Cada `factory brain import` correcta SHALL regenerar el mapa de la biblioteca en `[brain] map_dir` (por defecto `brain-mapa/`) a partir del catálogo importado. El mapa contiene un catálogo por nota, una lista de libros, una guía para agentes y un `.gitignore` propio que solo deja versionar sus archivos. La salida MUST ser determinista.

#### Scenario: Importación con mapa
- **WHEN** se importa un vault con 5 notas de 2 libros
- **THEN** el mapa contiene un catálogo con 5 líneas, una lista con 2 libros y una guía `AGENTS.md`, y `factory brain import` informa de la ruta del mapa

#### Scenario: Reimportación sin cambios
- **WHEN** se reimporta el mismo vault
- **THEN** ningún archivo del mapa cambia y `git status` no muestra diferencias en él

### Requirement: Aviso si el mapa no se versiona
Si git ignora la ruta del mapa, la importación SHALL avisar de que el mapa no viajará con el repo y `factory doctor` MUST marcarlo con una comprobación recomendada. `factory brain commit` MUST seguir commiteando el cerebro diario.

#### Scenario: Mapa en .gitignore
- **WHEN** `brain-mapa/` está en `.gitignore` y se importa el vault
- **THEN** la importación avisa, `factory doctor` marca el mapa como no versionable y `factory brain commit` commitea las notas del diario sin error

### Requirement: El mapa no contiene texto de los libros
El mapa SHALL construirse campo a campo desde una lista blanca. Para las notas: ruta, libro, tipo, título, capítulo, título del capítulo, sección, páginas, tokens y keywords. Para los libros: identificador, título, autores, dominios, páginas, capítulos, notas, palabras y tokens. MUST NOT contener resúmenes, subtítulos, cuerpos de notas, notas `.md` ni las guías del vault.

#### Scenario: Catálogo con resúmenes
- **WHEN** el catálogo del vault incluye `abstract` en cada nota
- **THEN** ninguna línea del mapa tiene `abstract` y ninguna frase de los resúmenes ni de los cuerpos aparece en ningún archivo del mapa

#### Scenario: Campos desconocidos del vault
- **WHEN** el catálogo y la lista de libros del vault traen campos fuera de la lista blanca (por ejemplo `source`, `readme` o `body`)
- **THEN** las claves del mapa son exactamente las de la lista blanca y ningún valor de esos campos aparece en el mapa

### Requirement: Formatos estrictos de los valores
Cada valor del mapa SHALL cumplir un formato estricto: identificadores, tipo, capítulo y keywords sin espacios; autores de hasta 80 caracteres; listas solo como listas. Solo los títulos, las secciones y los autores admiten frases cortas, y los títulos y las secciones de más de 20 palabras se recortan.

#### Scenario: Encabezado sospechoso
- **WHEN** una sección del vault tiene un título de 40 palabras
- **THEN** el mapa guarda solo sus primeras 20 palabras

#### Scenario: Tipos inesperados
- **WHEN** una nota trae `pages` como número o `section_path` como texto
- **THEN** el mapa se genera sin error y guarda esos campos como listas vacías

### Requirement: Comprobación de doctor sobre el mapa
`factory doctor` SHALL fallar con una comprobación crítica si el texto de algún archivo del mapa no es exactamente el que generaría factory (un campo de más, un valor fuera de formato, una clave repetida, una guía distinta) o si falta o sobra un archivo que git versionaría. Los archivos que git no versionaría no cuentan. El mensaje visible MUST nombrar el archivo y el campo.

#### Scenario: Resumen añadido a mano
- **WHEN** una línea del catálogo del mapa contiene `abstract`
- **THEN** `factory doctor` falla con una comprobación crítica que nombra el campo y la línea

#### Scenario: Texto pegado en un valor permitido
- **WHEN** una keyword o un autor del mapa contienen una frase que no cumple su formato, o se añade texto a `llms.txt`
- **THEN** `factory doctor` falla con una comprobación crítica y su salida nombra el archivo y el campo

#### Scenario: Clave repetida
- **WHEN** una línea del catálogo repite una clave para esconder un párrafo en el primer valor
- **THEN** `factory doctor` falla aunque, al interpretarla, la línea parezca válida

#### Scenario: Archivos del sistema en el mapa
- **WHEN** el sistema operativo o Obsidian crean `.DS_Store` u `.obsidian/` dentro del mapa
- **THEN** la comprobación pasa y `git status` no muestra esos archivos

#### Scenario: Mapa válido
- **WHEN** el mapa es el que generó factory
- **THEN** la comprobación del mapa pasa

### Requirement: El mapa sustituye al principal ausente
Si el cerebro principal no está importado y el mapa existe, la búsqueda, la inyección y el intake SHALL usar el catálogo del mapa. Si el principal está importado, el mapa MUST ignorarse. Las notas del mapa MUST aparecer solo como cita y ruta, y la salida MUST indicar que el texto no está en este equipo y cómo importarlo.

#### Scenario: Clon nuevo sin libros
- **WHEN** en un clon sin `brain-principal/` se busca "rate limiting"
- **THEN** se listan citas de los libros con su capítulo y páginas, y la salida indica que el texto no está disponible y sugiere `factory brain import`

#### Scenario: Búsqueda JSON en un clon sin libros
- **WHEN** en un clon sin `brain-principal/` se busca con `--json`
- **THEN** la salida estándar es JSON válido y el aviso va a la salida de errores

#### Scenario: Inyección solo con el mapa
- **WHEN** un objetivo con `knowledge.queries` se ejecuta en un clon sin el principal
- **THEN** el prompt del maker cita las notas encontradas sin texto completo de ningún libro

#### Scenario: Principal y mapa presentes
- **WHEN** el principal está importado y el mapa existe
- **THEN** cada nota aparece una sola vez en los resultados, con su texto disponible

### Requirement: Protección del mapa frente a los loops
La ruta del mapa SHALL ser ruta prohibida en todo objetivo, con denegaciones de edición y escritura en cada invocación. Su huella MUST compararse al inicio y al final de cada ejecución, con aviso si cambia.

#### Scenario: El maker edita el mapa
- **WHEN** una ronda modifica un archivo del mapa en el worktree
- **THEN** la ronda se revierte por violación de alcance y la retroalimentación nombra el archivo

#### Scenario: Cambio en el mapa durante una ejecución
- **WHEN** el mapa del checkout principal cambia durante una ejecución
- **THEN** `decision.md` y la bandeja incluyen un aviso de integridad del mapa
