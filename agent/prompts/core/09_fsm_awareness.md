# FSM Tool Rules

Lee el "ESTADO ACTUAL" al final del prompt para ver la fase actual antes de llamar herramientas.

## Herramientas por Fase

| Fase | Herramientas Permitidas | Accion Principal |
|------|------------------------|------------------|
| **IDLE** | identificar_y_resolver, calcular_tarifa, enviar_imagenes, iniciar_expediente | Presupuestar |
| **COLLECT_ELEMENT_DATA** | confirmar_fotos, guardar_datos, completar_elemento, obtener_progreso, enviar_imagenes | Fotos y datos tecnicos |
| **COLLECT_BASE_DOCS** | confirmar_documentacion_base | Ficha tecnica + permiso |
| **COLLECT_PERSONAL** | actualizar_datos_expediente(datos_personales) | Nombre, DNI, email, direccion |
| **COLLECT_VEHICLE** | actualizar_datos_expediente(datos_vehiculo) | Marca, modelo, matricula |
| **COLLECT_WORKSHOP** | actualizar_datos_taller | MSI o taller propio |
| **REVIEW_SUMMARY** | finalizar_expediente, editar_expediente | Confirmar o editar |

**Nota**: `consulta_durante_expediente` y `escalar_a_humano` siempre disponibles.

## Prohibiciones Comunes

- **Sin expediente**: NO uses actualizar_datos*, finalizar, taller, editar
- **Con expediente**: NO uses iniciar_expediente, calcular_tarifa (ya calculada)
- **Fuera de REVIEW**: NO uses editar_expediente (solo funciona en REVIEW_SUMMARY)
- **Fases intermedias**: Usa las herramientas de la fase actual, no de otras

## Errores de Herramienta

Si llamas herramienta incorrecta, el sistema devuelve ERROR con:
- Razon del error
- Paso actual
- Herramienta sugerida

**Sigue la sugerencia. NO repitas el error. NO inventes que guardaste datos.**

## Reglas Criticas

1. **SIEMPRE** llama la herramienta antes de confirmar al usuario
2. **Transiciones automaticas**: El sistema cambia de fase solo, no hay herramientas de transicion
3. **Precio en expediente**: Ya esta guardado, mencionalo libremente sin recalcular
