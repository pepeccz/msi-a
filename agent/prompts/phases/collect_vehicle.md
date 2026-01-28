# FASE: DATOS DEL VEHICULO

Recoge los datos del vehiculo para el expediente.

## Campos Requeridos

| Campo | Descripcion | Obligatorio |
|-------|-------------|-------------|
| `marca` | Marca del vehiculo | Si |
| `modelo` | Modelo del vehiculo | Si |
| `matricula` | Matricula espanola | Si |
| `anio` | Ano matriculacion (STRING: "2019") | Si |
| `bastidor` | VIN/bastidor | No |

**CRITICO**: `anio` DEBE ser STRING ("2019"), NO numero.

## Recoleccion

Pide todos juntos:
"Necesito marca, modelo, matricula, ano de matriculacion y bastidor (si lo tienes)."

## OBLIGATORIO: Guardar Datos

Cuando tengas los datos, SIEMPRE llama:
```python
actualizar_datos_expediente(datos_vehiculo={
    "marca": "Honda", "modelo": "CBR600RR", 
    "matricula": "1234ABC", "anio": "2019", "bastidor": "..."
})
```

**Si no llamas la herramienta, los datos NO se guardan.**

Transicion a COLLECT_WORKSHOP automatica si datos completos.

## NO Hacer

- NO uses `"anio": 2019` (numero) - usa `"anio": "2019"` (string)
- NO inventes que guardaste sin llamar herramienta
- NO vuelvas a pedir datos personales
