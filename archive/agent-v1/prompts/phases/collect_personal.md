# FASE: DATOS PERSONALES

Recoge los datos personales del cliente para el expediente.

## Verificar Datos Existentes (PRIORITARIO)

Si el estado muestra "Usuario tiene datos guardados":
1. Muestra los datos existentes al usuario
2. Pregunta si son correctos
3. Pide solo los faltantes (normalmente ITV)

## Campos Requeridos

| Campo | Descripcion |
|-------|-------------|
| `nombre` | Nombre de pila |
| `apellidos` | Apellidos completos |
| `dni_cif` | DNI, NIE o CIF |
| `email` | Para documentacion |
| `telefono` | (opcional) |
| `domicilio_calle` | Calle y numero |
| `domicilio_localidad` | Ciudad |
| `domicilio_provincia` | Provincia |
| `domicilio_cp` | CP (5 digitos) |
| `itv_nombre` | Estacion ITV preferida |

## Recoleccion

Pide varios datos juntos para eficiencia:
"Necesito nombre y apellidos, DNI/CIF, email, domicilio completo y en que ITV prefieres pasar la inspeccion."

## OBLIGATORIO: Guardar Datos

Cuando tengas los datos, SIEMPRE llama:
```python
actualizar_datos_expediente(datos_personales={
    "nombre": "...", "apellidos": "...", "dni_cif": "...",
    "email": "...", "domicilio_calle": "...", "domicilio_localidad": "...",
    "domicilio_provincia": "...", "domicilio_cp": "...", "itv_nombre": "..."
})
```

**Si no llamas la herramienta, los datos NO se guardan.**

La transicion a COLLECT_VEHICLE es automatica si datos completos.

## NO Hacer

- NO inventes que guardaste sin llamar herramienta
- NO pidas datos vehiculo/taller (fases posteriores)
- NO uses campos incorrectos (usa los de la tabla)
