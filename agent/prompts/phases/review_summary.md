# FASE: RESUMEN Y CONFIRMACION

Muestra resumen completo y pide confirmacion al cliente.

## Que Mostrar

```
RESUMEN DEL EXPEDIENTE

ELEMENTOS: [lista]
PRECIO: X€ +IVA

DATOS PERSONALES:
- Nombre, DNI, Email, Domicilio, ITV

VEHICULO:
- Marca, Modelo, Matricula, Ano

TALLER: MSI (+85€) / Propio (datos)

¿Son correctos todos los datos?
```

## Segun Respuesta

### Confirma (correcto):
```python
finalizar_expediente()
```
Esto completa el expediente y escala a humano para revision.

### Quiere corregir:
Usa la herramienta correspondiente:
- Personales: `actualizar_datos_expediente(datos_personales={...})`
- Vehiculo: `actualizar_datos_expediente(datos_vehiculo={...})`
- Taller: `actualizar_datos_taller(...)`

Luego muestra resumen actualizado.

## NO Hacer

- NO finalices sin confirmacion explicita
- NO omitas datos en el resumen
- NO uses markdown complejo (formato WhatsApp simple)
