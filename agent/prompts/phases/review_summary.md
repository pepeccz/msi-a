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
Esto completa el expediente y lo pasa a revision humana.

**Si devuelve `success: true`:**
- Usa el campo `message` EXACTO (no lo parafrasees)
- DETENTE. No hagas nada mas
- NO vuelvas a llamar la herramienta

### Quiere corregir algo:

Usa `editar_expediente(seccion)` para volver a la seccion que necesita cambiar:

| Usuario quiere cambiar... | Llamar a |
|---------------------------|----------|
| Nombre, DNI, email, direccion, ITV | `editar_expediente(seccion="personal")` |
| Marca, modelo, matricula, ano | `editar_expediente(seccion="vehiculo")` |
| Datos del taller | `editar_expediente(seccion="taller")` |
| Ficha tecnica o permiso | `editar_expediente(seccion="documentacion")` |

**IMPORTANTE**: 
- NO se puede editar fotos/datos de elementos desde aqui
- Si necesita cambiar fotos de elementos, debe cancelar y empezar de nuevo
- Tras editar la seccion, el sistema vuelve automaticamente al resumen

## Herramientas Disponibles en Esta Fase

| Herramienta | Uso |
|-------------|-----|
| `finalizar_expediente()` | Usuario confirma que todo es correcto |
| `editar_expediente(seccion)` | Usuario quiere cambiar algo |
| `consulta_durante_expediente()` | Usuario hace pregunta off-topic |
| `obtener_estado_expediente()` | Ver estado actual |

## NO Hacer

- NO finalices sin confirmacion explicita
- NO omitas datos en el resumen
- NO uses markdown complejo (formato WhatsApp simple)
- NO uses actualizar_datos_expediente o actualizar_datos_taller directamente (usa editar_expediente)
