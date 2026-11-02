# Spec Delta

## ADDED Requirements

### Requirement: Estado de carga
Hasta recibir la primera instantánea, la página SHALL indicar en cada vista que está cargando. MUST NOT mostrar los mensajes de vacío («No hay transcripciones…», «Aún no hay revisiones…»), porque afirman algo que la página todavía no sabe. Si la primera petición falla, MUST mostrar el error en lugar del indicador de carga.

#### Scenario: Primera carga lenta
- **WHEN** la página se abre y `/api/snapshot` aún no ha respondido
- **THEN** las pestañas Tokens, Revisiones y Tareas muestran «Cargando…»
- **AND** ninguna muestra un mensaje de vacío

#### Scenario: Primera carga fallida
- **WHEN** la primera petición a `/api/snapshot` responde con un error
- **THEN** la página muestra el aviso del error y deja de indicar que carga

### Requirement: Día de los tokens explícito
El indicador de tokens del día y el eje del gráfico de tokens por día SHALL rotularse como días UTC, igual que su agregación. El gráfico MUST mostrar cada día entre el primero y el último con datos, y un día sin datos como un hueco con valor cero.

#### Scenario: Día local distinto del UTC
- **WHEN** la hora local es el 1 de noviembre a las 20:15 en UTC−5
- **THEN** el indicador dice que corresponde al día 2026-11-02 en UTC

#### Scenario: Días sin actividad
- **WHEN** hay datos del 30 de octubre y del 2 de noviembre, y ninguno entre medias
- **THEN** el gráfico muestra cuatro posiciones, con el 31 de octubre y el 1 de noviembre a cero

### Requirement: Revisión sin veredicto
Una revisión `sin_veredicto` SHALL mostrar «—» en el lugar del recuento de hallazgos, nunca «sin hallazgos». Ese texto queda reservado para una revisión con veredicto y ningún hallazgo.

#### Scenario: Revisor que no dio veredicto
- **WHEN** el feed incluye una revisión con estado `sin_veredicto`
- **THEN** su fila no contiene el texto «sin hallazgos»

### Requirement: Navegación con el historial
El `#hash` de la URL SHALL determinar la pestaña y la feature abiertas, con la forma `#<pestaña>` o `#tareas/<id>`. Ir atrás o adelante en el historial del navegador MUST mostrar la vista que corresponde al nuevo `#hash`, sin recargar.

#### Scenario: Botón Atrás
- **WHEN** el usuario pasa de Tokens a Revisiones y pulsa Atrás en el navegador
- **THEN** la página muestra la pestaña Tokens

#### Scenario: Enlace a una feature
- **WHEN** se abre la página con `#tareas/observability-panel`
- **THEN** se muestra la pestaña Tareas con el detalle de `observability-panel`

### Requirement: Pestañas accesibles con teclado
Las pestañas SHALL seguir el patrón de pestañas accesibles: cada pestaña controla su panel, y cada panel está etiquetado por su pestaña. Las flechas izquierda y derecha MUST mover la selección a la pestaña contigua.

#### Scenario: Flecha derecha
- **WHEN** el foco está en la pestaña Tokens y se pulsa la flecha derecha
- **THEN** se selecciona la pestaña Revisiones y recibe el foco

### Requirement: Detalle de feature visible
Al abrir el detalle de una feature, la página SHALL desplazarse hasta él y darle el foco. Al cerrarlo, MUST devolver el foco a la tarjeta de esa feature.

#### Scenario: Feature al final del tablero
- **WHEN** el usuario pulsa una feature que está más abajo de lo visible en la columna de terminadas
- **THEN** el detalle queda a la vista y con el foco

#### Scenario: Cerrar el detalle
- **WHEN** el usuario pulsa «Cerrar» en el detalle
- **THEN** el foco vuelve a la tarjeta de la feature

### Requirement: Selector de tema
El control de tema SHALL tener tres posiciones (Sistema, Claro y Oscuro) y mostrar en su etiqueta la posición activa. La posición elegida MUST recordarse entre visitas. En Sistema, la página MUST seguir la preferencia del sistema operativo.

#### Scenario: Volver al tema del sistema
- **WHEN** el tema está en Oscuro y el usuario pulsa el control
- **THEN** el control pasa a Sistema y la página sigue la preferencia del sistema operativo

### Requirement: Filtros del feed de revisiones
Los indicadores de estado del feed SHALL ser controles que filtran el feed por ese estado, y MUST indicar si están activos. Un interruptor MUST ocultar las revisiones `sin_cierre` y `sin_veredicto`. Los filtros de estado se combinan con el filtro de origen.

#### Scenario: Filtrar por fallidas
- **WHEN** el usuario activa el filtro de estado `fail`
- **THEN** el feed solo muestra revisiones `fail`, y el control aparece como activo

#### Scenario: Ocultar revisiones sin cierre
- **WHEN** el usuario activa el interruptor de ocultar
- **THEN** el feed no muestra revisiones `sin_cierre` ni `sin_veredicto`

