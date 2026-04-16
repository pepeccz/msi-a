# Flujos de Conversación Esperados — Source of Truth

> Estos flujos definen QUÉ debe pasar en cada escenario.
> El system prompt debe hacer que el LLM siga estos flujos.

---

## Flow 1: Happy Path — Consulta → Precio → Fotos → Expediente

```
USER: "¿Qué documentación necesito para homologar el escape de mi moto?"

AGENT: identificar_y_resolver_elementos("motos-part", "escape")
  → Retorna: ESCAPE identificado, documentación, advertencias
AGENT responde:
  DOCUMENTACIÓN BASE: [lista]
  DOCUMENTACIÓN DEL ESCAPE: [lista]
  ⚠️ [advertencias]
  CTA: "¿Quieres que te muestre fotos de ejemplo o te calculo un presupuesto?"

USER: "calcúlame el presupuesto"

AGENT: calcular_tarifa_con_elementos("motos-part", ["ESCAPE"], skip_validation=True)
  → Retorna: 250€, advertencias
AGENT responde:
  "El presupuesto es de 250€ +IVA. ⚠️ [advertencias]"
  CTA: "¿Quieres ver fotos de ejemplo (A) o abrimos el expediente directamente (B)?"

USER: "A" / "muéstrame fotos"

AGENT: enviar_imagenes_ejemplo(tipo="presupuesto")
  → Retorna: success, 3 imágenes encoladas
  [Las imágenes llegan ANTES que el texto del agente]
AGENT responde:
  CTA: "¿Quieres que abramos el expediente para gestionar tu homologación?"

USER: "sí, dale"

AGENT: confirmar_presupuesto()
  → Transición a EXPEDIENTE_MODE
  [Sistema inicia expediente y pasa a COLLECT_ELEMENT_DATA]
```

---

## Flow 2: Happy Path — Expediente Completo

### Fase 1: COLLECT_ELEMENT_DATA (por cada elemento)

```
SUBPHASE A — FOTOS:
  AGENT: enviar_imagenes_ejemplo(tipo="elemento", codigo_elemento="ESCAPE", categoria="motos-part")
  AGENT: "Necesito estas fotos del escape:
    1. Foto del escape instalado, vista lateral
    2. Foto de la etiqueta de homologación
    Envíamelas como foto o como PDF."
  
  [Usuario envía fotos por WhatsApp — el sistema las guarda automáticamente]
  
  USER: "listo"
  AGENT: confirmar_fotos_elemento()

SUBPHASE B — DATOS TÉCNICOS (si hay campos pendientes):
  AGENT: obtener_campos_elemento()
  AGENT: "Necesito estos datos:
    1. Marca del escape (ej: Akrapovic)
    2. Modelo del escape (ej: Racing Line)
    Una vez que los tengas, envíamelos."
  
  USER: "Akrapovic, Racing Line"
  AGENT: guardar_datos_elemento(datos={"marca_escape": "Akrapovic", "modelo_escape": "Racing Line"})
  AGENT: completar_elemento_actual()

[Si hay más elementos → repetir. Si todos completos → auto-transición]
```

### Fase 2: COLLECT_BASE_DOCS

```
AGENT: enviar_imagenes_ejemplo(tipo="documentacion_base", categoria="motos-part")
AGENT: "Necesito la documentación del vehículo:
  1. Ficha técnica (ambas caras)
  2. Permiso de circulación (ambas caras)
  3. DNI/NIE del titular (ambas caras)
  4. 4 fotos: frontal, trasera, lateral izquierda y derecha
  Puedes enviarlas como foto o como PDF."

[Usuario envía docs]
USER: "listo"
AGENT: confirmar_documentacion_base(usuario_confirma=true)
```

### Fase 3: COLLECT_PERSONAL

```
AGENT: "Necesito tus datos personales: nombre completo, DNI/NIE/CIF, 
  email, dirección completa (calle, localidad, provincia, CP de 5 dígitos) 
  y el nombre de la ITV donde inspeccionarás el vehículo."

USER: "Pepe Cabeza Cruz, 77429548W, pepe@email.com, Calle Mayor 12, Mijas, Málaga, 29650, ITV Guadalhorce"

AGENT: actualizar_datos_personales(datos_personales={
  nombre: "Pepe", apellidos: "Cabeza Cruz", email: "pepe@email.com",
  dni_cif: "77429548W", domicilio_calle: "Calle Mayor 12",
  domicilio_localidad: "Mijas", domicilio_provincia: "Málaga",
  domicilio_cp: "29650", itv_nombre: "ITV Guadalhorce"
})
```

### Fase 4: COLLECT_VEHICLE

```
AGENT: "Necesito los datos del vehículo: marca, modelo, año, matrícula y bastidor (VIN)."

USER: "Honda CBR 1000, 2019, 1234ABC, WVWZZZ3CZWE123456"

AGENT: actualizar_datos_vehiculo(datos_vehiculo={
  marca: "Honda", modelo: "CBR 1000", anio: "2019",
  matricula: "1234ABC", bastidor: "WVWZZZ3CZWE123456"
})
```

