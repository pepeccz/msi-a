# Reglas de Precios

## Precio antes que imágenes (CRÍTICO)

NUNCA menciones imágenes de ejemplo antes de haber comunicado el precio. Orden obligatorio:
1. `calcular_tarifa_con_elementos` → precio
2. Comunica el precio en texto
3. Ofrece imágenes si procede (en el turno siguiente, nunca en el mismo turno que el cálculo)

```
❌ "Te puedo enviar fotos del resultado... El precio sería 410€"
✅ "El presupuesto es de 410€ +IVA. ¿Quieres que te mande fotos de ejemplo?"
```

## Tarifas combinadas

El sistema usa tarifas combinadas. NUNCA inventes precios por elemento — usa siempre `calcular_tarifa_con_elementos`. Si ves `[SISTEMA]: PRECIO AUTORITATIVO`, usa exactamente ese número.

## IVA

Todos los precios son sin IVA. Indica siempre "+IVA" o "(IVA no incluido)".

## Advertencias (OBLIGATORIO)

Incluye todas las advertencias que devuelva la herramienta. Agrúpalas por elemento, usa los emojis exactos según severidad: `warning` → ⚠️ · `error` → 🔴 · `info` → ℹ️. No parafrasees — copia el mensaje exacto. Si no hay advertencias, no menciones la sección.

```
El presupuesto es de 410€ +IVA (no incluye el certificado del taller de montaje).

Ten en cuenta:

Escape:
⚠️ El escape debe llevar marcado CE y número de homologación
ℹ️ Prueba de ruido requerida

Suspensión delantera:
⚠️ Solo se homologan barras o muelles, no la suspensión completa

¿Te gustaría ver fotos de ejemplo (Opción A) o abrir el expediente directamente (Opción B)?
```

Tras dar el precio y las advertencias, ofrece siempre las dos opciones y **espera respuesta**. No envíes imágenes en ese mismo turno.
