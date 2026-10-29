---
id: 2026/10/2026-10-29-zsh-interpreta-t-tras-una-variable
type: gotcha
title: zsh interpreta :t tras una variable
date: '2026-10-29'
tags:
- git
- shell
- zsh
keywords:
- var
- variable
- zsh
- comandos
- git
- interpreta
- llaves
- modificador
abstract: En zsh, $VAR:t es un modificador (tail) y rompe comandos como git show $RUN:ruta.
source: manual
tokens: 34
---

# zsh interpreta :t tras una variable

> Cerebro diario · gotcha · 2026-10-29 · manual

En zsh, $VAR:t es un modificador (tail) y rompe comandos como git show $RUN:ruta. Usa ${VAR} con llaves cuando a la variable le sigue ':'.
