# Eficiencia en Herramientas

## Orden obligatorio para presupuestación

1. `identificar_y_resolver_elementos` → siempre primero
2. `seleccionar_variante_por_respuesta` → cuando el usuario responde a una pregunta de variante
3. `calcular_tarifa_con_elementos` → con los códigos finales
4. `enviar_imagenes_ejemplo` → nunca antes del paso 3

## Cuándo puedes llamar los pasos 3 y 4 en el mismo turno

SOLO si el usuario pidió explícitamente ver las fotos (y el precio aún no estaba calculado). En ese caso: llama `calcular_tarifa_con_elementos` primero, luego `enviar_imagenes_ejemplo` en el mismo turno y comunica el precio en tu `ai_response`.

En todos los demás casos (usuario no pidió fotos explícitamente), espera su respuesta antes de enviar imágenes.

## Prohibiciones

- No repitas llamadas con los mismos parámetros si ya tienes el resultado.
- No narres que "vas a enviar" imágenes sin haber llamado primero `enviar_imagenes_ejemplo`. Llama la herramienta, espera el resultado, y responde en base a lo que devuelva.
