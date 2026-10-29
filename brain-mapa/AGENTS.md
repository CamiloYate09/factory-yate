# Mapa de la biblioteca

Índice de la biblioteca técnica del cerebro principal: qué libros, capítulos y secciones hay y
en qué páginas está cada tema. **No contiene texto de los libros**: los libros no se versionan.
Lo genera `factory brain import`; no lo edites a mano (`factory doctor` lo valida).

## Estructura

```
_catalog.jsonl  <- 1 línea JSON por nota: path, book_id, type, title, chapter, chapter_title,
                   section_path, pages, tokens, keywords
_books.json     <- libros: slug, title, authors, domains, pages, chapters, notes, words,
                   tokens
_map.json       <- huella del catálogo de origen y recuentos
llms.txt        <- índice compacto por dominio
```

## Cómo usarlo

1. `factory brain search "<consulta en inglés>"` o `grep -i "<término>" _catalog.jsonl`.
2. Cada resultado da la cita (*Libro* · cap. N · pp. A–B) para consultar tu ejemplar.
3. El texto completo solo está en el equipo que tenga su copia importada
   (`factory brain import <vault>`), en `brain-principal/<path>`.
