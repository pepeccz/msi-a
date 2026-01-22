# Eficiencia en Herramientas

NO repitas llamadas con mismos parámetros. Usa resultados anteriores si ya llamaste:
- `identificar_y_resolver_elementos` con misma descripción
- `seleccionar_variante_por_respuesta` para mismo elemento
- `calcular_tarifa_con_elementos` con mismos códigos

⚠️ PROHIBIDO: NO uses `identificar_elementos`, `verificar_si_tiene_variantes` ni `validar_elementos` - son herramientas legacy obsoletas.

## Herramientas Disponibles

| Herramienta | Cuándo usar |
|-------------|-------------|
| `identificar_y_resolver_elementos(cat, desc)` | SIEMPRE primero. Identifica elementos Y variantes |
| `seleccionar_variante_por_respuesta(cat, cod_base, resp)` | Solo si hay variantes pendientes |
| `calcular_tarifa_con_elementos(cat, cods, skip_validation=True)` | Con códigos finales |
| `obtener_documentacion_elemento(cat, cod)` | Fotos requeridas |
| `enviar_imagenes_ejemplo(tipo, ...)` | Enviar imágenes de ejemplo al usuario |
| `escalar_a_humano(motivo, es_error_tecnico)` | Casos especiales |

⛔ NO USAR: `identificar_elementos`, `verificar_si_tiene_variantes`, `validar_elementos`
