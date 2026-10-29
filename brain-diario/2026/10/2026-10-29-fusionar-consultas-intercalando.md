---
id: 2026/10/2026-10-29-fusionar-consultas-intercalando
type: pattern
title: Fusionar consultas intercalando
date: '2026-10-29'
tags:
- busqueda
- cerebros
keywords:
- consulta
- consultas
- fuente
- fusionar
- plazas
- agrupa
- api
- cada
abstract: 'Al fusionar resultados de varias consultas, intercálalos (la mejor de cada
  consulta, luego la segunda…) en lugar de ordenar todo por puntuación: una consulta
  con títulos más coincidentes (''api gateway'') se llevaba todas las plazas y dejaba
  fuera a ''rate limiting''.'
source: manual
tokens: 87
---

# Fusionar consultas intercalando

> Cerebro diario · pattern · 2026-10-29 · manual

Al fusionar resultados de varias consultas, intercálalos (la mejor de cada consulta, luego la segunda…) en lugar de ordenar todo por puntuación: una consulta con títulos más coincidentes ('api gateway') se llevaba todas las plazas y dejaba fuera a 'rate limiting'. Agrupa por consulta, no por consulta y fuente, para no dar plazas de más a una fuente.
