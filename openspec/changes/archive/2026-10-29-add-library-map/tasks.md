# Tasks

## 1. Mapa de la biblioteca

- [x] 1.1 Añadir `[brain] map_dir` (por defecto `brain-mapa`) y `Config.map_path`. Implementar `brain/libmap.py` con las listas blancas, la normalización, el recorte a 20 palabras y `build_map` determinista, que escribe solo lo que cambia (D1–D3). Verificar con `pytest tests/test_brain_map.py`, escenarios "Importación con mapa", "Reimportación sin cambios", "Catálogo con resúmenes" y "Encabezado sospechoso".
- [x] 1.2 Generar el mapa al final de `factory brain import` y mostrarlo en la salida y en `factory brain status`.
- [x] 1.3 Comprobación crítica `brain-map-sin-texto` en `doctor`. Verificar con `pytest tests/test_brain_map.py tests/test_doctor.py`, escenarios "Resumen añadido a mano" y "Mapa válido".

## 2. Recuperación con el mapa

- [x] 2.1 Origen del principal: el catálogo del principal si existe y, si no, el del mapa, con las rutas apuntando a `brain-principal/` (D4).
  - `render` marca las notas sin texto en este equipo.
  - `search` y `status` indican el modo "solo mapa".
  - `catalog_paths` incluye el mapa.

  Verificar con `pytest tests/test_brain_map.py tests/test_brain_search.py`, escenarios "Clon nuevo sin libros", "Solo el mapa disponible", "Inyección solo con el mapa" y "Principal y mapa presentes".

## 3. Protección y commit

- [x] 3.1 Añadir el mapa a `_forced_deny()` y a los cerebros del motor (denegaciones, `--add-dir` y huella). Verificar con `pytest tests/test_brain_map.py`, escenario "El maker edita el mapa".
- [x] 3.2 Hacer que `factory brain commit`, `uncommitted()`, `status` y `land` cubran el mapa (D6). Verificar con `pytest tests/test_brain_daily.py`, escenario "Mapa regenerado por una importación".

## 4. Documentación, datos reales y validación

- [x] 4.1 Documentar en `docs/harness/cerebros.md` (tabla, mapa y fichas propias) y en el README, paso G: qué trae un clon, cómo importar tu copia y por qué los libros no se versionan. Sembrar unas pocas notas del diario con aprendizajes de `progress.md` (D7).
- [x] 4.2 Regenerar el mapa desde el vault real (sin coste de API). Comprobar:
  - `factory doctor` pasa;
  - ninguna frase de un `abstract` ni de una nota real aparece en `brain-mapa/`;
  - el tamaño es de unos 5,5 MB;
  - un clon temporal sin `brain-principal/` encuentra "rate limiting" con citas.

  Verificar también que `./scripts/check.sh` termina en 0 y que `openspec validate add-library-map --strict` pasa, y registrar la evidencia en `progress.md`.
