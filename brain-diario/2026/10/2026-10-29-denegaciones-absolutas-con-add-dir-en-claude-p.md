---
id: 2026/10/2026-10-29-denegaciones-absolutas-con-add-dir-en-claude-p
type: learning
title: Denegaciones absolutas con --add-dir en claude -p
date: '2026-10-29'
tags:
- claude-code
- permisos
keywords:
- add-dir
- claude
- ruta
- denegaciones
- directorio
- absoluta
- absolutas
- anadido
abstract: Con claude -p, las denegaciones con ruta absoluta Edit(//ruta/**) y Write(//ruta/**)
  bloquean la escritura en un directorio añadido con --add-dir (quedan en permission_denials),
  y la lectura sigue permitida.
source: manual
tokens: 82
---

# Denegaciones absolutas con --add-dir en claude -p

> Cerebro diario · learning · 2026-10-29 · manual

Con claude -p, las denegaciones con ruta absoluta Edit(//ruta/**) y Write(//ruta/**) bloquean la escritura en un directorio añadido con --add-dir (quedan en permission_denials), y la lectura sigue permitida. El CLAUDE.md de un directorio de --add-dir no se carga en el contexto. Comprobado con dos invocaciones reales (0,01 USD).
