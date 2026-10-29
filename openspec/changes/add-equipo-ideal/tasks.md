# Tasks

> Del grupo 2 al 8, cada grupo es una feature de `feature_list.json` y una unidad de trabajo independiente. Las unidades se implementan en paralelo, cada una en su propio worktree y su propia rama local (sin push ni PR), y respetan el contrato D1–D9 de `design.md`.
>
> Dentro de una unidad no se ejecutan `factory features start|verify`, no se edita `progress.md` y no se invoca al `checker`. Tras integrar las ramas, el coordinador inicia y verifica cada feature una por una (WIP=1).

## 1. Preparación

- [x] 1.1 Crear el cambio `add-equipo-ideal` con `proposal.md`, `design.md` (D1–D9), las specs delta (`team-roster`, `team-match`, `complexity-metrics` y `goal-loop`) y este `tasks.md`. Verificar con `openspec validate add-equipo-ideal --strict`.
- [x] 1.2 Añadir a `feature_list.json` las features `team-roster`, `complexity-metrics`, `team-security`, `team-coach`, `team-builders`, `team-reviewers` y `team-integration`, en `not_started` y con sus comandos `pytest`. Crear el esbozo de `docs/harness/equipo.md` y su enlace en `AGENTS.md`. Añadir `.claude/worktrees/` a `.gitignore`. Verificar que `factory features validate` y `./scripts/check.sh` pasan.

## 2. Plantilla y convocatoria (`team-roster`)

- [ ] 2.1 Implementar `src/factory/team/` (`TeamError`, lectura del frontmatter de `.claude/agents/*.md` y validación D1/D8). Verificar con `pytest tests/test_team_roster.py`, escenarios "Jugador declarado", "Agente ajeno al equipo", "Posición del dorsal 2", "Plantilla válida", "Sin equipo", "Dorsal repetido", "Dorsal fuera de rango", "Revisor con permisos de escritura" y "Técnico que edita".
- [ ] 2.2 Implementar `factory team list [--json]` y `factory team validate [--json]`, con un handler que capture `TeamError` e importe dentro de la función. Verificar con `pytest tests/test_team_roster.py`, escenario "Plantilla incompleta".
- [ ] 2.3 Implementar la convocatoria (`factory team lineup [--base] [--paths] [--peticion | --peticion-file] [--json]`), reutilizando `factory.globs.matches`. Verificar con `pytest tests/test_team_lineup.py`, escenarios "Rutas desde git" (repo git temporal), "Cambio solo en documentación", "Petición de producto sin cambios" y "Nada que jugar".
- [ ] 2.4 Añadir a `doctor` la comprobación crítica `team-roster` (subsistema `instrucciones`). Verificar con `pytest tests/test_team_roster.py tests/test_doctor.py tests/test_scaffold_integration.py`, escenario "Plantilla rota en el doctor".

## 3. Complejidad ciclomática (`complexity-metrics`)

