# Design

## Context

Ver proposal.md (Why). Ya existe (specs `main-brain`, `daily-brain` y `brain-retrieval`):

- `factory brain import` copia el vault a `brain-principal/`, que está en `.gitignore` y tiene un check crítico en `doctor`;
- el catálogo `_catalog.jsonl` del vault trae por nota `path, book_id, type, title, chapter, chapter_title, section_path, pages, tokens, keywords, abstract`;
- `_books.json` trae además `source` (ruta del PDF) y `readme`.

Medido sobre el vault real:

- `abstract` es una frase literal del libro ("According to Gartner, CTI can be defined as…"), así que se excluye;
- los títulos y las secciones son encabezados reales: el más largo tiene 17 palabras;
- el catálogo sin `abstract` ocupa unos 5,5 MB.

## Goals / Non-Goals

**Goals:**
- Que un clon nuevo pueda buscar en la biblioteca y obtener citas.
- Que ningún texto de los libros llegue a git, con una lista blanca impuesta en código y vigilada por `doctor`.
- Una salida determinista, para que reimportar no genere diff.

**Non-Goals:**
- Resúmenes generados con modelos: cuestan dinero y producen paráfrasis cercanas al original.
- Sincronizar los libros entre equipos: lo hace su dueño a mano.
- Embeddings.

## Decisions

### D1. Ubicación y contenido
- `[brain] map_dir = "brain-mapa"`, un directorio versionado separado de `brain-principal/`.
- Contenido:
  - `_catalog.jsonl`: una línea por nota con la lista blanca, ordenada por `path`;
  - `_books.json`: lista blanca, ordenada por `slug`;
  - `.gitignore`: `*` y luego solo sus archivos, para que `.DS_Store` u `.obsidian/` nunca se versionen ni cuenten en `doctor`;
  - `AGENTS.md` y `llms.txt`, escritos por factory (nunca se copian las guías del vault, que no están verificadas);
  - `_map.json`: huella del catálogo de origen y recuentos, sin fechas.
- La salida es JSON estable: el orden de las claves es el de la lista blanca, con `ensure_ascii=False`.

### D2. Lista blanca en código
- La lista blanca está en `brain/libmap.py`:
  - notas: `path, book_id, type, title, chapter, chapter_title, section_path, pages, tokens, keywords`;
  - libros: `slug, title, authors, domains, pages, chapters, notes, words, tokens`. Se quitó `subtitle`: en el vault real a veces trae texto de una página ("Copyright © 2022 Packt Publishing", "Head over to unique link below…").
- Cada línea se **construye** desde la lista blanca, nunca copiando la línea del catálogo y borrando claves. Los tipos se normalizan.
- `title`, `chapter_title` y cada elemento de `section_path` se recortan a 20 palabras, con margen sobre el máximo real de 17.
- **Formatos estrictos:**
  - keywords `[\w.+#/-]{1,60}` (las 89.425 reales lo cumplen), como máximo 12;
  - `book_id` y `domains` `[\w.-]{1,80}`;
  - `chapter` `[\w.-]{1,12}`;
  - `type` `[a-z_-]{1,20}`;
  - `path` termina en `.md`;
  - autores de hasta 20 palabras y 80 caracteres, sin duplicados;
  - las listas solo se aceptan como listas.
- **`doctor` reconstruye y compara el texto exacto**, no el JSON interpretado, porque una clave repetida conservaría solo el último valor:
  - cada línea del catálogo debe ser `json.dumps(map_note(línea))`;
  - `_books.json`, `_map.json` (recuentos reales y huella `[0-9a-f]{64}`), `AGENTS.md`, `llms.txt` y `.gitignore` deben ser los de factory;
  - no puede faltar ninguno.

  Lo que no cumple su formato se detecta. Una frase corta que sí lo cumple (un título de hasta 20 palabras) se acepta como encabezado; ver Risks. Solo cuentan los archivos que git versionaría (`git ls-files --cached --others --exclude-standard`).

### D3. Generación
- Al final de cada `import` correcta: `build_map(principal, map_dir)`.
- Escribe en un temporal y sustituye cada archivo solo si cambió, así que un vault igual deja el mapa idéntico byte a byte.
- Si `map_dir` está dentro del repo y git lo ignora, `import` avisa, `doctor` lo marca (recomendada) y `factory brain commit` lo omite sin bloquear el commit del diario.
- Las rutas de los tres cerebros no pueden coincidir, anidarse ni ser la raíz del repo: la configuración se rechaza.

### D4. Recuperación
- **Origen del principal:** si existe `brain-principal/_catalog.jsonl`, se usa; si no, se usa `brain-mapa/_catalog.jsonl`. Nunca los dos, para no duplicar resultados.
- **Rutas:** las entradas del mapa apuntan a `brain-principal/<path>`, donde estaría la nota si se importara.
- **Inyección:** sin texto, `note_body` devuelve vacío, `select` deja la nota como referencia y `render` añade "texto no disponible en este equipo".
- **Salida de la búsqueda:** `factory brain search` y `status` indican el modo "solo mapa" y sugieren `factory brain import <vault>`.
- **Intake:** `catalog_paths` devuelve el catálogo del mapa cuando no hay principal.
- **Coste aceptado:** el mapa no tiene `abstract`, así que pierde ese peso (×1) en la puntuación.

### D5. Protección
- El mapa entra en `_forced_deny()`, como el cerebro diario.
- Entra también en los cerebros del motor: denegaciones `Edit/Write`, `--add-dir` si existe, y huella al inicio y al final.

### D6. Commit
- `commit_daily` pasa a commitear el diario y el mapa con pathspec explícito.
- `uncommitted()` cubre los dos, y con él el aviso de `status` y la pista de `land`.

### D7. Conocimiento propio
- Para el diario no hace falta código: la documentación explica que viaja con el repo y es el sitio para fichas escritas con tus palabras.
- Se siembran unas pocas notas con aprendizajes ya registrados en `progress.md`, ninguno sacado de los libros.

## Risks / Trade-offs

- Los títulos de capítulo y de sección quedan en un repo público. Son datos de índice, como una tabla de contenidos, no prosa. El tope de 20 palabras y la comprobación de `doctor` cubren las conversiones defectuosas.
- Buscar solo en el mapa es algo menos preciso, porque no hay `abstract`. Se acepta.
- El mapa (unos 5,5 MB) se reescribe solo cuando cambia el vault.
