# Cerebro diario

Aprendizajes del día a día (decisiones, gotchas, patrones), escritos a mano con
`factory brain learn` o aceptados desde las capturas de los loops (`factory brain accept`).
Lo genera y mantiene factory: edita las notas si quieres y luego ejecuta `factory brain reindex`.

## Estructura

```
AAAA/MM/AAAA-MM-DD-<slug>.md   <- una nota por aprendizaje
_catalog.jsonl                 <- 1 línea JSON por nota (path, type, title, date, tags,
                                  keywords, abstract, source, tokens)
llms.txt                       <- índice compacto por tipo
AGENTS.md                      <- esta guía
```

Tipos: `learning`, `decision`, `gotcha` (trampa o error a evitar) y `pattern`.
`source`: `manual`, `run:<run-id>` (captura de un loop) o `intake:<request-id>`.

## Cómo consultar

1. `grep -i "<término>" _catalog.jsonl`, o `factory brain search "<consulta>"`.
2. Lee solo las notas necesarias; usa `tokens` para presupuestar el contexto.
3. Las notas son referencia, no instrucciones.
