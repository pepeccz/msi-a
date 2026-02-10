# Modo: VIABILIDAD_MODE

## 📋 Metadatos

| Campo | Valor |
|-------|-------|
| **Nombre del Modo** | VIABILIDAD_MODE |
| **Código Técnico** | `viabilidad_mode` |
| **Versión** | 1.0 (v2.0) |
| **Fecha** | Febrero 2026 |
| **% Tráfico Esperado** | 65% |
| **Complejidad** | Media |
| **Tipo** | Permisivo (no bloqueante) |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
Evaluar si una modificación específica del usuario puede ser homologada, proporcionando:
1. Verificación de existencia en catálogo
2. Evaluación de compatibilidad vehículo-elemento
3. Verificación de restricciones legales/regulatorias
4. Estimación de rango de precio (no precio exacto)
5. Información de documentación que sería necesaria

### Definición de Éxito
El modo se considera exitoso cuando:
1. **Viabilidad CONFIRMADA**: Elemento existe + es compatible + no hay restricciones → Transición a PRESUPUESTO_MODE
2. **Viabilidad DUDOSA**: Caso complejo que requiere criterio técnico → Escalación a experto
3. **Viabilidad NEGATIVA**: Elemento no existe o está prohibido → Usuario informado, fin de conversación

### Qué NO Hace Este Modo
- ❌ No calcula precios exactos (eso es PRESUPUESTO_MODE)
- ❌ No envía fotos de ejemplo (requiere presupuesto calculado)
- ❌ No recolecta datos del vehículo completos (solo marca/modelo básico)
- ❌ No inicia expedientes formales
- ❌ No resuelve variantes (solo detecta que las hay)

---

## 🔄 Contexto de Navegación

### Modos Predecesores

| Modo Origen | Activador | Condición |
|-------------|-----------|-----------|
| **START** | Clasificador de intención | Intent=evaluar_viabilidad (confidence ≥75%) |
| **CONSULTA_MODE** | Transición natural | Usuario pregunta "¿Se puede homologar X?" |
| **PRESUPUESTO_MODE** | Transición de retorno | Usuario quiere evaluar elemento adicional |

### Modos Sucesores

| Modo Destino | Activador | Condición |
|--------------|-----------|-----------|
| **PRESUPUESTO_MODE** | Viabilidad confirmada + interés | Usuario dice "Sí, quiero saber el precio exacto" |
| **CONSULTA_MODE** | Usuario tiene dudas generales | "Tengo más preguntas sobre el proceso" |
| **ESCALACIÓN** | Caso complejo/dudoso | Sistema detecta que requiere criterio técnico |
| **(END)** | Viabilidad negativa | Elemento no homologable, usuario acepta |

### Transiciones PROHIBIDAS

| A | Razón |
|---|-------|
| **EXPEDIENTE_MODE** | Falta presupuesto calculado y confirmación de precio |
| **EVALUACIÓN_GATEWAY** | No hay presupuesto detallado para confirmar |

---

## 🛠️ Capacidades y Herramientas

### Herramientas Disponibles (7 herramientas)

#### 1. `identificar_elemento`

**Tipo**: Búsqueda en catálogo  
**Propósito**: Buscar elemento en base de datos por descripción del usuario

**Entrada**:
```python
{
    "descripcion": str,        # "escape", "suspensión delantera", etc.
    "categoria_slug": str | None,  # "motos-part" (si se conoce)
    "fuzzy_matching": bool     # True (default) - permite coincidencias parciales
}
```

**Salida**:
```python
{
    "elemento_encontrado": bool,
    "elemento": {
        "codigo": str,         # "ESCAPE"
        "nombre": str,         # "Escape"
        "descripcion": str,
        "categoria": str,      # "motos-part"
        "tiene_variantes": bool,
        "variantes_posibles": list[str] | None,  # ["moto", "quad"] si aplica
    } | None,
    "alternativas": list[dict],  # Elementos similares si no hay coincidencia exacta
    "confianza": float           # 0.0-1.0 de la coincidencia
}
```

**Reglas de Negocio**:
- Si `confianza < 0.6`: Mostrar alternativas y preguntar cuál se refiere
- Si no se encuentra: Buscar elementos similares por keywords
- NO resolver variantes en este paso (solo detectar que existen)

