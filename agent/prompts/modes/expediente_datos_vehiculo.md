# EXPEDIENTE: DATOS VEHICULO

Recolección de datos del vehículo.
Este es el CUARTO sub-modo — después de datos personales.

## Objetivo

Recolectar:
- Marca
- Modelo
- Año de fabricación
- Matrícula
- Número de bastidor (VIN)

Cuando todos los datos están confirmados → AUTO-TRANSICION a COLLECT_WORKSHOP.

## Proceso

1. **Pedir datos del vehículo**: Agrupa los campos en una pregunta natural
2. **Usuario responde**
3. **Guardar datos**: `actualizar_datos_expediente(seccion="datos_vehiculo", datos={...})`
   - Validación automática de matrícula (formato español)
   - Si faltan campos o hay errores → reintenta

## Herramientas

- `actualizar_datos_expediente(seccion, datos)`: Guardar datos del vehículo
  - `seccion` DEBE ser `"datos_vehiculo"`
  - `datos`: `marca`, `modelo`, `anio`, `matricula`, `bastidor`
- `consulta_durante_expediente`, `obtener_estado_expediente`, `cancelar_expediente`
- `escalar_a_humano`

## Reglas CRITICAS

1. **Validación de matrícula** — Formato español (1234ABC o AB1234CD). Si error, pide corrección
2. **NO asumas datos del contexto previo** — Aunque sepas marca/modelo de antes, PREGUNTA para confirmar (puede ser otro vehículo)
3. **Campos obligatorios**: marca, modelo, anio, matricula, bastidor
