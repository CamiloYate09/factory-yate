---
id: en-repos-con-pyproject-toml-factory
objective: En repos con pyproject.toml, `factory init` genera un init.sh que crea
  (si no existe) un entorno virtual .venv del proyecto, instala con `-e .` dentro
  de él y ejecuta check.sh usando ese entorno. Los init.sh generados para Makefile
  y package.json no cambian, y un test nuevo con 'venv' en el nombre lo cubre.
mode: finite
status: draft
request: 20261028-051056-cuando-factory-init-se-aplica-bb12
risk: medium
surfaces:
- harness
acceptance:
- name: tests nuevos del venv en init
  run: python -m pytest -q tests/test_init.py -k venv
- name: tests de la feature harness-scaffolding
  run: python -m pytest -q tests/test_templates.py tests/test_init.py tests/test_scaffold_integration.py
- name: verificación completa
  run: ./scripts/check.sh
scope:
  allow:
  - src/factory/scaffold.py
  - src/factory/templates/init.sh
  - tests/test_init.py
  deny:
  - pyproject.toml
  - scripts/**
  - init.sh
  protected:
  - init.sh
  - scripts/check.sh
  - pyproject.toml
  - feature_list.json
  - openspec/specs/**
  - tests/conftest.py
  allow_modify:
  - tests/test_init.py
---

## Contexto

Contexto: `detect()` (src/factory/scaffold.py:68-74) devuelve `install='python3 -m pip install -e .'` para pyproject.toml, e `init_harness` lo sustituye en `{{INSTALL}}` de src/factory/templates/init.sh. El init.sh raíz de este repo sirve de referencia: usa uv si existe y, si no, `python3 -m venv .venv` + `.venv/bin/python -m pip install -e ...`.

Pasos sugeridos:
1) Para pyproject.toml, generar un bloque de instalación de varias líneas: `[ -d .venv ] || python3 -m venv .venv` (o `uv venv` si `command -v uv`), luego `.venv/bin/python -m pip install -e .`.
2) Asegurar que check.sh se ejecuta dentro del venv, por ejemplo con `export VIRTUAL_ENV="$PWD/.venv"; export PATH="$VIRTUAL_ENV/bin:$PATH"` antes del `exec ./scripts/check.sh`. Así `python3 -m pytest` resuelve al venv sin tocar los comandos de verificación detectados.
3) No cambiar las cadenas de instalación de Makefile (`make setup`) ni de package.json (`npm install`), ni el placeholder cuando no hay detección.
4) Tests nuevos en tests/test_init.py con 'venv' en el nombre: (a) con pyproject.toml, el init.sh generado contiene `.venv` y no contiene `python3 -m pip install -e .` fuera del venv; (b) con Makefile y con package.json, el init.sh generado no menciona `.venv` y conserva `make setup` / `npm install`. Comprobar solo el texto generado, sin ejecutar el init.sh de pyproject (evita pip y la red). Si se quiere, validar la sintaxis con `bash -n init.sh`.
5) Ninguna aserción existente debería necesitar cambios. No debilitar tests.

## Origen

Borrador generado por `factory intake` a partir de la petición `20261028-051056-cuando-factory-init-se-aplica-bb12`. Revisa los comandos de `acceptance` antes de promoverlo con `factory goal promote <este archivo> --yes`.

## Fuera de alcance

- Instalar extras de desarrollo ('.[dev]') o detectar grupos opcionales del pyproject.toml destino
- Cambiar los comandos de verificación detectados (python3 -m pytest / ruff) o el check.sh generado
- Documentar el requisito en openspec/specs/harness-scaffolding mediante un cambio OpenSpec
