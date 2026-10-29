# Spec Delta

## MODIFIED Requirements

### Requirement: Commit explícito del cerebro diario
Los comandos del cerebro diario y la importación SHALL escribir los archivos sin hacer commit. `factory brain commit` MUST hacer un commit solo de los cambios bajo la ruta del cerebro diario y la del mapa de la biblioteca, y dejar sin tocar cualquier otro cambio del checkout. `factory status` MUST avisar si el cerebro diario o el mapa tienen cambios sin commitear.

#### Scenario: Commit con otros cambios en el checkout
- **WHEN** hay notas nuevas en el cerebro diario y además un archivo de código modificado, y se ejecuta `factory brain commit`
- **THEN** el commit contiene solo los archivos del cerebro diario y el archivo de código sigue modificado sin commitear

#### Scenario: Aviso de cambios pendientes
- **WHEN** el cerebro diario tiene notas sin commitear
- **THEN** `factory status` muestra un aviso que sugiere `factory brain commit`

#### Scenario: Mapa regenerado por una importación
- **WHEN** una importación regenera el mapa y se ejecuta `factory brain commit`
- **THEN** el commit incluye los cambios del mapa y ningún archivo del cerebro principal
