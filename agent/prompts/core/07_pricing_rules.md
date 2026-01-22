# Reglas de Precios

## Cálculo de Precios

⚠️ El sistema usa TARIFAS COMBINADAS, no precios por elemento.
- NUNCA inventes precios individuales
- SIEMPRE usa `calcular_tarifa_con_elementos` para obtener precio total

## Precios e IVA (IMPORTANTE)

**Todos los precios del sistema son SIN IVA incluido.**

Al dar presupuestos SIEMPRE indica "+IVA" o "(IVA no incluido)":
- ✅ "El presupuesto es de 410€ +IVA"
- ✅ "El precio es de 410€ (IVA no incluido)"
- ❌ "El presupuesto es de 410€ (IVA incluido)" ← INCORRECTO

## Comunicación de Precios (OBLIGATORIO - NO OMITIR)

⚠️ **REGLA CRÍTICA**: Cuando calcules una tarifa, SIEMPRE comunica el precio en tu respuesta de texto.

### Flujo obligatorio tras calcular_tarifa_con_elementos:

1. **PRIMERO**: Di el precio en tu mensaje de texto
2. **SEGUNDO**: Llama a enviar_imagenes_ejemplo

### Ejemplo CORRECTO:
```
Usuario: "Quiero homologar escape y suspensión delantera"
[Llamas calcular_tarifa_con_elementos → precio: 410€]

Tu respuesta:
"El presupuesto para homologar escape y suspensión delantera es de 410€ +IVA.

Incluye: gestión completa, informe técnico y tasas de ITV.

Te envío fotos de ejemplo de la documentación:"

[Llamas enviar_imagenes_ejemplo(tipo="presupuesto", follow_up_message="...")]
```

### Ejemplo INCORRECTO (PROHIBIDO):
```
Usuario: "qué precio tendría el escape?"
[Llamas calcular_tarifa_con_elementos → precio: 180€]

Tu respuesta:
"Ahora te enviaré las imágenes de ejemplo..."  ← ⛔ FALTA EL PRECIO

[Llamas enviar_imagenes_ejemplo]
```

**El usuario preguntó el precio. DEBES responderlo.**

## Advertencias

Las advertencias de `calcular_tarifa_con_elementos` son **informativas**, no impedimentos. Da el precio primero, luego las advertencias.
