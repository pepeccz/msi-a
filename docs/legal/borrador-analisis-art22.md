# Análisis de Decisiones Automatizadas y Elaboración de Perfiles
## Art. 22 RGPD — MSI-a Sistema de IA Agéntica

**Versión**: 1.0 (BORRADOR — pendiente validación abogado RGPD)  
**Fecha**: Febrero 2026  
**Responsable del tratamiento**: MSI Automotive S.L.  
**Encargado del tratamiento**: Zanovix (agencia de desarrollo)  
**Redactado por**: Zanovix (para revisión y firma de MSI Automotive S.L.)  
**Clasificación**: ⚖️ Requiere validación jurídica externa  

---

> ⚠️ **NOTA LEGAL IMPORTANTE**
>
> Este documento es un **borrador técnico** redactado por Zanovix en su calidad de encargado del tratamiento.
> Antes de ser utilizado como documento legal válido, **debe ser revisado y validado por un abogado especialista en RGPD**,
> y posteriormente **aprobado y firmado por MSI Automotive S.L.** como responsable del tratamiento.

---

## Índice

1. [Marco Normativo](#1-marco-normativo)
2. [Descripción del Sistema MSI-a](#2-descripción-del-sistema-msi-a)
3. [Identificación de Procesos Automatizados](#3-identificación-de-procesos-automatizados)
4. [Análisis por Proceso — ¿Aplica el Art. 22?](#4-análisis-por-proceso--aplica-el-art-22)
5. [Conclusión: ¿MSI-a cae bajo el Art. 22 RGPD?](#5-conclusión-msi-a-cae-bajo-el-art-22-rgpd)
6. [Garantías Implementadas](#6-garantías-implementadas)
7. [Garantías Adicionales Recomendadas](#7-garantías-adicionales-recomendadas)
8. [Información a los Interesados](#8-información-a-los-interesados)
9. [Registro y Mantenimiento](#9-registro-y-mantenimiento)
10. [Aprobación](#10-aprobación)

---

## 1. Marco Normativo

### 1.1 Art. 22 RGPD — Texto Literal

> **Art. 22.1**: "Todo interesado tendrá derecho a no ser objeto de una decisión basada únicamente en el tratamiento automatizado, incluida la elaboración de perfiles, que produzca efectos jurídicos en él o le afecte significativamente de modo similar."
>
> **Art. 22.2**: Dicho derecho no se aplicará cuando la decisión:
> - (a) sea necesaria para la celebración o la ejecución de un contrato entre el interesado y el responsable del tratamiento;
> - (b) esté autorizada por el Derecho de la Unión o los Estados miembros;
> - **(c) se base en el consentimiento explícito del interesado**.
>
> **Art. 22.3**: En los casos de 22.2.a) y 22.2.c), el responsable del tratamiento adoptará las medidas adecuadas para salvaguardar los derechos y libertades y los intereses legítimos del interesado.
>
> **Art. 22.4**: Las decisiones del apartado 2 no podrán basarse en las categorías especiales de datos del Art. 9, salvo que exista consentimiento explícito o razones de interés público (con medidas adecuadas).

### 1.2 Definición de Elaboración de Perfiles (Art. 4.4 RGPD)

> "Toda forma de tratamiento automatizado de datos personales consistente en utilizar datos personales para evaluar determinados aspectos personales de una persona física, en particular para **analizar o predecir aspectos relativos al rendimiento profesional, situación económica, salud, preferencias personales, intereses, fiabilidad, comportamiento, ubicación o movimientos** de dicha persona."

### 1.3 Criterios EDPB para "Afectación Significativa"

Las **Directrices 03/2017 del WP29** (ahora EDPB) sobre decisiones automatizadas establecen que una decisión afecta "significativamente" cuando:
- Produce efectos jurídicos (cambios en derechos, obligaciones, relaciones contractuales)
- Afecta a las circunstancias, el comportamiento o las opciones de las personas de modo considerable
- Influye de manera duradera en las perspectivas de la persona
- Conlleva efectos discriminatorios

### 1.4 Orientaciones AEPD — IA Agéntica (Febrero 2026)

Las Orientaciones de la AEPD sobre IA Agéntica y Protección de Datos (febrero 2026) destacan:
- Los sistemas de IA agéntica pueden tomar decisiones con consecuencias significativas para los interesados
- Debe evaluarse si las interacciones constituyen "perfilado" en el sentido del Art. 4.4 RGPD
- La autonomía del agente no elimina la responsabilidad del responsable del tratamiento

---

## 2. Descripción del Sistema MSI-a

### 2.1 Funcionalidad Principal

MSI-a es un **agente conversacional de IA** que atiende consultas de clientes por WhatsApp para MSI Automotive S.L. (empresa de homologaciones de vehículos en España).

**Funciones principales**:
- Información sobre servicios de homologación de vehículos
- Cálculo de presupuestos de homologación
- Recopilación de datos para apertura de expedientes
- Escalado a agentes humanos

### 2.2 Arquitectura del Sistema

```
Usuario WhatsApp → Chatwoot → API MSI-a → LangGraph Agent
                                              ↓
                                    Intent Router (IA)
                                    ↙        ↓        ↘
                              CONSULTA  PRESUPUESTO  EXPEDIENTE
                                              ↓
                                    LLM (Tier 1/2/3)
                                              ↓
                                    Respuesta → WhatsApp
```

**Modos de operación**:
| Modo | Función |
|------|---------|
| `CONSULTA_MODE` | Responde preguntas educativas sobre homologaciones |
| `PRESUPUESTO_MODE` | Calcula presupuestos basados en tipo de vehículo/modificaciones |
| `EVALUACION_GATEWAY` | Confirma si el usuario quiere continuar |
| `EXPEDIENTE_MODE` | Recoge datos para apertura de expediente formal |
| `ESCALATION` | Transfiere a agente humano |

### 2.3 Datos Procesados

| Dato | Fuente | Uso en el sistema |
|------|--------|-------------------|
| Número de teléfono WhatsApp | Chatwoot | Identificador del usuario |
| Mensajes de conversación | WhatsApp | Input para LLM |
| Tipo de vehículo | Conversación | Cálculo de tarifa |
| Elementos de homologación solicitados | Conversación | Cálculo de tarifa |
| Historial de conversación | Redis/PostgreSQL | Contexto para LLM |
| Intención del usuario | Clasificador IA | Routing de modo |

---

## 3. Identificación de Procesos Automatizados

### 3.1 Mapa de Decisiones Automatizadas en MSI-a

| ID | Proceso | Automatización | Datos usados | Consecuencia para el interesado |
|----|---------|---------------|-------------|----------------------------------|
| **DA-01** | Clasificación de intención del usuario | IA (LangGraph Router) | Texto del mensaje | Qué modo/respuesta recibe |
| **DA-02** | Cálculo de presupuesto de homologación | Algoritmo determinista (tarifas fijas) | Tipo vehículo, elementos | Precio informado al usuario |
| **DA-03** | Decisión de escalar a humano | IA + reglas | Contexto conversación | Acceso a agente humano |
| **DA-04** | Selección de nivel LLM (Tier 1/2/3) | Reglas automáticas | Tipo de tarea | Calidad de respuesta |
| **DA-05** | Detección de digresión | IA | Historial conversación | Continuidad del modo |
| **DA-06** | Identificación de elementos de homologación | IA (NLP + fuzzy) | Descripción usuario | Qué elementos se incluyen en presupuesto |
| **DA-07** | Recopilación de datos expediente | IA (modo EXPEDIENTE) | Datos del vehículo/usuario | Apertura de expediente formal |

---

## 4. Análisis por Proceso — ¿Aplica el Art. 22?

Para que el Art. 22.1 RGPD aplique, deben cumplirse **tres condiciones simultáneamente**:
1. ✅ Decisión basada **únicamente** en tratamiento automatizado
2. ✅ Incluye **elaboración de perfiles** (no necesariamente, pero la decisión automatizada sí)
3. ✅ Produce **efectos jurídicos** o afecta **significativamente** al interesado

### DA-01: Clasificación de Intención del Usuario

| Factor | Análisis |
|--------|----------|
| ¿Exclusivamente automatizada? | ✅ Sí — LangGraph router sin intervención humana |
| ¿Produce efectos jurídicos? | ❌ No — solo determina el modo de conversación |
| ¿Afecta significativamente? | ❌ No — el usuario puede reformular y cambiar de modo |
| ¿Elaboración de perfiles? | Mínima — solo para el contexto de esa sesión |

**Conclusión DA-01**: **No aplica Art. 22.1 RGPD**. La clasificación de intención es una decisión de gestión de la conversación sin efectos significativos para el interesado.

### DA-02: Cálculo de Presupuesto de Homologación

| Factor | Análisis |
|--------|----------|
| ¿Exclusivamente automatizada? | ✅ Sí — las tarifas son fijas y el cálculo es algorítmico |
| ¿Produce efectos jurídicos? | ❓ Potencialmente — el presupuesto puede ser la base de una decisión económica del usuario |
| ¿Afecta significativamente? | ⚠️ Posiblemente — determina el precio que se comunica al usuario |
| ¿Elaboración de perfiles? | ❌ No — las tarifas son fijas por tipo de homologación |

**Análisis detallado**:
- Las tarifas de MSI-a son **fijas y públicas** (definidas en la base de datos `tariff_tiers`)
- El cálculo es **determinista**: dados los mismos elementos de homologación, el precio es siempre el mismo para cualquier usuario
- **No hay personalización por características del usuario** (edad, historial, etc.)
- El precio calculado es una **información**, no una decisión vinculante

**Conclusión DA-02**: **No aplica Art. 22.1 RGPD en sentido estricto**. El cálculo aplica tarifas objetivas y uniformes sin perfilado del individuo. Es análogo a un calculador de precios online con tarifas públicas.

Sin embargo, **se recomienda** incluir información sobre el proceso en la política de privacidad como buena práctica.

### DA-03: Decisión de Escalar a Agente Humano

| Factor | Análisis |
|--------|----------|
| ¿Exclusivamente automatizada? | ⚠️ Parcialmente — el usuario también puede pedir escalado |
| ¿Produce efectos jurídicos? | ❌ No en sentido estricto |
| ¿Afecta significativamente? | ⚠️ Podría — si el sistema no escala cuando debería, el usuario no recibe asistencia adecuada |
| ¿Elaboración de perfiles? | ❌ No — se basa en el contenido del mensaje, no en perfil del usuario |

**Conclusión DA-03**: **No aplica Art. 22.1 RGPD**. La escalada es una función de gestión de conversación. El usuario siempre puede solicitar explícitamente hablar con un humano (tool `escalar_a_humano`).

### DA-04: Selección de Nivel LLM

| Factor | Análisis |
|--------|----------|
| ¿Exclusivamente automatizada? | ✅ Sí |
| ¿Produce efectos jurídicos? | ❌ No |
| ¿Afecta significativamente? | ❌ No directamente perceptible por el usuario |
| ¿Elaboración de perfiles? | ❌ No |

**Conclusión DA-04**: **No aplica Art. 22.1 RGPD**. Es una decisión de infraestructura técnica invisible para el usuario.

### DA-05: Detección de Digresión

| Factor | Análisis |
|--------|----------|
| ¿Exclusivamente automatizada? | ✅ Sí |
| ¿Produce efectos jurídicos? | ❌ No |
| ¿Afecta significativamente? | ❌ Mínimamente — puede afectar fluidez de conversación |
| ¿Elaboración de perfiles? | ❌ No |

**Conclusión DA-05**: **No aplica Art. 22.1 RGPD**.

### DA-06: Identificación de Elementos de Homologación

| Factor | Análisis |
|--------|----------|
| ¿Exclusivamente automatizada? | ✅ Sí — NLP + fuzzy matching |
| ¿Produce efectos jurídicos? | ⚠️ Indirectamente — determina qué se incluye en el presupuesto |
| ¿Afecta significativamente? | ⚠️ Sí — si se identifican mal los elementos, el presupuesto puede ser incorrecto |
| ¿Elaboración de perfiles? | ❌ No — se basa en el texto del mensaje |

**Análisis detallado**:
- La identificación incorrecta de elementos puede llevar a presupuestos incorrectos
- Sin embargo, el sistema siempre **presenta la identificación al usuario para confirmación** antes de calcular el presupuesto
- El usuario puede corregir y el sistema reformula
- Existe supervisión humana implícita en el flujo (EVALUACION_GATEWAY)

**Conclusión DA-06**: **No aplica Art. 22.1 RGPD** porque la identificación automatizada siempre se valida con el usuario antes de tener efectos. Sin embargo, se recomienda reforzar la presentación de la confirmación.

### DA-07: Recopilación de Datos para Expediente

| Factor | Análisis |
|--------|----------|
| ¿Exclusivamente automatizada? | ✅ Sí — el agente decide qué datos pedir y cómo |
| ¿Produce efectos jurídicos? | ✅ Sí — puede llevar a la apertura de un expediente formal de homologación |
| ¿Afecta significativamente? | ✅ Sí — implica inicio de un proceso administrativo y económico |
| ¿Elaboración de perfiles? | ❌ No — recopila datos específicos del expediente, no perfila al usuario |

**Análisis detallado**:
- El EXPEDIENTE_MODE recoge datos para abrir un expediente formal de homologación
- Sin embargo, la **apertura del expediente no se produce automáticamente** — requiere revisión y validación por parte del equipo de MSI Automotive
- El agente actúa como **recogida de datos preliminar**, no como decisión final
- Existe un humano (equipo MSI Automotive) que valida y aprueba el expediente

**Conclusión DA-07**: **No aplica Art. 22.1 RGPD** porque la decisión de abrir el expediente involucra revisión humana de MSI Automotive. La IA solo recopila datos; la decisión la toma un humano.

---

## 5. Conclusión: ¿MSI-a cae bajo el Art. 22 RGPD?

### 5.1 Conclusión General

**El sistema MSI-a, tal como está diseñado actualmente, NO produce decisiones que caigan bajo el Art. 22.1 RGPD** por las siguientes razones:

1. **Sin efectos jurídicos directos**: Ningún proceso de MSI-a genera automáticamente consecuencias jurídicas (contratos, denegaciones, obligaciones) sin intervención humana posterior.

2. **Sin afectación significativa autónoma**: Las respuestas del agente son información y orientación, no decisiones vinculantes. El usuario siempre puede reformular, preguntar de nuevo o solicitar asistencia humana.

3. **Sin elaboración de perfiles individualizada**: El sistema no construye perfiles de usuarios basados en características personales para personalizar el trato. Las tarifas son uniformes para todos los usuarios.

4. **Supervisión humana disponible**: MSI Automotive revisa los expedientes antes de cualquier acción con consecuencias.

### 5.2 Escenarios de Riesgo Futuros

Sin embargo, si MSI-a evoluciona para incluir las siguientes funcionalidades, **sería necesario re-evaluar**:

| Funcionalidad Futura | Riesgo Art. 22 |
|----------------------|----------------|
| Denegación automática de presupuestos | ⚠️ Alto |
| Scoring/calificación de clientes | ⚠️ Alto |
| Personalización de precios por perfil de usuario | ⚠️ Alto |
| Decisión automática de apertura de expediente sin revisión humana | ⚠️ Alto |
| Detección automática de fraude con consecuencias | ⚠️ Alto |

### 5.3 Posición de Cautela Recomendada

Aunque la conclusión es que el Art. 22.1 no aplica actualmente, **se recomienda adoptar una posición de cautela** dado que:

1. El EDPB puede interpretar de manera más amplia el concepto de "afectación significativa"
2. Las Orientaciones AEPD 2026 sobre IA agéntica destacan la necesidad de evaluar continuamente
3. El umbral de "afectación significativa" puede ser subjetivo en algunos casos

**Posición de cautela**: Actuar **como si el Art. 22 aplicara** para los procesos DA-02 y DA-06 adoptando las garantías del Art. 22.3 RGPD (información, intervención humana, impugnación) aunque estrictamente no sean obligatorias.

---

## 6. Garantías Implementadas

MSI-a ya cuenta con varias garantías que serían exigibles si el Art. 22 aplicara:

### 6.1 Supervisión Humana

| Garantía | Implementación Técnica | Adecuación |
|----------|----------------------|------------|
| **Escalado a agente humano** | Tool `escalar_a_humano` en todos los modos | ✅ Completo |
| **Modo ESCALATION** | Modo dedicado a transferencia a humano | ✅ Completo |
| **Revisión humana de expedientes** | Equipo MSI Automotive valida expedientes | ✅ Completo |
| **Panel de administración** | Admin panel para supervisión | ✅ Completo |

### 6.2 Transparencia

| Garantía | Implementación Técnica | Adecuación |
|----------|----------------------|------------|
| **Identificación como IA** | Prompt `02_identity.md` | ⚠️ Solo en prompt, no hardcodeado |
| **Información sobre uso de IA** | Aviso primera interacción (pendiente implementar) | ❌ Pendiente |
| **Explicación de decisiones** | El agente puede explicar su razonamiento | ✅ Parcial |

### 6.3 Exactitud y Corrección

| Garantía | Implementación Técnica | Adecuación |
|----------|----------------------|------------|
| **Confirmación antes de calcular** | EVALUACION_GATEWAY | ✅ Completo |
| **Posibilidad de corrección** | Usuario puede reformular en cualquier momento | ✅ Completo |
| **Historial de conversación** | Contexto completo disponible | ✅ Completo |

---

## 7. Garantías Adicionales Recomendadas

### 7.1 Para Aumentar la Robustez del Compliance

#### GAR-01: Cláusula de "Derecho a Intervención Humana" en Aviso Inicial

Incluir en el aviso de primera interacción una mención explícita al derecho de solicitar revisión humana:

```
"Puedes solicitar hablar con un agente humano en cualquier momento 
escribiendo 'quiero hablar con una persona'."
```

**Dónde implementar**: `agent/prompts/core/02_identity.md` + aviso primera interacción  
**Estado**: Parcialmente en prompts; pendiente en aviso inicial

#### GAR-02: Hardcodear Identificación como IA

La identificación del sistema como IA no debe depender solo del prompt del LLM (que puede variar). Debe estar hardcodeada en el código:

```python
# En agent/modes/presupuesto_mode.py
FIRST_MESSAGE_PREFIX = (
    "Soy el asistente virtual de MSI Automotive. "
    "Soy una inteligencia artificial y no soy un agente humano. "
)
```

**Estado**: ❌ Pendiente implementación (QW-01 del plan de compliance)

#### GAR-03: Registro de Decisiones Automatizadas

Ampliar el sistema de `tool_call_logs` para registrar explícitamente las decisiones más importantes:

```python
# En tool_logging_service.py — ampliar para incluir:
{
    "decision_type": "tariff_calculation",
    "input_data": {"elements": [...], "category": "..."},
    "output_data": {"price": 450.00},
    "timestamp": "...",
    "conversation_id": "...",
    "is_automated": True
}
```

**Estado**: ⚠️ Parcialmente implementado (tool_call_logs existe pero no distingue tipo de decisión)

#### GAR-04: Mecanismo de Impugnación

Implementar un mecanismo claro para que el usuario pueda impugnar el resultado del cálculo:

- El usuario puede preguntar "¿por qué ese precio?"
- El agente debe poder explicar qué elementos se incluyen y su tarifa
- Debe existir un canal para disputar el presupuesto (email o humano)

**Estado**: ⚠️ Parcialmente (el agente puede explicar, pero no hay canal formal de impugnación)

---

## 8. Información a los Interesados

### 8.1 Información Mínima sobre Procesos Automatizados

Conforme al Art. 13.2.f RGPD, si hubiera decisiones automatizadas, los interesados deben ser informados de:
- La existencia de decisiones automatizadas
- La lógica aplicada
- Las consecuencias previstas

Aunque concluimos que el Art. 22.1 no aplica estrictamente, **se recomienda incluir en la Política de Privacidad** la siguiente información:

```markdown
## Uso de Inteligencia Artificial

MSI Automotive utiliza un sistema de inteligencia artificial (MSI-a) para 
atender consultas a través de WhatsApp. Este sistema:

**Procesos automatizados que realiza:**
- Clasifica su consulta para dirigirla al proceso adecuado
- Calcula presupuestos de homologación aplicando tarifas fijas y públicas
- Recopila información para preparar expedientes

**Lo que NO hace automáticamente:**
- No toma decisiones jurídicamente vinculantes sin revisión humana
- No personaliza precios según características personales
- No aplica elaboración de perfiles para tomar decisiones sobre usted

**Sus derechos:**
- Puede solicitar hablar con un agente humano en cualquier momento
- Puede preguntar al sistema por qué ha calculado un determinado precio
- Puede impugnar cualquier resultado contactando con nosotros en [email]

**Lógica del cálculo de presupuestos:**
Los presupuestos se calculan aplicando tarifas fijas establecidas por tipo 
de homologación y elementos solicitados. Las tarifas son públicas e iguales 
para todos los usuarios.
```

### 8.2 Derechos Específicos del Art. 22.3 RGPD (Medidas Cautelares)

Aunque no aplica obligatoriamente, se recomienda garantizar los siguientes derechos como medida de prudencia:

| Derecho | Descripción | Implementación |
|---------|-------------|----------------|
| **Intervención humana** | Solicitar revisión humana del presupuesto | `escalar_a_humano` tool |
| **Expresar punto de vista** | Aportar contexto adicional | Conversación libre con el agente |
| **Impugnar la decisión** | Cuestionar el cálculo | Email a MSI Automotive + agente humano |

---

## 9. Registro y Mantenimiento

### 9.1 Actualización del Análisis

Este análisis debe revisarse cuando:

| Evento | Acción |
|--------|--------|
| Cambio significativo en funcionalidades del agente | Revisión completa |
| Nueva funcionalidad que toma decisiones | Análisis del nuevo proceso |
| Actualización de Directrices EDPB sobre Art. 22 | Revisión de conclusiones |
| Resolución de la AEPD sobre sistemas similares | Actualización de conclusiones |
| **Plazo máximo sin revisión** | **Anual** |

### 9.2 Historial de Versiones

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0 | Febrero 2026 | Análisis inicial de MSI-a v2.0 (arquitectura basada en modos) |

---

## 10. Aprobación

Este documento debe ser aprobado por:

| Rol | Nombre | Fecha | Firma |
|-----|--------|-------|-------|
| Representante Legal MSI Automotive S.L. | _________________ | _______ | _______ |
| Delegado de Protección de Datos (si designado) | _________________ | _______ | _______ |
| Abogado RGPD externo | _________________ | _______ | _______ |
| Responsable Técnico (Zanovix) | _________________ | _______ | _______ |

---

## Anexo A — Extracto Relevante Art. 22 RGPD

El Art. 22 RGPD protege a los interesados frente a decisiones que se basen **exclusivamente** en el tratamiento automatizado. Los elementos clave son:

- **"Únicamente"**: Si existe cualquier intervención humana significativa, el Art. 22 no aplica
- **"Efectos jurídicos"**: Modificación de derechos u obligaciones legales
- **"Afecte significativamente de modo similar"**: Efectos relevantes equivalentes a los jurídicos

El EDPB, en sus Directrices 03/2017, aclara que ejemplos de afectación significativa incluyen:
- Denegación automática de solicitudes de crédito
- Contratación automatizada sin revisión humana
- Fijación de primas de seguro sin revisión
- Targeting discriminatorio en publicidad

**Ejemplos que NO constituyen afectación significativa según el EDPB**:
- Recomendaciones de productos
- Filtrado de resultados de búsqueda
- Chatbots de información general (comparable a MSI-a)

---

*Este documento es un borrador técnico redactado por Zanovix. No tiene valor jurídico hasta ser validado por abogado especialista en RGPD y aprobado y firmado por MSI Automotive S.L.*

*Próxima revisión programada: Febrero 2027 o ante cualquier cambio significativo en las funcionalidades del sistema.*
