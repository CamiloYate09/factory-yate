---
id: 2026/10/2026-10-29-macos-no-tiene-timeout
type: gotcha
title: macOS no tiene timeout
date: '2026-10-29'
tags:
- macos
- shell
keywords:
- macos
- timeout
- codigo
- comando
- coreutils
- ejemplo
- gnu
- gtimeout
abstract: 'macOS no trae el comando timeout de GNU: un script que lo use termina con
  código 127.'
source: manual
tokens: 53
---

# macOS no tiene timeout

> Cerebro diario · gotcha · 2026-10-29 · manual

macOS no trae el comando timeout de GNU: un script que lo use termina con código 127. Usa el límite de tiempo de la propia herramienta (por ejemplo timeout_s en subprocess) o instala coreutils y llama a gtimeout.
