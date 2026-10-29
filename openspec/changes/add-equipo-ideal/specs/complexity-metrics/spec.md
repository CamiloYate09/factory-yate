# Spec Delta

## Purpose

Mide de forma determinista y sin dependencias la complejidad ciclomática de las funciones Python, también como delta frente a una referencia. Así el jugador `metricas` y cualquier persona pueden detectar las funciones que un cambio vuelve más difíciles de probar y de mantener.

## ADDED Requirements

### Requirement: Cálculo de la complejidad ciclomática
`factory complexity` SHALL calcular la complejidad ciclomática de cada función y método Python. La cuenta MUST ser:
- base 1;
- +1 por cada `if` y `elif`, `for` y `async for`, `while`, `except`, `case` de un `match` y expresión condicional;
- +1 por cada `for` e `if` de una comprensión;
- +1 por cada operando adicional de `and` y `or`.

#### Scenario: Función lineal
- **WHEN** se analiza una función sin ramas
- **THEN** su complejidad es 1

#### Scenario: Ramas y operadores lógicos
- **WHEN** una función tiene un `if` con condición `a and b or c`, un `elif` y un bucle `for`
- **THEN** su complejidad es 6: base 1, +1 por el `if`, +2 por los operandos adicionales, +1 por el `elif` y +1 por el `for`

### Requirement: Funciones anidadas, métodos y rangos
Las funciones anidadas SHALL medirse por separado, sin sumar a la función que las contiene. Los métodos MUST nombrarse `Clase.metodo`. Cada función MUST tener un rango: A (1–5), B (6–10), C (11–20), D (21–30), E (31–40) o F (41 o más).

#### Scenario: Rango de una función lineal
- **WHEN** una función tiene complejidad 1
- **THEN** su rango es A

#### Scenario: Método de una clase
- **WHEN** la clase `Motor` define el método `arrancar`
- **THEN** la función se informa como `Motor.arrancar`

#### Scenario: Función anidada
- **WHEN** una función con un `if` contiene otra función con dos `if`
- **THEN** la exterior tiene complejidad 2, la interior 3 y se informan por separado

### Requirement: Alcance y salida
Sin rutas, el comando SHALL analizar los archivos `*.py` versionados del repo. Con rutas, MUST analizar esos archivos y los `*.py` de esos directorios. La salida MUST listar las funciones por complejidad descendente, con `archivo:línea`, nombre, complejidad y rango, seguidas de un resumen con el número de funciones, la media y el máximo. Con `--json` MUST emitir los mismos datos como JSON. Un archivo con errores de sintaxis MUST avisarse y omitirse sin abortar el análisis.

#### Scenario: Directorio indicado
- **WHEN** se ejecuta `factory complexity src` en un repo con funciones en `src/` y en `tests/`
- **THEN** solo aparecen las funciones de `src/`, ordenadas de mayor a menor complejidad

#### Scenario: Archivo con error de sintaxis
- **WHEN** uno de los archivos analizados no es Python válido
- **THEN** la salida avisa de ese archivo y sigue informando de los demás

### Requirement: Delta frente a una referencia
Con `--base REF`, el comando SHALL analizar solo los archivos `*.py` cambiados frente a `REF`, incluidos los no versionados. Cada función MUST mostrar su complejidad en `REF` y el delta. Una función que no existe en `REF` MUST marcarse como nueva, sin valor base.

#### Scenario: Función empeorada
- **WHEN** un cambio añade dos `if` a una función que tenía complejidad 4 en `REF`
- **THEN** la función aparece con base 4, actual 6 y delta +2

#### Scenario: Función nueva
- **WHEN** un cambio añade una función que no existía en `REF`
- **THEN** la función aparece marcada como nueva con su complejidad actual

### Requirement: Umbral
Con `--max N`, el comando SHALL terminar con código 1 si alguna función del alcance supera N, y nombrar esas funciones. En modo `--base`, el alcance del umbral MUST ser solo las funciones nuevas o empeoradas. Sin `--max`, el comando MUST terminar con código 0 si el análisis se completa.

#### Scenario: Umbral superado
- **WHEN** se ejecuta `factory complexity --max 10` y una función tiene complejidad 12
- **THEN** el comando termina con código 1 y nombra esa función

#### Scenario: Deuda previa sin empeorar
- **WHEN** se ejecuta `factory complexity --base main --max 10` y la única función por encima de 10 no cambió frente a `main`
- **THEN** el comando termina con código 0