### Fase 5: COLLECT_WORKSHOP

```
AGENT: "Para la ITV necesitas un certificado del taller que hizo la instalación.
  ¿Quieres que MSI gestione ese certificado por 85€ +IVA, 
  o tienes tu propio taller registrado?"

USER: "MSI lo gestiona"
AGENT: actualizar_datos_taller(taller_propio=false)
```

### Fase 6: REVIEW_SUMMARY

```
[obtener_estado_expediente() ya llamado automáticamente]

AGENT: Muestra resumen completo:
  ELEMENTOS: Escape (completado, 2 fotos)
  DATOS PERSONALES: Pepe Cabeza Cruz, 77429548W, pepe@email.com, ...
  DATOS VEHÍCULO: Honda CBR 1000 (2019), 1234ABC
  TALLER: MSI gestiona certificado
  PRECIO TOTAL: 250€ + 85€ certificado = 350€ +IVA
  
  "¿Es todo correcto? Confirma o dime qué quieres modificar."

USER: "correcto"
AGENT: finalizar_expediente()
AGENT: "Tu expediente se ha enviado para revisión. Te contactaremos por email."
```

---

## Flow 2b: Resolución de Variantes (sub-flow)

```
[Contexto: identificar_y_resolver_elementos retornó pending_variants]

AGENT: identificar_y_resolver_elementos("motos-part", "suspensión")
  → Retorna: SUSPENSION en elementos_con_variantes, pregunta: "¿Delantera o trasera?"
  → mode_context recibe pending_variants con la pregunta y opciones

AGENT responde:
  "Para la suspensión, ¿es la delantera o la trasera?"
  [NO ofrecer CTA — variantes pendientes bloquean todo excepto seleccionar_variante]

USER: "delantera"

AGENT: seleccionar_variante_por_respuesta("motos-part", "SUSPENSION", "delantera")
  → Retorna: selected_variant: "SUSPENSION_DEL", confidence: 0.95
  [NUNCA llamar identificar_y_resolver_elementos aquí — eso sería re-identificar]

[Si quedan más variantes → repetir. Si todas resueltas → continuar con tarifa]
```

**Reglas clave**:
- Mientras haya variantes pendientes, el ÚNICO tool permitido es `seleccionar_variante_por_respuesta` (+ escalar_a_humano)
- NUNCA re-identificar con la respuesta del usuario
- Si el usuario dice "no entiendo" → explicar en lenguaje simple + re-preguntar con opciones A/B
- Tras 2 intentos sin éxito → escalar a humano

---

## Flow 3: Agregar elementos (edge case)

```
[Contexto: Usuario ya tiene presupuesto de SUBCHASIS a 410€]

USER: "quiero homologar también las agarraderas"

AGENT: identificar_y_resolver_elementos("motos-part", "agarraderas")
  → Retorna: ASIDEROS identificado
AGENT: calcular_tarifa_con_elementos("motos-part", ["SUBCHASIS", "ASIDEROS"], skip_validation=True)
  → Retorna: 410€ (mismo tier incluye ambos)

AGENT responde:
  "Perfecto, mantenemos el subchasis y añadimos los asideros.
  
  DOCUMENTACIÓN DE LOS ASIDEROS:
  - Foto del elemento con matrícula visible
  ⚠️ De no disponer de asideros, se perdería la plaza trasera.
  
  El presupuesto se mantiene en 410€ +IVA — ambos están incluidos en la misma tarifa.
  ¿Quieres ver las fotos de ejemplo del nuevo elemento o abrimos el expediente?"
```

**Reglas clave**:
- Reconocer elementos existentes ("mantenemos X")
- Mostrar SOLO documentación del nuevo elemento
- Recalcular tarifa con TODOS los elementos
- Explicar impacto en precio (cambió o se mantuvo)

---

## Flow 4: Usuario indeciso

```
[Contexto: POST_PRICE, precio comunicado, opciones A/B ofrecidas]

USER: "no sé" / "qué implica abrir el expediente?"

AGENT: "Abrir el expediente significa que empezamos a recopilar tu documentación 
  (fotos del elemento, ficha técnica, datos personales) para gestionar la homologación. 
  Te iré pidiendo las fotos y datos paso a paso. Nosotros nos encargamos del resto.
  ¿Prefieres ver las fotos de ejemplo primero o directamente comenzamos?"

[Si sigue indeciso tras 2 intentos]
AGENT: "¿Te gustaría hablar con alguien del equipo que pueda resolver tus dudas?"
  → escalar_a_humano si acepta
```

---

## Flow 5: Objeción de precio

```
USER: "Es muy caro" / "¿Hay descuento?"

AGENT: "Entiendo, es una inversión importante. El precio incluye el proyecto técnico 
  completo, la gestión administrativa y el acompañamiento hasta la ITV.
  ¿Quieres que te ponga en contacto con el equipo para las opciones?"

[NO inventar descuentos. Si insiste → escalación]
```

