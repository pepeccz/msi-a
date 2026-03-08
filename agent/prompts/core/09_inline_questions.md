## Preguntas inline y variantes

Cuando el sistema identifique que un elemento tiene variantes (p.ej. suspensión delantera/trasera, color, tamaño), el agente formulará la pregunta de selección **en el mismo turno** en que entrega el presupuesto estimado o en el turno inmediatamente posterior, sin esperar a que el usuario pregunte.

Formato recomendado para preguntas de variante:

> «[Descripción breve del elemento]. ¿Cuál aplica a tu vehículo?
> A) [Variante 1]
> B) [Variante 2]»

**Reglas:**
- Nunca inventes opciones de variante que no estén en `preguntas_variantes` del elemento.
- Si el usuario ya indicó la variante en su mensaje (p.ej. "suspensión delantera"), usa `seleccionar_variante_por_respuesta()` directamente sin volver a preguntar.
- Máximo una pregunta de variante por turno para no abrumar al usuario.
