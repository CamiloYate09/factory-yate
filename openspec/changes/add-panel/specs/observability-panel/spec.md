# Spec Delta

## Purpose

Ofrece un panel gráfico local que reúne en una sola vista el consumo de tokens, el feed de revisiones y el estado de implementación de features, cambios OpenSpec y ejecuciones de factory. Se actualiza solo cuando cambia el estado y nunca modifica nada.

## ADDED Requirements

### Requirement: Instantánea del estado
`factory panel --json` SHALL imprimir en stdout una instantánea JSON con las secciones `tokens`, `reviews` y `tasks`, y terminar con código 0. El servidor MUST devolver la misma instantánea en `GET /api/snapshot`. Un archivo de estado ausente o ilegible MUST dejar su sección vacía con un aviso en `warnings`.

#### Scenario: Repo sin ejecuciones
- **WHEN** se ejecuta `factory panel --json` en un repo sin `.factory/`
- **THEN** termina con código 0 y la instantánea tiene las tres secciones, con listas vacías donde no hay datos

#### Scenario: Lista de features corrupta
- **WHEN** `feature_list.json` no es JSON válido
- **THEN** la instantánea sigue generándose y `warnings` nombra el archivo

### Requirement: Servidor local
`factory panel` SHALL servir la página y la API en `127.0.0.1` (puerto configurable con `--port`, 8765 por defecto) hasta que se interrumpa. MUST rechazar con 403 las peticiones cuya cabecera `Host` no sea `127.0.0.1`, `localhost` o `[::1]` y responder 405 a cualquier método distinto de `GET` o `HEAD`.

#### Scenario: Página principal
- **WHEN** se pide `GET /` con `Host: 127.0.0.1:8765`
- **THEN** responde 200 con la página HTML del panel

#### Scenario: Host ajeno
- **WHEN** se pide `GET /api/snapshot` con `Host: atacante.example`
- **THEN** responde 403 sin datos

#### Scenario: Escritura
- **WHEN** se envía `POST /api/snapshot`
- **THEN** responde 405

### Requirement: Actualización en vivo
`GET /api/stream` SHALL mantener una conexión de *server-sent events* y enviar un evento `change` con las secciones afectadas cuando cambie algún archivo vigilado: `feature_list.json`, los `tasks.md` de los cambios activos, el estado y los eventos de `.factory/` y las transcripciones del proyecto. La página MUST refrescar la instantánea al recibirlo.

#### Scenario: Revisión que termina
- **WHEN** se añade una línea a `.factory/hooks/events.jsonl` con el panel abierto
- **THEN** el stream envía un evento `change` que incluye `reviews`

#### Scenario: Feature promovida
- **WHEN** `factory features verify` cambia `feature_list.json`
- **THEN** el stream envía un evento `change` que incluye `tasks`

### Requirement: Estado de implementación
La sección `tasks` SHALL incluir cada feature con su estado, prioridad, comandos de verificación y última evidencia, y cada cambio OpenSpec activo con sus tareas hechas y totales por grupo. Un grupo cuyo título nombre un id de feature entre comillas invertidas MUST enlazarse con esa feature.

#### Scenario: Grupo enlazado
- **WHEN** `tasks.md` tiene el grupo "## 2. Plantilla y convocatoria (`team-roster`)" con 1 de 4 tareas marcadas y existe la feature `team-roster`
- **THEN** la feature `team-roster` muestra 1/4 tareas de ese grupo

### Requirement: Ejecuciones y bandeja
La sección `tasks` SHALL incluir las ejecuciones de factory con su estado, ronda actual, criterios superados, último veredicto, coste acumulado y si su proceso sigue vivo, además del número de entradas pendientes de la bandeja.

#### Scenario: Ejecución huérfana
- **WHEN** una ejecución figura como `running` pero su `pid` ya no existe
- **THEN** la instantánea la marca como no viva

### Requirement: Página gráfica
La página SHALL funcionar sin red: HTML, CSS, JS y gráficos en línea, sin recursos externos. Debe mostrar el consumo de tokens con gráficos, el feed de revisiones y el estado de implementación con una vista de detalle por feature, y adaptarse a tema claro u oscuro y a pantallas estrechas.

#### Scenario: Sin recursos externos
- **WHEN** se inspecciona la página servida
- **THEN** no contiene ninguna URL `http://` ni `https://` a otro origen

### Requirement: Panel de solo lectura
El panel SHALL limitarse a leer: ni el servidor ni `factory panel --json` crean, modifican o borran archivos del repo, de `.factory/` o de las transcripciones.

#### Scenario: Instantánea sin efectos
- **WHEN** se pide `/api/snapshot` sobre un repo con ejecuciones, hooks y transcripciones
- **THEN** las fechas de modificación y los contenidos de todos esos archivos quedan iguales
