# Proposal

## Why

factory-yate ya tiene harness, motor de loops y cerebros, pero en las sesiones interactivas solo hay dos papeles: quien construye (la sesión principal) y un único revisor genérico (el subagente `checker`). Un solo revisor generalista no cubre con la misma profundidad la seguridad, la calidad de los tests, la complejidad del código, la documentación, el encaje con la petición de producto y la revisión de ramas ajenas. Además, nadie decide de forma explícita **qué** revisiones merece cada cambio: o se piden todas a mano o no se pide ninguna.

Queremos un **equipo ideal** de sub-agentes con forma de equipo de fútbol: un **técnico** que entiende el contexto y decide la convocatoria, y hasta **11 jugadores** especialistas. Cada uno tiene un puesto, un tipo (construye o revisa) y unas reglas de convocatoria declaradas. Siete puestos se cubren ahora y cuatro quedan vacantes para fichajes futuros.

## What Changes

**Plantilla declarada en los propios agentes**
- Cada jugador es un subagente de Claude Code en `.claude/agents/<nombre>.md`. Su frontmatter lleva tres claves extra: `dorsal` (1–11, que fija la posición en un 4-3-3), `tipo` (`revisor`, `constructor` o `tecnico`) y `convocatoria` (globs de rutas más los tokens `siempre` y `peticion`).
- No hay archivo central: añadir o quitar un jugador es añadir o quitar su archivo.
- Los revisores son de solo lectura (`Read, Grep, Glob`). El `checker` sigue igual y actúa como **árbitro**: fuera de la plantilla e independiente.

**`factory team`**
- `factory team list` muestra la formación, el técnico y las vacantes.
- `factory team validate` comprueba el contrato del frontmatter: dorsales únicos, tipos válidos, revisores de solo lectura y un solo técnico.
- `factory team lineup` sugiere de forma determinista la convocatoria a partir de las rutas cambiadas (`--base`, `--paths`) y de si hay una petición de producto, con el motivo de cada jugador.
- `factory doctor` incluye la validación de la plantilla.

**`factory complexity`**
- Mide la complejidad ciclomática de funciones Python con `ast`, sin dependencias. Muestra rangos A–F y, con `--base`, el delta frente a una referencia. Con `--max N` termina en 1 si alguna función del alcance supera el umbral.

**Plantilla inicial (7 jugadores + técnico)**
- Técnico `tecnico` y reglamento del partido en la skill `/equipo`: convocatoria, pre-partido, construcción, verificación determinista, revisión en paralelo, documentación y acta.
- #1 `seguridad` (portero), basado en `cloudflare/security-audit-skill` (MIT), que se copia literal en `.claude/skills/security-audit/`.
- #2 `qa`, #3 `documentador`, #4 `revisor-pr`, #5 `metricas`, #6 `producto` (preguntas y respuestas frente a la petición) y #9 `ingeniero-software`.
- Vacantes 7, 8, 10 y 11, con perfiles sugeridos documentados.

**Protección**
- `.claude/agents/**` y `.claude/skills/**` pasan a ser archivos críticos del harness: ningún maker de un loop puede reescribir el equipo.

**Fuera de alcance**
- Ejecutar el equipo dentro de `factory goal run` o `factory tick` (jugadores como checkers adicionales del motor). Será un cambio posterior.
- Fichar los puestos vacantes.
- Incluir el equipo en las plantillas de `factory init`.
- Añadir `factory complexity` o los validadores de Node de la skill de seguridad a `scripts/check.sh`.
- El modo de auditoría completa de la skill de seguridad dentro del jugador `seguridad`, que es de solo lectura.

## Capabilities

### New Capabilities
- `team-roster`: plantilla declarada en el frontmatter de los agentes, validación, formación con vacantes y convocatoria determinista (`factory team`).
- `team-match`: el técnico y el reglamento del partido, el contrato de entrada y salida de cada jugador, el formato común de los revisores y la relación con el árbitro.
- `complexity-metrics`: medición de la complejidad ciclomática, delta frente a una referencia y umbral (`factory complexity`).

### Modified Capabilities
- `goal-loop`: se añade el requisito "Definiciones del equipo protegidas". Solo requisitos `ADDED`; no cambia ningún requisito existente.

## Impact

- **Código:** paquete nuevo `src/factory/team/`, módulo `src/factory/complexity.py`, subcomandos `team` y `complexity` en `cli.py`, una comprobación en `doctor.py` y dos rutas críticas en `protection.py`.
- **Archivos:**
  - `.claude/agents/`: 8 agentes nuevos;
  - `.claude/skills/equipo/` y `.claude/skills/security-audit/`, este último copiado literal con su `LICENSE`;
  - `docs/harness/equipo.md` y enlaces en `AGENTS.md`, `CLAUDE.md`, `README.md` y `roles.md`.
- **Dependencias:** ninguna (pyyaml ya lo es).
- **Coste:** los subcomandos no tienen coste. Usar el equipo cuesta una invocación de subagente por jugador convocado; por eso existe la convocatoria.
- **Licencias:** `security-audit-skill` es MIT (Copyright (c) 2025-2026 Cloudflare, Inc.). Se conserva su `LICENSE` junto a la copia y se cita el commit de origen.