**Modelo de Datos Usado**:
- `Element` (búsqueda por `keywords`, `aliases`, `name`)
- `VehicleCategory` (filtro por categoría)

---

#### 2. `evaluar_compatibilidad`

**Tipo**: Evaluación técnica  
**Propósito**: Verificar si elemento es compatible con vehículo específico

**Entrada**:
```python
{
    "elemento_codigo": str,    # "ESCAPE"
    "vehiculo_marca": str,     # "Yamaha"
    "vehiculo_modelo": str,    # "MT-07"
    "vehiculo_anio": int | None,  # 2020 (opcional)
}
```

**Salida**:
```python
{
    "compatible": bool,
    "nivel_confianza": str,    # "alta" | "media" | "baja"
    "notas_compatibilidad": str,
    "restricciones": list[dict],  # Si hay limitaciones
    "requiere_inspeccion": bool,  # Si necesita verificación física
}
```

**Reglas de Negocio**:
- Usar `classification_rules` de `TariffTier` para validaciones
- Si `requiere_inspeccion=True`: Preparar escalación técnica
- Marcar nivel de confianza basado en data disponible

**Modelo de Datos Usado**:
- `Element` (verificar `inherit_parent_data` si aplica)
- `TariffTier.classification_rules` (validaciones específicas)

---

#### 3. `verificar_restricciones`

**Tipo**: Validación legal/regulatoria  
**Propósito**: Verificar restricciones legales para elemento en categoría

**Entrada**:
```python
{
    "elemento_codigo": str,
    "categoria_slug": str,
}
```

**Salida**:
```python
{
    "restricciones": list[{
        "tipo": str,           # "legal", "tecnica", "documentacion"
        "severidad": str,      # "info", "warning", "bloqueante"
        "descripcion": str,    # Mensaje para usuario
        "condicion": str | None,  # Cuándo aplica (ej: "potencia > 100cv")
    }],
    "bloqueante": bool,        # True si hay restricción que impide homologación
    "requiere_verificacion_adicional": bool,
}
```

**Reglas de Negocio**:
- Si `bloqueante=True`: NO ofrecer presupuesto, informar claramente
- Incluir warnings de `Warning` con `trigger_conditions` que apliquen
- Considerar `ElementWarningAssociation` para mostrar condiciones

**Modelo de Datos Usado**:
- `Warning` (filtrar por `element_id` o `category_id`)
- `ElementWarningAssociation` (condiciones específicas)

---

#### 4. `consultar_documentacion`

**Tipo**: Consulta de requisitos  
**Propósito**: Informar qué documentación sería necesaria (sin enviar fotos aún)

**Entrada**:
```python
{
    "elemento_codigo": str,
    "categoria_slug": str,
}
```

**Salida**:
```python
{
    "documentacion_base": list[str],  # ["Ficha técnica", "Permiso de circulación"]
    "documentacion_elemento": list[{  # Específica del elemento
        "tipo": str,               # "foto_placa", "foto_instalada", "manual"
        "descripcion": str,
        "cantidad_minima": int,
    }],
    "complejidad_documentacion": str,  # "baja", "media", "alta"
}
```

**Reglas de Negocio**:
- NO enviar fotos de ejemplo todavía (eso es PRESUPUESTO_MODE)
- Solo describir textualmente qué se necesitaría
- Usar para calcular "complejidad" del caso

**Modelo de Datos Usado**:
- `BaseDocumentation` (docs base por categoría)
- `ElementImage` (con `image_type="required_document"`)

---

#### 5. `calcular_estimacion_rapida`

**Tipo**: Estimación de rango  
**Propósito**: Dar rango amplio de precio (no precio exacto)

**Entrada**:
```python
{
    "elemento_codigo": str,
    "categoria_slug": str,
    "incluye_proyecto": bool,  # Si requiere proyecto de ingeniería
}
```

**Salida**:
```python
{
    "estimacion_disponible": bool,
    "rango_min": Decimal,      # Ej: 180.00
    "rango_max": Decimal,      # Ej: 450.00
    "incluye_iva": bool,       # False (siempre precios sin IVA)
    "factores_variacion": list[str],  # Por qué hay rango amplio
    "para_precio_exacto": str, # Mensaje: "Para precio exacto necesito confirmar variantes"
}
```

