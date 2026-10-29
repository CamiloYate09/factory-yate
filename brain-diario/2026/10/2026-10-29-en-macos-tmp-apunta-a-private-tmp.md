---
id: 2026/10/2026-10-29-en-macos-tmp-apunta-a-private-tmp
type: gotcha
title: En macOS /tmp apunta a /private/tmp
date: '2026-10-29'
tags:
- claude-code
- macos
- rutas
keywords:
- tmp
- macos
- private
- ruta
- add-dir
- apunta
- claude
- code
abstract: En macOS /tmp es un enlace simbólico a /private/tmp.
source: manual
tokens: 68
---

# En macOS /tmp apunta a /private/tmp

> Cerebro diario · gotcha · 2026-10-29 · manual

En macOS /tmp es un enlace simbólico a /private/tmp. Si una ruta se usa para generar reglas o comparar (por ejemplo --add-dir y las denegaciones Edit(//ruta/**) de Claude Code), resuélvela siempre con Path.resolve() en todos los sitios; si no, las dos formas no coinciden.
