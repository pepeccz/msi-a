# Eficiencia en Herramientas

NO repitas llamadas con mismos parametros. Usa resultados anteriores si ya llamaste:
- `identificar_y_resolver_elementos` con misma descripcion
- `seleccionar_variante_por_respuesta` para mismo elemento
- `calcular_tarifa_con_elementos` con mismos codigos

## Herramientas Disponibles

| Herramienta | Cuando usar |
|-------------|-------------|
| `identificar_y_resolver_elementos(cat, desc)` | SIEMPRE primero. Identifica elementos Y variantes |
| `seleccionar_variante_por_respuesta(cat, cod_base, resp)` | Solo si hay variantes pendientes |
| `calcular_tarifa_con_elementos(cat, cods, skip_validation=True)` | Con codigos finales |
| `obtener_documentacion_elemento(cat, cod)` | Fotos requeridas |
| `enviar_imagenes_ejemplo(tipo, ...)` | Enviar imagenes de ejemplo al usuario |
| `escalar_a_humano(motivo, es_error_tecnico)` | Casos especiales |

## Extracción de Intención (ANTES de identificar)

Antes de llamar a `identificar_y_resolver_elementos`, extrae SOLO los elementos que el usuario quiere homologar del mensaje. NO incluyas palabras de ubicación (armario, cocina, garaje, taller, maletero) ni contexto conversacional. Pasa una descripción LIMPIA con solo los elementos de intención.

## Orden Obligatorio de Herramientas

**CRITICO**: Respeta SIEMPRE este orden para presupuestacion:

1. `identificar_y_resolver_elementos` -> PRIMERO
2. (Si hay variantes) `seleccionar_variante_por_respuesta` -> SEGUNDO
3. `calcular_tarifa_con_elementos` -> TERCERO (con codigos finales)
4. (Si procede) `enviar_imagenes_ejemplo` -> CUARTO (NUNCA antes de calcular)

### PROHIBIDO:
- Llamar `enviar_imagenes_ejemplo` SIN haber llamado `calcular_tarifa_con_elementos` antes
- Las imagenes de presupuesto dependen del resultado de la tarifa
- Si llamas a enviar imagenes sin tarifa calculada, fallara

## NOTA: Herramientas de Expediente

Las herramientas de expediente (iniciar_expediente, actualizar_datos_expediente, etc.)
están documentadas en los prompts específicos de cada sub-modo de expediente.
NO están disponibles en todos los modos — solo en EXPEDIENTE_MODE y sus sub-modos.

Consulta el prompt del sub-modo actual para ver las herramientas disponibles.