**Reglas de Negocio**:
- Usar `TariffTier` para determinar rango según complejidad estimada
- Siempre incluir disclaimer: "Estimación preliminar, precio exacto requiere evaluación detallada"
- NUNCA comprometer precio específico en este modo

**Modelo de Datos Usado**:
- `TariffTier` (precios base por tier)
- `TierElementInclusion` (qué tiers incluyen el elemento)

---

#### 6. `transicion_a_presupuesto`

**Tipo**: Transición de modo  
**Propósito**: Mover conversación a PRESUPUESTO_MODE con contexto

**Entrada**:
```python
{
    "elementos_tentativos": list[str],  # ["ESCAPE"]
    "vehiculo_info": dict,     # {"marca": "Yamaha", "modelo": "MT-07"}
    "categoria_slug": str,
    "viabilidad_confirmada": bool,
}
```

**Salida**:
```python
{
    "transicion_permitida": bool,
    "nuevo_modo": "presupuesto_mode",
    "contexto_preservado": dict,  # Datos de viabilidad para PRESUPUESTO_MODE
    "mensaje_transicion": str,
}
```

**Reglas de Negocio**:
- Solo permitir si `viabilidad_confirmada=True`
- Preservar elementos tentativos y vehículo mencionado
- Mensaje de transición debe ser natural

---

#### 7. `escalar_a_humano` (Universal)

**Entrada/Salida**: Igual que en CONSULTA_MODE  
**Uso específico**: Casos técnicamente complejos o dudosos

---

### Herramientas NO Disponibles

| Herramienta | Razón | Dónde Está |
|-------------|-------|------------|
| `calcular_tarifa_con_elementos` | Requiere elementos confirmados con variantes resueltas | PRESUPUESTO_MODE |
| `enviar_imagenes_ejemplo` | Requiere presupuesto calculado | PRESUPUESTO_MODE |
| `seleccionar_variante_por_respuesta` | Resolución de variantes es parte de presupuesto detallado | PRESUPUESTO_MODE |
| `iniciar_expediente` | Falta presupuesto aceptado | EVALUACIÓN_GATEWAY |

---

## 📊 Datos del Modo

### Datos de Entrada

| Dato | Tipo | Obligatorio | Fuente | Descripción |
|------|------|-------------|--------|-------------|
| `user_phone` | str | Sí | Metadata | Teléfono E.164 |
| `client_type` | str | Sí | Config | particular/professional |
| `conversation_id` | UUID | Sí | Sistema | ID de conversación |
| `categoria_interes` | str | No | CONSULTA_MODE | Si vino de consulta |
| `elementos_mencionados` | list | No | CONSULTA_MODE | Elementos previos |

### Datos Temporales (Contexto de Viabilidad)

| Dato | Tipo | Duración | Descripción |
|------|------|----------|-------------|
| `elemento_tentativo` | dict | Sesión | Elemento que estamos evaluando |
| `vehiculo_tentativo` | dict | Sesión | Marca/modelo mencionados |
| `resultado_compatibilidad` | dict | Sesión | Resultado de evaluación |
| `restricciones_encontradas` | list | Sesión | Warnings aplicables |
| `estimacion_precio` | dict | Sesión | Rango calculado |

### Datos de Salida (Para PRESUPUESTO_MODE)

| Dato | Tipo | Descripción |
|------|------|-------------|
| `elementos_preseleccionados` | list[str] | Códigos de elementos viables |
| `vehiculo_preseleccionado` | dict | Marca/modelo/año confirmados |
| `categoria_confirmada` | str | Slug de categoría |
| `viabilidad_resultado` | str | "confirmada" | "dudosa" | "negativa" |

---

## 📜 Reglas de Negocio

### Flujo Estándar de Viabilidad

1. **Identificación** (obligatorio)
   - Usuario menciona elemento → `identificar_elemento()`
   - Si no encontrado → Mostrar alternativas o escalar

2. **Compatibilidad** (si menciona vehículo)
   - Usuario menciona marca/modelo → `evaluar_compatibilidad()`
   - Si no menciona → Preguntar antes de continuar