- [ ] 3.1 Implementar `src/factory/complexity.py` (D6). Verificar con `pytest tests/test_complexity.py`, escenarios "Función lineal", "Ramas y operadores lógicos", "Rango de una función lineal", "Método de una clase" y "Función anidada", más casos de `match`, comprensiones, `try/except` y lambdas.
- [ ] 3.2 Implementar `factory complexity [RUTAS…] [--base REF] [--max N] [--json]`, con un handler que capture `ComplexityError`. Verificar con `pytest tests/test_complexity.py`, escenarios "Directorio indicado", "Archivo con error de sintaxis", "Función empeorada", "Función nueva", "Umbral superado" y "Deuda previa sin empeorar".
- [ ] 3.3 Crear el jugador `.claude/agents/metricas.md` (#5, revisor). Verificar con `pytest tests/test_team_metricas.py` (contrato D2/D8, secciones obligatorias y regla del escenario "Función empeorada hasta D") y con una prueba real en haiku (≤ 0,05 USD).

## 4. Seguridad (`team-security`)

- [ ] 4.1 Copiar literal `skills/security-audit/` de `cloudflare/security-audit-skill` @ `c1c8a8c` en `.claude/skills/security-audit/`, junto con su `LICENSE` y un `UPSTREAM.md` (repositorio, commit, fecha y política de resincronización). Verificar con `pytest tests/test_team_seguridad.py`: los archivos coinciden byte a byte con la lista esperada y la licencia está presente.
- [ ] 4.2 Crear el jugador `.claude/agents/seguridad.md` (#1, revisor) con D5. Verificar con `pytest tests/test_team_seguridad.py`, escenarios "Sin artefactos de auditoría", "Inyección de comandos probada desde el código" y "Sospecha sin traza completa" (contrato del prompt), y con una prueba real en haiku (≤ 0,05 USD) sobre un diff con `shell=True`.

## 5. Técnico (`team-coach`)

- [x] 5.1 Escribir el reglamento del partido en `.claude/skills/equipo/SKILL.md` (D4: convocatoria, fases, partido de revisión, acta, límite de 3 vueltas y árbitro). Verificar con `pytest tests/test_team_tecnico.py`, escenarios "Convocatoria parcial justificada", "El técnico amplía la sugerencia", "Pregunta abierta antes de construir", "Informe de complejidad para métricas", "Revisión de una rama de un loop", "Acta con un hallazgo medio" y "Acta en verde antes de terminar la feature" (contrato del reglamento).
- [x] 5.2 Crear `.claude/agents/tecnico.md` (`tipo: tecnico`, sin `dorsal`). Verificar con `pytest tests/test_team_tecnico.py`, escenario "Técnico sin escritura", y con una prueba real en haiku (≤ 0,05 USD) limitada a la fase de convocatoria.
- [x] 5.3 Completar `docs/harness/equipo.md`: plantilla, formación, vacantes con perfiles sugeridos, cómo fichar, árbitro y costes.

## 6. Constructores (`team-builders`)

- [ ] 6.1 Crear `.claude/agents/ingeniero-software.md` (#9, constructor). Verificar con `pytest tests/test_team_constructores.py`.
- [ ] 6.2 Crear `.claude/agents/documentador.md` (#3, constructor; solo `*.md`). Verificar con `pytest tests/test_team_constructores.py`, escenario "El documentador no toca código", y con una prueba real en haiku (≤ 0,05 USD).

## 7. Revisores (`team-reviewers`)

- [ ] 7.1 Crear `.claude/agents/qa.md` (#2), `producto.md` (#6) y `revisor-pr.md` (#4), todos revisores de solo lectura con el formato D3. Verificar con `pytest tests/test_team_revisores.py`, escenarios "Revisión sin efectos", "Cabecera del jugador" y "Hallazgo sin evidencia" (contrato del prompt).
- [ ] 7.2 Hacer una prueba real en haiku (≤ 0,05 USD) de uno de los tres revisores, comprobando que `git status --porcelain` no cambia.

## 8. Integración (`team-integration`)

- [ ] 8.1 Añadir `.claude/agents/**` y `.claude/skills/**` a `STATIC_CRITICAL`, y sus muestras a `CRITICAL_SAMPLES` (D7). Verificar con `pytest tests/test_protected_config.py tests/test_protected_paths.py`, escenarios "El maker edita un agente del equipo" y "Un objetivo intenta liberar las skills".
- [ ] 8.2 Documentar el equipo:
  - `AGENTS.md`: comandos `factory team` y `factory complexity`;
  - `CLAUDE.md`: `/equipo` y el árbitro;
  - `README.md`: paso H;
  - `docs/harness/roles.md`: árbitro frente a equipo.

  Verificar con `./scripts/check.sh` (doctor sin fallos).

## 9. Integración y validación

- [ ] 9.1 Integrar las ramas de las unidades en `main` (decisión humana) y ejecutar `./scripts/check.sh`, `factory team validate`, `factory team list` y `openspec validate add-equipo-ideal --strict`.
- [ ] 9.2 Ejecutar `factory features start|verify` de las 7 features, una a una.
- [ ] 9.3 Pedir la revisión independiente del `checker` sobre el diff conjunto y corregir los hallazgos `critical` y `medium`.
- [ ] 9.4 Hacer un partido real con `/equipo` sobre un cambio pequeño, con un tope de coste acordado con el humano, y registrarlo en `progress.md`.

## Workflow follow-up

- Archivar con `/opsx:archive add-equipo-ideal`.
- Cambios posteriores posibles:
  - el equipo dentro de `factory goal run` (jugadores convocados como checkers adicionales);
  - fichajes para los dorsales 7, 8, 10 y 11;
  - el equipo en las plantillas de `factory init`.
