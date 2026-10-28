# Verificación

El subsistema de retroalimentación es el de mayor retorno del harness (L02). "Se ve bien" no cuenta; un comando que termina en 0 sí (L07).

## La ruta única: `./scripts/check.sh`

Se ejecuta sin interacción y se detiene en el primer fallo. Pasos, en orden:

| Paso | Comando | Qué detecta |
|---|---|---|
| `lint` | `python -m ruff check .` | errores, imports, estilo, bugs comunes |
| `formato` | `python -m ruff format --check .` | código Python sin formatear (los `.md` se excluyen) |
| `tests` | `python -m pytest -q` | comportamiento: unidades e integración |
| `harness` | `python -m factory doctor` | harness roto: features sin evidencia, WIP>1, enlaces rotos… |

Usa el intérprete de `.venv` si existe y, si no, `python3` (o `$PYTHON`). Termina en 0 solo si todo pasa.

## Cómo leer un fallo

Un fallo termina así:

```
FALLO en la comprobación 'tests'.
Reproducir con: .venv/bin/python -m pytest -q
```

1. Ejecuta el comando de "Reproducir con" para ver el error completo.
2. Para aislar el fallo, ejecuta solo lo afectado, por ejemplo `.venv/bin/python -m pytest -q tests/test_features.py -k wip`.
3. Si `ruff format` falla, `.venv/bin/ruff format src tests` lo corrige.
4. Si `ruff check` falla, `.venv/bin/ruff check --fix src tests` arregla lo automático; el resto se corrige a mano.
5. Si `factory doctor` falla, cada `[FAIL]` trae debajo una línea `→` con la acción concreta.

## Tres capas (L09)

Pasar los tests unitarios no significa haber terminado la tarea. La verificación avanza por capas:

1. **Sintaxis y estilo**: `ruff`. Es barata, y se corrige primero.
2. **Comportamiento**: `pytest`. Cada escenario de las specs (`openspec/changes/*/specs/`) tiene al menos un test con nombre reconocible.
3. **Sistema**: tests de integración sobre repos git temporales (`conftest.py`: `init_git_repo`, `make_harness`), el loop completo con el agente simulado (`FakeRunner`) y `factory doctor` sobre este repo.

Hay una capa adicional opcional que llama a `claude -p` de verdad: `pytest -m live`. Está excluida por defecto porque **cuesta dinero** y solo se ejecuta con aprobación humana.

## Reglas

- **No debilites tests** para que algo pase: borrarlos, añadir `skip`, relajar aserciones o capturar excepciones para ocultarlas. Si un test está mal, documenta por qué en `progress.md` y pide revisión.
- **No cambies `scripts/check.sh`** ni la configuración de ruff/pytest en `pyproject.toml` sin una petición explícita. Cambiar la regla de verificación durante una implementación invalida la evidencia.
- **Escribe mensajes de error pensados para el agente**: qué falló, dónde y cómo arreglarlo (L10). `factory doctor` sigue este estilo, con una acción por comprobación.
- **Promueve el feedback a defensa permanente**: cuando una revisión detecta un tipo de defecto nuevo, añade un test o una comprobación de `doctor` que lo capture la próxima vez (L10).

## Evidencia

La evidencia de una feature son comandos ejecutados con su resultado, no frases. `factory features verify <id>` ejecuta los comandos de verificación de la feature y, si todos pasan, registra para cada uno:

```json
{"command": "python -m pytest -q tests/test_x.py", "exit_code": 0, "date": "2026-10-27T12:00:00+00:00", "commit": "abc123…"}
```

Si todavía no hay commits, el campo `commit` vale `sin-commit`. Ver [features.md](features.md).

## Añadir una comprobación nueva

1. Pide confirmación humana: cambia la definición de "verde".
2. Añade un paso `run_step <nombre> <comando>` en `scripts/check.sh`.
3. Ejecuta `./scripts/check.sh` y regístralo en `progress.md`.

---
Adaptado de walkinglabs/learn-harness-engineering (MIT), lecciones 02, 07, 09 y 10.
