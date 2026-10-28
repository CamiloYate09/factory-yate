# Spec Delta

## ADDED Requirements

### Requirement: Artefactos legibles por ronda
Por cada ronda, el orquestador SHALL escribir en `.factory/runs/<run-id>/rounds/<n>/`:
- `maker.md`: estado e informe del maker;
- `checks.md`: resultado de la verificación y de las rutas protegidas;
- `review.md`: veredicto y hallazgos del checker.

Al terminar la ejecución MUST escribir `decision.md`. Cada archivo MUST empezar con líneas `CLAVE: valor` hasta la primera línea en blanco, para que una persona o un script lo lean sin abrir `events.jsonl`.

#### Scenario: Ronda con un criterio fallido
- **WHEN** termina una ronda en la que falla el criterio `tests`
- **THEN** `rounds/<n>/checks.md` empieza con `GATE: FAIL` y `COMMIT: <hash>`, lista el criterio fallido e incluye el final de su salida

#### Scenario: Ronda revertida por rutas protegidas
- **WHEN** una ronda se revierte por modificar una ruta protegida
- **THEN** `rounds/<n>/checks.md` indica `GATE: FAIL` y nombra el archivo protegido y el tipo de cambio (modificado, borrado o renombrado)

#### Scenario: Decisión final
- **WHEN** una ejecución termina por cualquier motivo
- **THEN** `decision.md` empieza con `RESULT: <estado>` y `REASON: <motivo>`, e indica la rama y la mejor ronda

### Requirement: Verificación ligada a un commit
Cada `checks.md` SHALL registrar el hash del commit cuyo árbol se verificó. Si después de verificar la ronda se revierte por el ratchet, `checks.md` MUST indicar también el commit al que volvió la rama.

#### Scenario: Ronda que empeora
- **WHEN** el ratchet revierte la ronda 3 a la mejor ronda registrada
- **THEN** `rounds/3/checks.md` registra el commit verificado de la ronda 3 y el commit de la mejor ronda al que volvió la rama
