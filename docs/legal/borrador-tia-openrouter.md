# Evaluación de Impacto de la Transferencia (TIA)
## OpenRouter / DeepSeek — Art. 46 RGPD + Directrices 05/2021 EDPB

**Versión**: 1.1 (BORRADOR — pendiente validación abogado RGPD)  
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
>
> La transferencia de datos personales a terceros países sin las garantías adecuadas constituye una infracción grave
> del RGPD (Art. 83.5) con multas de hasta 20.000.000 € o el 4% del volumen de negocio mundial anual.

---

## Índice

1. [Objeto y Alcance](#1-objeto-y-alcance)
2. [Descripción de la Transferencia](#2-descripción-de-la-transferencia)
3. [Identificación del País de Destino](#3-identificación-del-país-de-destino)
4. [Análisis del Ordenamiento Jurídico del País Tercero](#4-análisis-del-ordenamiento-jurídico-del-país-tercero)
5. [Garantías Contractuales Adoptadas](#5-garantías-contractuales-adoptadas)
6. [Medidas Suplementarias Técnicas](#6-medidas-suplementarias-técnicas)
7. [Medidas Suplementarias Organizativas](#7-medidas-suplementarias-organizativas)
8. [Evaluación de Efectividad de las Garantías](#8-evaluación-de-efectividad-de-las-garantías)
9. [Conclusión y Decisión](#9-conclusión-y-decisión)
10. [Plan de Revisión y Monitorización](#10-plan-de-revisión-y-monitorización)
11. [Aprobación](#11-aprobación)
12. [Anexos](#12-anexos)

---

## 1. Objeto y Alcance

### 1.1 Objeto

La presente Evaluación de Impacto de la Transferencia (TIA, por sus siglas en inglés *Transfer Impact Assessment*) analiza la adecuación de las garantías establecidas para la transferencia de datos personales al utilizar el servicio de API de **OpenRouter, Inc.** (empresa estadounidense) que enruta consultas al modelo de inteligencia artificial **DeepSeek** (empresa china, operada por DeepSeek AI, Hangzhou, China).

Esta evaluación se realiza conforme a:
- El **Art. 46 RGPD** (transferencias mediante garantías adecuadas)
- Las **Directrices 05/2021 del EDPB** sobre transferencias a terceros países
- La **Sentencia Schrems II** (TJUE, C-311/18, 16 julio 2020)
- La **Sentencia Schrems I** (TJUE, C-362/14, 6 octubre 2015)

### 1.2 Alcance

| Elemento | Descripción |
|----------|-------------|
| **Sistema analizado** | MSI-a — Agente conversacional WhatsApp de MSI Automotive S.L. |
| **Servicio externo** | OpenRouter API (router) → DeepSeek Chat API (LLM) |
| **Tipo de datos transferidos** | Mensajes de WhatsApp de usuarios (consultas sobre homologaciones) que pueden contener datos personales |
| **Frecuencia** | Continua (cada conversación que requiera Tier 3 del LLM Router) |
| **Volumen estimado** | Variable; estimado ~30-50% de las conversaciones activas |
| **Finalidad** | Procesamiento de lenguaje natural para responder consultas sobre homologaciones de vehículos |

### 1.3 Partes Involucradas

| Rol RGPD | Entidad | País | Base Legal |
|-----------|---------|------|------------|
| Responsable del tratamiento | MSI Automotive S.L. | España (UE) | Art. 24 RGPD |
| Encargado del tratamiento | Zanovix (agencia) | España (UE) | Art. 28 RGPD |
| Sub-encargado (router) | OpenRouter, Inc. | EE.UU. (no adecuado) | SCCs + TIA |
| Sub-subencargado (LLM) | DeepSeek AI | China (no adecuado) | ⚠️ Sin marco adecuado |

---

## 2. Descripción de la Transferencia

### 2.1 Flujo de Datos

```
Usuario WhatsApp
      ↓
Mensaje de texto (puede incluir nombre, teléfono, tipo de vehículo, etc.)
      ↓
Chatwoot → Webhook MSI-a API
      ↓
Redis Stream → Agente LangGraph
      ↓
[Si Tier 3 requerido por LLM Router]
      ↓
OpenRouter API (EE.UU.) ──────────────────────────────┐
      ↓                                               │
DeepSeek Chat API (China) ← TRANSFERENCIA CRÍTICA     │
      ↓                                               │
Respuesta procesada                                   │
      ↓                                               └─ DATOS FUERA DE LA UE
MSI-a Agent → Chatwoot → WhatsApp Usuario
```

### 2.2 Datos Personales Transferidos

Los mensajes enviados a la API de OpenRouter/DeepSeek pueden contener:

| Categoría de Dato | Ejemplos | Riesgo |
|-------------------|----------|--------|
| **Datos de identificación** | Nombre del usuario (si lo menciona en conversación) | Medio |
| **Datos de contacto** | Número de teléfono WhatsApp (incluido en contexto) | Alto |
| **Datos del vehículo** | Matrícula, bastidor, marca, modelo | Medio-Alto |
| **Datos económicos** | Consultas de precios, presupuestos solicitados | Bajo |
| **Datos de comportamiento** | Historial de conversación (últimas N interacciones) | Medio |

> ⚠️ **Nota técnica**: El historial de conversación enviado como contexto al LLM incluye el número de teléfono del usuario como identificador. Esto implica transferencia de datos de contacto a cada llamada.

### 2.3 Condiciones Técnicas de la Transferencia

| Parámetro | Valor |
|-----------|-------|
| **Protocolo** | HTTPS/TLS 1.3 |
| **Cifrado en tránsito** | ✅ Sí (TLS) |
| **Cifrado en reposo en destino** | ❓ No verificable desde MSI-a |
| **Retención por OpenRouter** | Según sus términos (ver sección 4.2) |
| **Retención por DeepSeek** | Según sus términos (ver sección 4.3) |
| **Pseudonimización previa** | ❌ No implementada actualmente |
| **Minimización de datos** | Parcial (se envía historial completo de sesión) |

---

## 3. Identificación del País de Destino

### 3.1 OpenRouter, Inc. — Estados Unidos

| Aspecto | Análisis |
|---------|----------|
| **Decisión de adecuación UE** | ❌ No existe decisión de adecuación general para EE.UU. |
| **Marco EU-US Data Privacy Framework** | ✅ En vigor desde julio 2023 (Decisión de ejecución 2023/1795) |
| **OpenRouter adherido al DPF** | ❓ **Verificar en**: [dataprivacyframework.gov](https://www.dataprivacyframework.gov) |
| **Legislación de vigilancia relevante** | FISA Section 702, EO 12333, CLOUD Act |
| **Riesgo residual post-DPF** | Medio (pendiente posible impugnación Schrems III) |

> 📋 **Acción requerida**: Verificar si OpenRouter, Inc. está inscrita en el Data Privacy Framework antes de firmar este documento.

### 3.2 DeepSeek AI — China (República Popular China)

| Aspecto | Análisis |
|---------|----------|
| **Decisión de adecuación UE** | ❌ No existe. China no tiene decisión de adecuación |
| **Marco de transferencia aplicable** | ❌ Ninguno equivalente al DPF |
| **Legislación de vigilancia relevante** | Ley de Seguridad Nacional (2015), Ley de Ciberseguridad (2017), Ley de Inteligencia Nacional (2017), Ley de Seguridad de Datos (2021), Ley de Protección de la Información Personal PIPL (2021) |
| **Art. 7 Ley de Inteligencia Nacional China** | Obliga a empresas chinas a **cooperar con servicios de inteligencia** |
| **Riesgo** | **ALTO — No existe garantía equivalente al RGPD** |

> ⚠️ **ALERTA CRÍTICA**: La Ley de Inteligencia Nacional de China (Art. 7) obliga a DeepSeek AI a cooperar con los servicios de inteligencia del Estado chino, lo que podría implicar acceso a datos de ciudadanos europeos procesados por su API. Esto es **incompatible por naturaleza** con el RGPD según la doctrina Schrems II.

---

## 4. Análisis del Ordenamiento Jurídico del País Tercero

### 4.1 Metodología

Esta sección sigue la metodología del **EDPB Guidelines 05/2021** (Step 3: Assessment of the law and practice of the third country).

Los factores evaluados son:
1. Existencia de Estado de Derecho y tutela judicial
2. Respeto a los derechos fundamentales y libertades
3. Legislación de vigilancia/acceso gubernamental
4. Mecanismos de supervisión independiente
5. Acuerdos internacionales en vigor

### 4.2 EE.UU. — OpenRouter

**Marco legal aplicable**:

| Ley | Descripción | Impacto en transferencias UE |
|-----|-------------|------------------------------|
| **FISA Section 702** | Vigilancia electrónica extranjera | Alto — permite acceso a comunicaciones |
| **EO 12333** | Vigilancia de inteligencia exterior | Medio — fuera de alcance judicial |
| **CLOUD Act** | Acceso de autoridades EE.UU. a datos en la nube | Medio — mitigado por DPF |
| **Privacy Act 1974** | Protección datos del Gobierno | Bajo impacto en privados |

**Evaluación post-DPF**: El EU-US Data Privacy Framework (2023) introduce salvaguardias adicionales:
- Acceso de inteligencia solo cuando "necesario y proporcionado"
- Tribunal de Revisión de Protección de Datos (DPRC)
- Mecanismo de recurso para ciudadanos europeos

**Conclusión EE.UU.**: Riesgo **MEDIO-BAJO** si OpenRouter está adherida al DPF. Riesgo **ALTO** si no está adherida.

### 4.3 China — DeepSeek

**Marco legal aplicable**:

| Ley | Art. clave | Descripción | Impacto |
|-----|------------|-------------|---------|
| **Ley de Inteligencia Nacional** (2017) | Art. 7 | Obliga a empresas a apoyar/cooperar con inteligencia nacional | **CRÍTICO** |
| **Ley de Ciberseguridad** (2017) | Art. 28 | Obliga a proveedores de red a proporcionar apoyo técnico a fuerzas de seguridad | **ALTO** |
| **Ley de Seguridad de Datos** (2021) | Art. 36 | Organizaciones que proporcionen datos al extranjero deben obtener aprobación del Gobierno | **ALTO** |
| **PIPL** (2021) | Art. 13 | Requiere consentimiento o base legal para tratamiento de datos personales | Bajo (no equivalente RGPD) |

**Análisis de acceso gubernamental**:

El Art. 7 de la Ley de Inteligencia Nacional establece (traducción):
> *"Todo ciudadano, organización e institución chinos deberá apoyar, asistir y cooperar con el trabajo de inteligencia del Estado de acuerdo con la ley, y guardar secreto de cualquier trabajo de inteligencia del Estado que conozcan."*

Esto significa que **DeepSeek AI no puede negarse legalmente** a proporcionar acceso a datos (incluidos los de ciudadanos europeos) a los servicios de inteligencia chinos si así se les requiere.

**Mecanismos de tutela para ciudadanos europeos en China**:
- ❌ No existe tribunal independiente equivalente al DPRC europeo
- ❌ No existe mecanismo de recurso para ciudadanos extranjeros
- ❌ El poder judicial chino no es independiente del poder ejecutivo

**Conclusión China**: Riesgo **MUY ALTO — Incompatible con estándares del RGPD** según doctrina Schrems II.

---

## 5. Garantías Contractuales Adoptadas

### 5.1 Situación Actual

| Garantía | Estado |
|----------|--------|
| **Cláusulas Contractuales Tipo (SCCs) con OpenRouter** | ❌ No firmadas |
| **Contrato Art. 28 con OpenRouter** | ❌ No firmado |
| **SCCs con DeepSeek** | ❌ No firmadas / No viables (ver análisis) |
| **Contrato Art. 28 con DeepSeek** | ❌ No firmado |

> ⚠️ **Situación crítica**: Actualmente la transferencia se realiza **sin garantías adecuadas**, lo que constituye una infracción del Art. 46 RGPD.

### 5.2 Garantías Requeridas — OpenRouter (EE.UU.)

**Opción recomendada: Módulo 4 de las SCCs (encargado-a-encargado)**

Las SCCs de la Comisión Europea (Decisión de Ejecución 2021/914) contemplan 4 módulos:
- Módulo 1: Responsable-a-Responsable
- Módulo 2: Responsable-a-Encargado
- **Módulo 3: Encargado-a-Encargado** ← Aplicable (Zanovix → OpenRouter)
- Módulo 4: Encargado-a-Responsable

**Proceso**:
1. MSI Automotive S.L. (Responsable) autoriza a Zanovix a contratar con OpenRouter como sub-encargado
2. Zanovix firma SCCs Módulo 3 con OpenRouter
3. OpenRouter acepta SCCs en sus términos de servicio o vía contrato bilateral

**Alternativa**: Si OpenRouter está adherida al EU-US DPF, las transferencias a OpenRouter pueden basarse en el DPF sin necesidad de SCCs adicionales para esa parte.

### 5.3 Garantías Requeridas — DeepSeek (China)

**Análisis de viabilidad de SCCs con China**:

| Factor | Análisis |
|--------|----------|
| **¿Puede DeepSeek firmar SCCs?** | Técnicamente sí, pero las SCCs no pueden superar las obligaciones de la legislación nacional china |
| **¿Son las SCCs efectivas con China?** | **Probablemente NO** — el Art. 7 de la Ley de Inteligencia Nacional choca frontalmente con las SCCs |
| **Posición del EDPB** | Las SCCs no son garantía suficiente si la legislación local permite acceso gubernamental sin control judicial |

**Conclusión**: Las SCCs con DeepSeek/entidad china **no proporcionan garantías reales** según la doctrina Schrems II. La transferencia a DeepSeek **no tiene base legal adecuada en virtud del Art. 46 RGPD**.

---

## 6. Medidas Suplementarias Técnicas

Conforme a las Directrices 05/2021 EDPB (Anexo 2), se identifican las siguientes medidas suplementarias para mitigar los riesgos:

### 6.1 Medidas Implementadas Actualmente

| Medida | Estado | Efectividad |
|--------|--------|-------------|
| **HTTPS/TLS en tránsito** | ✅ Implementado | Protege contra interceptación en tránsito |
| **Logs sanitizados** (`sanitize_phone()`) | ✅ Implementado | Reduce exposición en logs locales |
| **Hybrid LLM (Tier 1-2 local)** | ✅ Implementado | Reduce frecuencia de transferencias al 30-50% |

### 6.2 Medidas Suplementarias Propuestas

#### MST-01: Pseudonimización antes de envío al LLM (RECOMENDADA)

```python
# Propuesta técnica para agent/utils/llm_pseudonymizer.py

import hashlib
import re
from typing import tuple

PHONE_PATTERN = re.compile(r'\+?[0-9]{9,15}')
NAME_PATTERN = re.compile(r'\b[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]{2,}\s+[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]{2,}\b')

def pseudonymize_for_llm(text: str, user_phone: str) -> tuple[str, dict]:
    """
    Replace PII with pseudonyms before sending to external LLM.
    Returns (pseudonymized_text, mapping_dict) for local record.
    """
    mapping = {}
    pseudonymized = text
    
    # Replace phone number
    phone_hash = hashlib.sha256(user_phone.encode()).hexdigest()[:8]
    pseudo_phone = f"USER_{phone_hash}"
    pseudonymized = pseudonymized.replace(user_phone, pseudo_phone)
    mapping[pseudo_phone] = user_phone
    
    return pseudonymized, mapping
```

**Efectividad**: Alta para datos de contacto. Limitada para contenido semántico.  
**Coste de implementación**: ~2 días de desarrollo.

#### MST-02: Minimización de historial de conversación

En lugar de enviar el historial completo de conversación, enviar solo los últimos N mensajes necesarios para el contexto.

**Implementación**: Reducir `MAX_HISTORY_MESSAGES` de ilimitado a 5-10 mensajes.  
**Efectividad**: Reduce el volumen de datos personales transferidos.  
**Coste**: Bajo (1-2 horas).

#### MST-03: Cifrado end-to-end del contenido (NO VIABLE en la práctica)

El cifrado del contenido antes de enviarlo al LLM haría inútil el procesamiento de lenguaje natural. **No es una medida viable** para este caso de uso.

### 6.3 Valoración de Suficiencia de Medidas

| Escenario | Medidas | ¿Suficiente para Art. 46? |
|-----------|---------|--------------------------|
| Transferencia a OpenRouter (DPF) | DPF + SCCs Módulo 3 | ✅ Sí (si DPF válido) |
| Transferencia a OpenRouter (sin DPF) | SCCs Módulo 3 + MST-01 + MST-02 | ⚠️ Posiblemente sí |
| Transferencia a DeepSeek (China) | SCCs + MST-01 + MST-02 | ❌ No — insuficiente dada Ley Inteligencia Nacional |

---

## 7. Medidas Suplementarias Organizativas

### 7.1 Medidas Propuestas

| Medida | Descripción | Responsable |
|--------|-------------|-------------|
| **MSO-01** | Revisión trimestral de adherencia de OpenRouter al DPF | Zanovix |
| **MSO-02** | Monitorización cambios legislativos en China (PIPL, Ley Inteligencia Nacional) | Abogado RGPD |
| **MSO-03** | Evaluación anual de proveedores LLM alternativos establecidos en UE/EEE | Zanovix + MSI Automotive |
| **MSO-04** | Formación del personal sobre transferencias internacionales | MSI Automotive |
| **MSO-05** | Registro de transferencias en el RAT con actualización semestral | Zanovix |

### 7.2 Proveedores LLM Alternativos en UE/EEE (Para Consideración Futura)

| Proveedor | País | Modelo | Estado RGPD |
|-----------|------|--------|-------------|
| **Mistral AI** | Francia (UE) | Mistral Large, Mixtral | ✅ Adecuado — empresa europea |
| **Aleph Alpha** | Alemania (UE) | Luminous | ✅ Adecuado — empresa europea |
| **BLOOM** (Hugging Face) | Francia (UE) | Varios | ✅ Adecuado — open source |
| **Ollama (modelos locales)** | Local (sin transferencia) | llama3, qwen2.5 | ✅ Óptimo — sin transferencia |

> 💡 **Recomendación estratégica**: Evaluar el modelo **Mistral Large** de Mistral AI (París, UE) como alternativa a DeepSeek para el Tier 3 del LLM Router. Esto eliminaría la transferencia a China y simplificaría significativamente el compliance.

---

## 8. Evaluación de Efectividad de las Garantías

### 8.1 Resumen por Destinatario

#### OpenRouter, Inc. (EE.UU.)

| Criterio | Evaluación | Puntuación |
|----------|------------|------------|
| Marco legal del país tercero | EU-US DPF vigente | 3/5 |
| Garantías contractuales | SCCs disponibles + posible DPF | 4/5 |
| Medidas técnicas | TLS + Pseudonimización (propuesta) | 3/5 |
| Recurso efectivo para interesados | DPRC (DPF) | 3/5 |
| **TOTAL** | | **13/20 — RIESGO MEDIO** |

**Conclusión OpenRouter**: La transferencia **puede ser viable** con las garantías adecuadas (SCCs Módulo 3 y/o DPF), especialmente con la implementación de MST-01 (pseudonimización).

#### DeepSeek AI (China)

| Criterio | Evaluación | Puntuación |
|----------|------------|------------|
| Marco legal del país tercero | Ley Inteligencia Nacional — incompatible con RGPD | 0/5 |
| Garantías contractuales | SCCs no efectivas vs. Ley nacional china | 1/5 |
| Medidas técnicas | TLS + Pseudonimización (insuficiente bajo Art. 46) | 2/5 |
| Recurso efectivo para interesados | Inexistente en China | 0/5 |
| **TOTAL** | | **3/20 — RIESGO CRÍTICO** |

**Conclusión técnica**: No existe base adecuada bajo **Art. 46 RGPD** para esta transferencia. Las garantías disponibles son insuficientes para contrarrestar el marco legal chino.

**Decisión de MSI Automotive S.L. (Febrero 2026)**: Tras evaluar las opciones disponibles (migración a Mistral AI, uso de Nebius NL, pseudonimización), MSI Automotive S.L. ha decidido **mantener DeepSeek V3 via OpenRouter como proveedor Tier 3**, asumiendo conscientemente el riesgo residual bajo **Art. 49.1.b RGPD** (necesario para la ejecución del servicio) en tanto no exista una alternativa técnica equivalente a coste razonable. Esta decisión queda documentada y será revisada anualmente o ante cambios normativos relevantes. La validación jurídica de esta base queda pendiente del abogado RGPD externo.

### 8.2 Tabla Resumen de Riesgos

| Riesgo | Probabilidad | Impacto | Riesgo Residual | Aceptable |
|--------|-------------|---------|-----------------|-----------|
| Acceso inteligencia EE.UU. a datos vía OpenRouter | Baja | Alto | Medio | ⚠️ Condicionalmente |
| Acceso inteligencia China a datos vía DeepSeek | Alta | Crítico | Muy Alto | ⚠️ **Asumido conscientemente por MSI Automotive** |
| Violación de datos en tránsito | Muy Baja | Alto | Bajo | ✅ Sí |
| Uso de datos para entrenamiento LLM | Media | Alto | Alto | ❌ Pendiente confirmar opt-out con OpenRouter |

---

## 9. Conclusión y Decisión

### 9.1 Conclusión

Tras el análisis realizado conforme a las Directrices 05/2021 del EDPB y la doctrina Schrems II:

**Respecto a OpenRouter (EE.UU.)**:
La transferencia puede ser **viable** si se cumplen las siguientes condiciones:
1. Se verifica la adherencia de OpenRouter al EU-US Data Privacy Framework, O
2. Se firman SCCs Módulo 3 (Encargado-a-Encargado) con OpenRouter, Y
3. Se implementa pseudonimización (MST-01) antes del envío, Y
4. Se firman términos que excluyan el uso de datos para entrenamiento

**Respecto a DeepSeek (China)**:
La transferencia de datos personales de ciudadanos europeos a DeepSeek AI (operada desde China) no tiene base legal adecuada bajo el **Art. 46 RGPD** dado el marco legal chino. MSI Automotive S.L. ha evaluado las alternativas disponibles y ha decidido **mantener DeepSeek V3 asumiendo el riesgo**, documentando la decisión bajo el Art. 49.1.b RGPD (necesario para la ejecución del servicio). Esta posición requiere validación del abogado RGPD externo.

### 9.2 Decisión Adoptada por MSI Automotive S.L.

> **Fecha de decisión**: Febrero 2026  
> **Decisor**: MSI Automotive S.L. (Responsable del tratamiento)

MSI Automotive S.L., habiendo sido informada del análisis técnico y jurídico contenido en este documento, y habiendo evaluado las siguientes alternativas:

| Alternativa evaluada | Motivo de descarte |
|---------------------|-------------------|
| Migración a Mistral AI (FR) | Descartada por eficiencia/coste en relación a calidad del modelo |
| Uso de Nebius (NL) como host de DeepSeek V3 | Descartada — no mejora la relación coste/beneficio suficientemente |
| Pseudonimización pre-envío (MST-01) | Puede implementarse como medida suplementaria (ver acciones pendientes) |
| Consentimiento explícito Art. 49.1.a | Descartada — impacto negativo en UX del servicio |

**Ha decidido**: Continuar usando **DeepSeek V3 via OpenRouter** como modelo Tier 3, aceptando el riesgo residual de la transferencia a China, bajo la base del **Art. 49.1.b RGPD** (necesidad para la ejecución del servicio prestado al interesado), y con el compromiso de:

1. ✅ Informar a los usuarios de la existencia de procesamiento por IA en la política de privacidad
2. ⏳ Confirmar con OpenRouter los términos de no-entrenamiento con datos de usuarios
3. ⏳ Firmar SCCs Módulo 3 con OpenRouter (capa contractual con el intermediario)
4. ⏳ Revisar esta decisión anualmente o ante cambios normativos relevantes

### 9.3 Acciones Pendientes (Alcance Reducido)

| Acción | Plazo | Responsable |
|--------|-------|-------------|
| **ACCIÓN 1**: Verificar si OpenRouter está en el DPF | < 30 días | Zanovix |
| **ACCIÓN 2**: Firmar SCCs Módulo 3 con OpenRouter (intermediario UE→EE.UU.) | < 30 días | MSI Automotive + Zanovix |
| **ACCIÓN 3**: Obtener confirmación escrita de no-entrenamiento de OpenRouter | < 30 días | MSI Automotive |
| **ACCIÓN 4**: Validar base Art. 49.1.b con abogado RGPD | < 45 días | Abogado RGPD ⚖️ |
| **ACCIÓN 5**: Incluir mención a procesamiento por IA externa en política de privacidad | < 15 días | Zanovix (ya en borrador) |

### 9.4 Base Jurídica Invocada: Art. 49.1.b RGPD

El Art. 49.1.b RGPD permite transferencias a terceros países cuando la transferencia sea **necesaria para la ejecución de un contrato entre el interesado y el responsable del tratamiento**.

Argumentación:
- MSI Automotive presta un servicio de consulta y presupuesto de homologaciones
- El procesamiento por LLM de alta capacidad es técnicamente necesario para dar respuesta adecuada a consultas complejas
- Los modelos locales (Tier 1-2) se usan prioritariamente; DeepSeek solo actúa como fallback para casos que los superan

**Limitación importante**: El EDPB interpreta esta excepción de forma restrictiva. Solo aplica a transferencias "necesarias" (no meramente convenientes) y hay debate sobre si cubre transferencias continuas/repetitivas. **La validación del abogado RGPD es obligatoria antes de firmar el documento.**

---

## 10. Plan de Revisión y Monitorización

| Evento | Acción | Frecuencia |
|--------|--------|------------|
| Revisión general de la TIA | Actualizar y revalidar todo el documento | Anual |
| Cambios en legislación del país tercero | Revisión urgente | Inmediata |
| Cambios en términos de servicio de OpenRouter/DeepSeek | Revisión urgente | Inmediata |
| Resolución de supervisión sobre EE.UU. o China | Revisión urgente | Inmediata |
| Cambio de proveedor LLM | Nueva TIA si aplica | Por evento |
| Invalidación del DPF (posible Schrems III) | Revisión urgente + medidas alternativas | Inmediata |

---

## 11. Aprobación

Este documento debe ser aprobado por:

| Rol | Nombre | Fecha | Firma |
|-----|--------|-------|-------|
| Representante Legal MSI Automotive S.L. | _________________ | _______ | _______ |
| Delegado de Protección de Datos (si designado) | _________________ | _______ | _______ |
| Abogado RGPD externo | _________________ | _______ | _______ |
| Responsable Técnico (Zanovix) | _________________ | _______ | _______ |

---

## 12. Anexos

### Anexo A — Legislación China Relevante (Extractos)

**Ley de Inteligencia Nacional de la RPC (2017), Art. 7**:
> "Todo ciudadano y organización deberá apoyar, cooperar y colaborar en el trabajo de inteligencia nacional de conformidad con la ley, y guardar secreto del trabajo de inteligencia nacional que conozcan."

**Ley de Ciberseguridad de la RPC (2017), Art. 28**:
> "Los operadores de redes deberán proporcionar apoyo técnico y asistencia a los órganos de seguridad pública y de seguridad del Estado que lleven a cabo actividades de prevención y de investigación de delitos de conformidad con la ley."

**Ley de Seguridad de Datos de la RPC (2021), Art. 36**:
> "Los organismos pertinentes de la República Popular China que, de conformidad con las leyes y reglamentos aplicables, soliciten a los operadores de datos que proporcionen datos almacenados en el territorio de China, deberán obtener la aprobación del órgano gubernamental competente de la República Popular China."

### Anexo B — Referencia Normativa UE

- **RGPD (UE) 2016/679**, especialmente Arts. 44-49 (transferencias internacionales)
- **Directrices 05/2021 del EDPB** sobre transferencias con arreglo al Art. 46(1) RGPD
- **Directrices 04/2021 del EDPB** sobre SCCs para transferencias internacionales
- **Decisión de Ejecución 2021/914** de la Comisión — SCCs actualizadas
- **Decisión de ejecución 2023/1795** — EU-US Data Privacy Framework
- **Sentencia C-311/18** (Schrems II), TJUE, 16 julio 2020
- **Sentencia C-362/14** (Schrems I), TJUE, 6 octubre 2015

### Anexo C — Historial de Versiones

| Versión | Fecha | Autor | Cambios |
|---------|-------|-------|---------|
| 1.0 | Febrero 2026 | Zanovix (borrador) | Versión inicial |
| — | — | Abogado RGPD | Pendiente validación jurídica |
| — | — | MSI Automotive | Pendiente aprobación y firma |

---

*Este documento es un borrador técnico redactado por Zanovix. No tiene valor jurídico hasta ser validado por abogado especialista en RGPD y aprobado y firmado por MSI Automotive S.L.*

*Siguiente revisión programada: Febrero 2027 (o antes si hay cambios normativos relevantes)*
