# Origen de la copia

Este directorio es una **copia literal** de `skills/security-audit/` del repositorio upstream, más el `LICENSE` de su raíz.

| Dato | Valor |
|---|---|
| Repositorio | https://github.com/cloudflare/security-audit-skill |
| Commit | `c1c8a8c1471069fb0e188eeaff69b8e8db6564a8` |
| Ruta de origen | `skills/security-audit/` (y `LICENSE` de la raíz) |
| Fecha de copia | 2026-10-28 |
| Licencia | MIT, Copyright (c) 2025-2026 Cloudflare, Inc. (ver `LICENSE`) |

## Política

- **La copia es literal y no se edita.** Ningún archivo de este directorio, salvo este `UPSTREAM.md`, se modifica a mano; tampoco `SKILL.md`.
- **Las adaptaciones van en `.claude/agents/seguridad.md`.** Ahí se fijan el modo guía sobre el diff, el listón de prueba "no ejecutado", el mapeo de severidad, la sección `needs_validation` y la checklist de este repositorio (decisión D5 de `openspec/changes/archive/2026-10-30-add-equipo-ideal/design.md`).
- **Integridad.** `tests/test_team_seguridad.py` recalcula el sha256 de cada archivo y lo compara con la tabla de abajo. El test además fija una huella de la tabla, de modo que editar un archivo y su fila a la vez también rompe la verificación.

## Resincronizar

Resincronizar es volver a copiar, con un clon local del upstream (`<clon>`) y un directorio temporal vacío (`<tmp>`):

1. Extraer la carpeta del nuevo commit: `git -C <clon> archive <commit> skills/security-audit | tar -x -C <tmp>`.
2. Borrar de este directorio todo salvo `UPSTREAM.md`, y copiar en él el contenido de `<tmp>/skills/security-audit/`.
3. Copiar la licencia de la raíz: `git -C <clon> show <commit>:LICENSE > LICENSE`.
4. Actualizar en este archivo el commit, la fecha y la tabla de sha256.
5. Actualizar en `tests/test_team_seguridad.py` estas constantes:
   - `COMMIT`;
   - `FECHA_DE_COPIA`;
   - `ARCHIVOS_COPIADOS`, si cambia el número de archivos;
   - `HUELLA_DE_LA_TABLA`: el test, al fallar, imprime la huella nueva.
6. Revisar si `.claude/agents/seguridad.md` sigue encajando con el nuevo `SKILL.md`.

## Validadores de Node

Los validadores `validate-findings.cjs` y `validate-coverage-ledger.cjs` (y sus `*.test.cjs`) necesitan Node. Solo los usa el modo de auditoría completa, que el jugador `seguridad` no ejecuta, y **no forman parte de `scripts/check.sh`**.

## sha256 de los archivos copiados

Incluye `LICENSE` y excluye este `UPSTREAM.md`.

| Archivo | sha256 |
|---|---|
| `AI-AND-LLM.md` | `7335a95c43554eadefcf03ece639291bb0e038c398a179299e3887ffe06bd2ef` |
| `ATTACK-CLASSES.md` | `3ee4f00c6e8c9dcf6dd02dd5ac2a4ceb322e2085f3e9fbe79cf0c6330bc7ef83` |
| `CLIENT-SIDE.md` | `613f6b98f86083e045525c5b60154ffdab122bac35f1e05eb17488e6e453370c` |
| `CLOUD-AND-DEPLOYMENT.md` | `3c80f3088be22345e07b057c056d6ed99fe2b0304f794398964f7ccd5a496ca3` |
| `DATA-ISOLATION-AND-LIFECYCLE.md` | `307dcb3e24d292715c4a041190e7bb135646a37eb6187619ae01d000a634a4ad` |
| `DESKTOP-MOBILE-AND-LOCAL-IPC.md` | `58eae8ee0ca6a46611c501ec5a3ab47fdff88dd7db0d8d74789bbf8bb19d8cb2` |
| `HUNTING.md` | `71c121decea1322c47c718f6e110f1a892980bb4266bd7ac55ef043a213ade09` |
| `LICENSE` | `e598e694aa506650c7192d5ea3be0e50aca0d356ea00551c53429f0b01eb6391` |
| `MEMORY-SAFETY-AND-BINARY.md` | `7c8b0dccfb35315cca2455509674d49632b2fe37e1f3aac16c1a496a7e9924a7` |
| `PROTOCOLS-RPC-AND-MESSAGING.md` | `8b73816fa5b3697c9c40977f0c836b40f01d6e81929ff2720fe83ce089e9a619` |
| `RECONNAISSANCE.md` | `02ca887aca84de8ae137f1891bd2f0a54f28d3fa6da92a27f54734382b3381a2` |
| `RESOURCE-EXHAUSTION-AND-AVAILABILITY.md` | `4326fab5c92a0b4c420a70196254040105cd794026562130b59bf1a6db3e4baa` |
| `SKILL.md` | `5e3e96a1e438d8f35fef0a1e38f02d4f00e2bdf910401b7dfe00e6779c6dac85` |
| `SUPPLY-CHAIN-AND-RELEASE.md` | `f372e919940e335468ba1ae09f99026c3986a345f7fe26f8068f132e199f52a5` |
| `VALIDATION-AND-REPORTING.md` | `b892470cb89bb31f33403e050d4bdfbe2cdaef940ade1496fa65e32b2e129449` |
| `WEB-PROTOCOL-AND-AUTH.md` | `4f3066dffa23c5635859187be9b96c32f2aff29a688186b91ff0c63e47d62b5c` |
| `report-schema.json` | `6575c9de4a62255699ea052ebf9a49ebfb373a32891bcd89af6f55cc84b35519` |
| `validate-coverage-ledger.cjs` | `2eb280bd2e33c002916f86db9b29f9edfedb6454e5db973c766290465b868ac8` |
| `validate-coverage-ledger.test.cjs` | `cfb9df26b03469a4279a70e7664a2a5434dd6f8c2c204e91f9b0aeb9dd71e648` |
| `validate-findings.cjs` | `e85f232e36bfac0f866f244da50376692d6b45c690beadcb00608b0e6c8b5283` |
| `validate-findings.test.cjs` | `b92001117a92c4161d43777a0ba2fa182a8a4d97f2304cc8c0cee5331497b73b` |
