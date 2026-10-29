# Spec Delta

## MODIFIED Requirements

### Requirement: Búsqueda en los cerebros
`factory brain search "<consulta>"` SHALL buscar por palabras clave en los catálogos del cerebro principal y del diario, sin servicios externos. Si el principal no está importado, MUST usar en su lugar el catálogo del mapa de la biblioteca. Cada resultado MUST incluir la ruta de la nota, su título, una cita (libro, capítulo y páginas, o fecha y origen para el diario) y sus tokens. `--brain`, `--limit` y `--json` acotan la búsqueda y la salida.

#### Scenario: Consulta con resultados
- **WHEN** se busca "rate limiting" con el cerebro principal importado
- **THEN** se listan las notas más relevantes con su ruta, título, cita del libro y capítulo con páginas, y tokens, ordenadas por relevancia

#### Scenario: Consulta sin resultados
- **WHEN** ninguna nota coincide con la consulta
- **THEN** el comando informa que no hay resultados, sugiere usar términos en inglés para el cerebro principal y termina con código cero

#### Scenario: Cerebro no configurado o vacío
- **WHEN** se busca sin haber importado el cerebro principal y sin mapa de la biblioteca
- **THEN** la búsqueda usa solo el cerebro diario e indica que el principal no está disponible y cómo importarlo

#### Scenario: Solo el mapa disponible
- **WHEN** se busca sin haber importado el cerebro principal, pero con el mapa de la biblioteca en el repo
- **THEN** los resultados del principal salen del mapa, con su cita, y la salida indica que el texto no está en este equipo y cómo importarlo
