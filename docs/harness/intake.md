# Intake de peticiones

Una puerta de triaje antes de construir. Recoge una idea en lenguaje natural y la convierte en un **borrador** de objetivo, sin que ningún comando propuesto por un agente se ejecute sin revisión humana.

## Uso

Para pasar de una idea en lenguaje natural a un objetivo, sin escribir `goal.md` a mano y sin ejecutar nada propuesto por un agente sin revisarlo:

```bash
.venv/bin/factory intake "Añade la función restar con su test"        # o --file peticion.md
.venv/bin/factory intake --answer <request-id> "decimal"               # si pidió información
.venv/bin/factory goal promote goals/drafts/<id>.md                    # ver comandos y avisos (no cambia nada)
.venv/bin/factory goal promote goals/drafts/<id>.md --yes              # crear goals/<id>.md ejecutable
```

- **Agente de intake:** rol `intake` (`[roles.intake]`, modelo `opus` por defecto, `--budget` 1 USD). Es de **solo lectura**: Read, Glob y Grep, sin shell ni edición, y ninguna configuración puede darle más. Lee el repo y decide:

  | Decisión | Efecto |
  |---|---|
  | `ACCEPT` | borrador `goals/drafts/<id>.md` con `status: draft`, `risk` y `surfaces`. Si recorta el alcance (`RESCOPED: yes`), lista lo que queda fuera |
  | `NEEDS-INFO` | pregunta en la bandeja; respondes con `--answer` y se vuelve a triar. Las decisiones anteriores quedan como `intake-<k>.md` |
  | `REJECT` | motivo en la bandeja |

- **La petición es un dato:** se guarda citada en `.factory/requests/<id>/request.md`, con un aviso de que no son instrucciones, y nunca entra en el prompt de sistema.
- **Los borradores no se ejecutan:** `goal run`, `tick` y el motor rechazan `status: draft` antes de ejecutar ningún criterio.
- **La promoción es explícita:** `goal promote` muestra el plan y avisa de ejecutables que no existen. Solo con `--yes` crea `goals/<id>.md`, sin sobrescribir uno existente, y marca la petición como `promoted`.

Estado de cada petición: `.factory/requests/<id>/state.json`, con las etapas `received → accepted | needs_info | rejected`, `needs_info → received` y `accepted → promoted`. Un único escritor valida cada paso.

## Seguridad

- El agente de intake no puede escribir ni ejecutar comandos: lo máximo que produce es un archivo de texto en `goals/drafts/`.
- `acceptance.run` se ejecuta con shell en tu máquina, así que **lee los comandos** que muestra `goal promote` antes de usar `--yes`.
- Una petición dañina (minería, exfiltración, desactivar controles) debe acabar en `REJECT`. Si el intake la aceptara, el borrador seguiría sin ejecutarse hasta que tú lo promuevas.

---
Patrón inspirado en *Software Factory for Claude Code v2* (ZazenCodes, GPLv3); texto escrito para factory-yate.