### Requirement: Indicadores enlazables
Los indicadores que tienen una vista asociada SHALL llevar a ella al pulsarlos:
- «Feature en curso» abre el detalle de esa feature;
- «Revisiones en curso» abre el feed filtrado por `en_curso`;
- «Coste registrado» abre la tabla de ejecuciones.

#### Scenario: Ir a la feature en curso
- **WHEN** hay una feature `in_progress` y el usuario pulsa su indicador
- **THEN** se muestra la pestaña Tareas con el detalle de esa feature

### Requirement: Frescura de los datos
La página SHALL mostrar cuánto tiempo hace que recibió la última instantánea, y actualizar ese texto sin pedir datos. Un control MUST pedir una instantánea nueva al pulsarlo.

#### Scenario: Refresco manual
- **WHEN** el usuario pulsa el control de refresco
- **THEN** la página pide `/api/snapshot` y el texto vuelve a «hace 0 s»

### Requirement: Comandos copiables
La página SHALL ofrecer botones que copian al portapapeles el comando de factory que corresponde a lo que se ve, y que nunca lo ejecutan:
- `.venv/bin/factory features verify <id>` en el detalle de una feature;
- `.venv/bin/factory goal rework <run> --answer ` en una ejecución terminada que no sea `completed`, sin ninguna respuesta de ejemplo: la escribe el usuario;
- `.venv/bin/factory land <run> --dry-run` en una ejecución `completed`.

#### Scenario: Copiar la verificación
- **WHEN** el usuario pulsa «Copiar comando» en el detalle de `panel-ux-fixes`
- **THEN** el portapapeles contiene `.venv/bin/factory features verify panel-ux-fixes`
- **AND** la página no envía ninguna petición distinta de `GET`

#### Scenario: Ejecución integrable
- **WHEN** una ejecución tiene estado `completed`
- **THEN** su botón copia el comando `land` con `--dry-run`, y no ofrece el comando `rework`

#### Scenario: Ejecución para retrabajar
- **WHEN** una ejecución tiene estado `max_rounds`
- **THEN** su botón copia `.venv/bin/factory goal rework <run> --answer ` y el comando termina sin respuesta

#### Scenario: Ejecución en marcha
- **WHEN** una ejecución tiene estado `running`
- **THEN** no ofrece ningún comando

### Requirement: Identificadores seguros en comandos
Un comando copiable SHALL ofrecerse solo si el identificador de la feature o de la ejecución contiene únicamente letras, dígitos, `.`, `_` y `-`. Con cualquier otro identificador, la página MUST omitir el botón, para no poner en el portapapeles texto que el shell interprete.

#### Scenario: Identificador con metacaracteres
- **WHEN** una feature tiene el id `x; rm -rf ~`
- **THEN** su detalle no muestra el botón de copiar comando

### Requirement: Gráfico de tokens sin lectura de caché
El gráfico de tokens por día SHALL tener un interruptor que excluye la lectura de caché. Por defecto, MUST excluirla e indicar junto al gráfico que está oculta, porque su volumen tapa el resto de series. El valor del interruptor MUST recordarse entre visitas.

#### Scenario: Vista por defecto
- **WHEN** se abre la pestaña Tokens por primera vez
- **THEN** el gráfico apila entrada, escritura de caché y salida, y una nota indica que la lectura de caché está oculta

### Requirement: Tablero de features compacto
En el tablero de features, la columna de terminadas SHALL aparecer plegada por defecto, mostrando su número de features. Un buscador MUST filtrar las tarjetas de todas las columnas por id o por título. Mientras haya una búsqueda, la columna de terminadas MUST mostrarse desplegada.

#### Scenario: Buscar una feature terminada
- **WHEN** el usuario escribe `review` en el buscador
- **THEN** el tablero muestra solo las features cuyo id o título contiene `review`, incluidas las terminadas

### Requirement: Texto legible
La página SHALL mostrar como código el texto entre comillas invertidas de los títulos y las tareas de OpenSpec, sin mostrar las comillas. Los estados de las revisiones MUST mostrarse en español, con el valor original disponible como título del elemento. Una etiqueta recortada MUST ofrecer su texto completo al pasar el puntero o con el foco.

#### Scenario: Grupo con id entre comillas invertidas
- **WHEN** un grupo se titula «Consumo de tokens (`token-usage`)»
- **THEN** `token-usage` aparece como código y las comillas invertidas no aparecen

#### Scenario: Estado traducido
- **WHEN** una revisión tiene estado `pass_with_minor`
- **THEN** su chip dice «aprobado con menores» y su título es `pass_with_minor`

### Requirement: Columnas sin información
La tabla de sesiones recientes SHALL ocultar la columna «Proyecto» cuando todas sus filas tienen el mismo valor.

#### Scenario: Todas las sesiones en el repo principal
- **WHEN** todas las sesiones recientes tienen el proyecto `principal`
- **THEN** la tabla no muestra la columna «Proyecto»
