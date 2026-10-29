# Proposal

## Why

El cerebro principal (82 libros, 11.245 notas) contiene el texto completo de libros comerciales, así que nunca se versiona. Por eso, quien clona el repo hoy no recibe ninguna base de conocimiento: `factory brain search` no encuentra nada del principal hasta que alguien importa su propia copia del vault.

El dueño quiere que cada clon traiga ya una base útil. A la vez, el texto de los libros no debe salir de sus equipos: lo moverá él a mano entre computadores.

## What Changes

- **Mapa de la biblioteca versionado** (nuevo, por defecto `brain-mapa/`):
  - cada `factory brain import` lo regenera a partir del catálogo del principal;
  - solo contiene metadatos de una lista blanca, con formatos estrictos: ruta, libro, tipo, título, capítulo, sección, páginas, tokens y keywords de cada nota, y título, autores, dominios y cifras de cada libro;
  - **ningún texto de los libros**: ni `abstract`, ni cuerpos, ni las guías del vault;
  - la salida es determinista, así que reimportar el mismo vault no produce diff.
- **Búsqueda con el mapa.** Sin el principal importado, `factory brain search` y la inyección usan el mapa:
  - devuelven citas (*Libro* · cap. N · pp. A–B) y avisan de que el texto no está en este equipo y de cómo importarlo;
  - la inyección deja esas notas solo como referencia;
  - con el principal importado, el mapa se ignora, para no duplicar resultados.
- **Salvaguardas:**
  - `factory doctor` falla (comprobación crítica) si el mapa contiene un campo fuera de la lista blanca o una nota `.md`;
  - el mapa es ruta prohibida en todo objetivo y queda en solo lectura, con huella, igual que los cerebros.
- **Commit explícito.** `factory brain commit` incluye el mapa junto al cerebro diario. `factory status` y `factory land` avisan si tiene cambios sin commitear.
- **Conocimiento propio compartible.** La documentación explica que el cerebro diario viaja con el repo y es el sitio para las fichas escritas con tus palabras.

## Capabilities

### New Capabilities
- `library-map`: mapa versionado de la biblioteca, sin texto de los libros. Cubre su generación, la lista blanca, la comprobación de `doctor`, la protección frente a los loops y su uso cuando no hay principal.

### Modified Capabilities
- `brain-retrieval`: "Búsqueda en los cerebros". Sin el principal importado, la búsqueda usa el mapa en lugar de quedarse solo con el diario.
- `daily-brain`: "Commit explícito del cerebro diario". `factory brain commit` también commitea el mapa.

## Impact

- **Código nuevo:** `src/factory/brain/libmap.py`.
- **Código modificado:** `config.py` (`[brain] map_dir`), `brain/importer.py`, `brain/catalog.py`, `brain/search.py`, `brain/inject.py`, `brain/daily.py` (commit), `doctor.py`, `engine.py` (prohibición, denegaciones y huella), `intake.py`, `status.py`, `land.py` y `cli.py`.
- **Documentación:** `docs/harness/cerebros.md` y README, paso G.
- **Datos:** `brain-mapa/` versionado, de unos 5,5 MB, generado desde el vault real.