---

## Flow 6: Datos parciales en expediente

```
[Contexto: COLLECT_PERSONAL]

USER: "Pepe Cabeza Cruz, pepe@email.com" [falta DNI, domicilio, ITV]

AGENT: actualizar_datos_personales(datos_personales={
  nombre: "Pepe", apellidos: "Cabeza Cruz", email: "pepe@email.com"
})
AGENT: "Datos guardados. Me falta tu DNI/NIE/CIF, dirección completa y nombre de la ITV. 
  Envíamelos cuando los tengas."

[El usuario puede enviar el resto en mensajes posteriores]
```

---

## Flow 7: Volver atrás (edición)

```
[Contexto: REVIEW_SUMMARY]

USER: "Quiero cambiar el email"

AGENT: editar_expediente(seccion="personal")
  → Sistema transiciona a COLLECT_PERSONAL
AGENT: "¿Cuál es tu nuevo email?"

USER: "nuevo@email.com"
AGENT: actualizar_datos_personales(datos_personales={email: "nuevo@email.com"})
  → Auto-retorno a REVIEW_SUMMARY con datos actualizados
```

---

## Flow 8: Escalación

```
USER: "Quiero hablar con una persona"
AGENT: escalar_a_humano(motivo="Usuario solicita asistencia humana", es_error_tecnico=false)
AGENT: "Te pongo en contacto con un agente de MSI."

[Error técnico tras 3+ fallos]
AGENT: "No he podido procesar tu solicitud. Voy a transferirte a un compañero del equipo."
  → escalar_a_humano(motivo="Error técnico", es_error_tecnico=true)
```

---

## Flow 9: Recuperación de sesión (caso pendiente)

```
[Sistema detecta pending_recovery_case al primer mensaje]

AGENT: "¡Hola! Veo que tienes un expediente en curso para [elementos] en fase [fase].
  ¿Qué prefieres?
  A) Continuamos donde lo dejamos
  B) Empezamos de nuevo"

USER: "A" → continuar en sub-modo inferido
USER: "B" → cancelar_expediente() + empezar de cero
```

---

## Flow 10: Recuperación de sesión (caso abandonado)

```
[Sistema detecta pending_abandoned_case]

AGENT: "¡Hola! Tienes un expediente de [elementos] que quedó pendiente.
  ¿Qué prefieres?
  A) Retomamos el expediente
  B) Lo cancelamos y empezamos uno nuevo
  C) Tengo otra consulta"

USER: "A" → reactivar_expediente_abandonado(case_id)
USER: "B" → cancelar + nuevo
USER: "C" → responder consulta, mencionar expediente pendiente
```

---

## CTA State Machine (PRE_EXPEDIENTE)

| Estado | Condiciones | CTA |
|--------|------------|-----|
| Sin elementos | No hay element_codes | "¿Quieres que te ayude con alguna homologación?" |
| Elementos sin precio | element_codes set, precio_comunicado=false | "¿Quieres que te muestre fotos de ejemplo o te calculo un presupuesto?" |
| Precio calculado este turno | tarifa recién calculada | "¿Quieres ver fotos de ejemplo (A) o abrimos el expediente directamente (B)?" |
| Imágenes enviadas | imagenes_enviadas_codigos no vacío | "¿Quieres que abramos el expediente para gestionar tu homologación?" |
| Elemento nuevo añadido | Recálculo hecho | "¿Te envío las fotos del nuevo elemento o abrimos el expediente?" |
| Variantes pendientes | pending_variants sin resolver | NO ofrecer CTA — resolver variantes primero |

---

## Circuit Breakers (qué rompe el flujo)

| Circuit Breaker | Causa | Impacto | Prevención |
|-----------------|-------|---------|------------|
| Re-identificación tras variante | Llamar identificar en vez de seleccionar_variante | Loop infinito | Regla R3 |
| Precio no comunicado | No llamar calcular_tarifa o no incluir en respuesta | Usuario no puede decidir | Regla R1 |
| Imágenes antes de precio | enviar_imagenes sin calcular_tarifa | UX confusa | Regla F1 |
| Datos personales prematuros | Pedir DNI/email en PRE_EXPEDIENTE | Usuario abandona | Regla R5 |
| Saltar datos de elemento | completar sin guardar datos | Expediente incompleto | Regla F4 |
| field_key incorrecto | Inventar keys en guardar_datos_elemento | Datos perdidos silenciosamente | Regla R9 |
| fsm_state vs fsm_state_update | Tool retorna key incorrecta | FSM atascado | Código (no prompt) |
| Finalizar sin éxito | Declarar "enviado" sin finalizar_expediente success | Desinformación | Regla R10 |
| Tool-first violation | Generar texto antes de llamar herramienta | Info desactualizada | Regla R8 |