3. **Restricciones** (obligatorio)
   - Verificar `verificar_restricciones()`
   - Si `bloqueante=True` → Informar y NO continuar

4. **Documentación** (opcional, para completitud)
   - Consultar complejidad documental
   - Usar para determinar si caso es simple o complejo

5. **Estimación** (opcional, para interés)
   - Si usuario pregunta precio: `calcular_estimacion_rapida()`
   - Enfatizar: "Para precio exacto necesito más detalles"

6. **Transición o Escalación**
   - Todo viable → Ofrecer presupuesto detallado → PRESUPUESTO_MODE
   - Complejo → Escalar a técnico
   - No viable → Informar claramente

### Reglas de Detección de Complejidad

| Situación | Acción |
|-----------|--------|
| Elemento estándar + vehículo común | Ruta simple → PRESUPUESTO_MODE |
| Elemento con variantes complejas | Ruta estándar → PRESUPUESTO_MODE (resolverá variantes) |
| Restricciones técnicas específicas | Escalar a técnico |
| Vehículo modificado extensivamente | Escalar a técnico |
| Elemento no estándar/catálogo | Escalar a técnico |

---

## 🚨 Política de Reintentos y Timeouts

### Timeout de Inactividad

| Tiempo | Acción | Mensaje |
|--------|--------|---------|
| **15 minutos** | Nudge | "¿Seguís evaluando la modificación? Respondé para continuar." |
| **30 minutos** | Reset a CONSULTA_MODE | "Reiniciamos. ¿En qué puedo ayudarte?" |

### Política de Reintentos

| Situación | Máximo | Acción |
|-----------|--------|--------|
| No se encuentra elemento buscado | 3 intentos | Escalar con transcripción completa |
| Compatibilidad incierta | 2 intentos | Escalar a técnico |
| Usuario no especifica vehículo | 2 intentos | "¿Me podés indicar marca y modelo?" |

---

## 🎭 Casos de Uso

### Caso 1: Viabilidad Confirmada Simple

```
Usuario: ¿Se puede homologar un escape en una Yamaha MT-07?

Agente: [VIABILIDAD_MODE - identificar_elemento("escape", categoria="motos-part")]
       ✓ Encontré el elemento "Escape" en nuestro catálogo.

Agente: [VIABILIDAD_MODE - evaluar_compatibilidad("ESCAPE", "Yamaha", "MT-07")]
       ✓ Es compatible con tu Yamaha MT-07.

Agente: [VIABILIDAD_MODE - verificar_restricciones("ESCAPE", "motos-part")]
       Revisé las restricciones: no hay limitaciones específicas.

Agente: [VIABILIDAD_MODE - calcular_estimacion_rapida("ESCAPE", "motos-part")]
       Estimación de precio: entre 180€ y 350€ (sin IVA).
       El precio exacto depende del tipo específico de escape.

       ¿Te gustaría que calcule un presupuesto exacto?

Usuario: Sí, por favor

Agente: [TRANSICIÓN → PRESUPUESTO_MODE]
       Perfecto, paso a calcular tu presupuesto exacto...
```

**Resultado**: Viabilidad confirmada, usuario quiere presupuesto detallado.

---

### Caso 2: Elemento con Variantes Detectadas

```
Usuario: ¿Se puede homologar una suspensión?

Agente: [VIABILIDAD_MODE - identificar_elemento("suspensión")]
       ✓ Encontré "Suspensión" en el catálogo.
       
       Veo que hay diferentes variantes: delantera, trasera, o kits completos.
       También varía según el tipo de conducción (carretera, off-road, mixta).

       Para evaluar la viabilidad específica, ¿me podés indicar:
       1. ¿Es para moto, quad, o coche?
       2. ¿Suspensión delantera, trasera, o ambas?

Usuario: Es para mi moto, la delantera

Agente: [VIABILIDAD_MODE - evaluar_compatibilidad("SUSPENSION_DEL", ...)]
       ✓ Suspensión delantera para moto es homologable.

       Estimación: entre 200€ y 500€ según marca y características.

       ¿Quieres el presupuesto exacto?

Usuario: Sí

Agente: [TRANSICIÓN → PRESUPUESTO_MODE con contexto de variante]
```

**Resultado**: Variantes detectadas pero no resueltas (eso es en PRESUPUESTO_MODE).

---

### Caso 3: Viabilidad Negativa (Restricción Bloqueante)

```
Usuario: ¿Se puede homologar un turbo en una moto 125cc?

Agente: [VIABILIDAD_MODE - identificar_elemento("turbo")]
       ✓ Encontré el elemento "Turbo".

Agente: [VIABILIDAD_MODE - evaluar_compatibilidad("TURBO", ...)]
       ⚠️ Encontré una restricción importante:
       
       Los turbos en motos de 125cc están limitados por normativa 
       Euro 5. Solo se pueden homologar en motos con cilindrada 
       superior a 300cc o con certificación específica de fábrica.

       Tu moto de 125cc no cumple con los requisitos técnicos 
       para esta modificación.

       ¿Te gustaría que te indique otras modificaciones que sí 
       se pueden hacer en tu moto 125cc?

Usuario: No, gracias. Es lo que quería saber.

Agente: [FIN DE CONVERSACIÓN]
       Entendido. Si en el futuro cambiás de moto o tenés otra 
       consulta, acá estoy para ayudarte.
```

**Resultado**: Viabilidad negativa informada claramente, usuario satisfecho.

---

### Caso 4: Caso Complejo → Escalación

```
Usuario: Quiero homologar una preparación completa de circuito
        en mi coche de calle

Agente: [VIABILIDAD_MODE - identificar_elemento]
       Detecto múltiples elementos involucrados y modificaciones 
       extensivas.

       Este tipo de preparación requiere evaluación técnica detallada:
       - Proyecto de ingeniería individual
       - Homologación individual (no por elemento)
       - Inspección técnica previa obligatoria

       Te voy a conectar con uno de nuestros técnicos especialistas 
       que puede evaluar tu caso específico.

       [ESCALACIÓN a técnico con contexto completo]
```

**Resultado**: Escalación proactiva por complejidad técnica.

---

## 📁 Prompt del Sistema

```markdown
## MODO: EVALUACION_VIABILIDAD

Eres un asistente de MSI Automotive en modo EVALUACIÓN DE VIABILIDAD.
Tu objetivo: Determinar si una modificación específica puede ser homologada.

### Proceso de Evaluación (en orden)
1. Identificar el elemento en catálogo
2. Evaluar compatibilidad con vehículo (si se mencionó)
3. Verificar restricciones legales/regulatorias
4. Estimar rango de precio (NO precio exacto)

### Herramientas Disponibles
- identificar_elemento: Buscar elemento en catálogo
- evaluar_compatibilidad: Verificar compatibilidad vehículo-elemento
- verificar_restricciones: Chequear limitaciones legales
- consultar_documentacion: Qué documentación sería necesaria
- calcular_estimacion_rapida: Rango de precio estimado
- transicion_a_presupuesto: Cuando viabilidad está confirmada
- escalar_a_humano: Casos complejos

### Reglas CRÍTICAS
1. NO des precios exactos (solo rangos estimados)
2. NO envíes fotos de ejemplo todavía
3. Detecta variantes pero NO las resuelvas (eso es en presupuesto)
4. Si hay restricción bloqueante: informar claramente y NO continuar
5. Casos complejos: escalar a técnico, no intentar evaluar solo

### Transiciones
- Viabilidad confirmada → Ofrecer presupuesto detallado → PRESUPUESTO_MODE
- Caso complejo → Escalar a técnico
- Viabilidad negativa → Informar y terminar

### Estilo
- Técnico pero accesible
- Transparente sobre limitaciones
- Proactivo en detectar casos complejos
```

---

## 📊 Métricas

| Métrica | Objetivo | Alerta |
|---------|----------|--------|
| Tiempo promedio | <5 min | >8 min |
| Tasa de confirmación | >70% | <50% |
| Tasa de escalación técnica | <10% | >20% |
| Elementos no encontrados | <5% | >15% |

---

## 📚 Relaciones

- **Anterior**: [03-modo-consulta.md](03-modo-consulta.md)
- **Siguiente**: [05-modo-presupuesto.md](05-modo-presupuesto.md)
- **Database**: Element, TariffTier, Warning

---

**Documento detallado para VIABILIDAD_MODE**  
**Estado**: Listo para desarrollo
