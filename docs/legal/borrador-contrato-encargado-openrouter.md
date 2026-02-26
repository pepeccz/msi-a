# Contrato de Encargo de Tratamiento — OpenRouter
## Art. 28 RGPD + Cláusulas Contractuales Tipo (SCCs) Módulo 3

**Versión**: 1.0 (BORRADOR — pendiente validación abogado RGPD)  
**Fecha**: Febrero 2026  
**Responsable del tratamiento**: MSI Automotive S.L.  
**Encargado principal**: Zanovix (agencia de desarrollo)  
**Sub-encargado**: OpenRouter, Inc. (enrutamiento de LLM)  
**Sub-subencargado**: DeepSeek AI (modelo LLM — ver nota)  
**Redactado por**: Zanovix (para revisión y firma de MSI Automotive S.L.)  
**Clasificación**: ⚖️ Requiere validación jurídica externa  

---

> ⚠️ **NOTA LEGAL IMPORTANTE**
>
> Este documento es un **borrador técnico** redactado por Zanovix en su calidad de encargado del tratamiento.
> Antes de ser utilizado como documento legal válido, **debe ser revisado y validado por un abogado especialista en RGPD**,
> y posteriormente **aprobado y firmado por MSI Automotive S.L.** como responsable del tratamiento.
>
> **Nota crítica sobre DeepSeek**: Como se analiza en la TIA (borrador-tia-openrouter.md), la transferencia de
> datos personales a DeepSeek AI (China) **no tiene base legal adecuada bajo el Art. 46 RGPD**.
> Este contrato con OpenRouter no soluciona el problema de DeepSeek. Ver Sección 7 para opciones.
>
> **Recomendación prioritaria**: Migrar el Tier 3 del LLM Router a **Mistral AI (Francia, UE)** para eliminar
> el problema de transferencias internacionales problemáticas.

---

## Índice

1. [Partes Contratantes](#1-partes-contratantes)
2. [Objeto y Estructura del Encargo](#2-objeto-y-estructura-del-encargo)
3. [Descripción del Tratamiento](#3-descripción-del-tratamiento)
4. [Cláusulas Contractuales Tipo (SCCs) — Módulo 3](#4-cláusulas-contractuales-tipo-sccs--módulo-3)
5. [Obligaciones de OpenRouter como Sub-encargado](#5-obligaciones-de-openrouter-como-sub-encargado)
6. [Prohibición de Uso para Entrenamiento](#6-prohibición-de-uso-para-entrenamiento)
7. [Tratamiento del Problema DeepSeek/China](#7-tratamiento-del-problema-deepseekchina)
8. [Medidas de Seguridad](#8-medidas-de-seguridad)
9. [Notificación de Brechas](#9-notificación-de-brechas)
10. [Derechos de los Interesados](#10-derechos-de-los-interesados)
11. [Auditoría y Supervisión](#11-auditoría-y-supervisión)
12. [Duración y Extinción](#12-duración-y-extinción)
13. [Responsabilidad](#13-responsabilidad)
14. [Disposiciones Finales](#14-disposiciones-finales)
15. [Firmas](#15-firmas)
16. [Anexo I — Descripción del Tratamiento](#16-anexo-i--descripción-del-tratamiento)
17. [Anexo II — SCCs Módulo 3 (Referencia)](#17-anexo-ii--sccs-módulo-3-referencia)

---

## 1. Partes Contratantes

### 1.1 Cadena de Responsabilidad

```
MSI Automotive S.L.        → Responsable del tratamiento (Art. 24 RGPD)
       ↓ (Art. 28 RGPD)
Zanovix                    → Encargado principal
       ↓ (Art. 28.4 RGPD)
OpenRouter, Inc.           → Sub-encargado (autorizado por MSI Automotive)
       ↓ (Transferencia Art. 46/49 RGPD)
[Modelo LLM destino]       → Sub-subencargado (ver Sección 7)
```

### 1.2 Identidad de las Partes

**ENCARGADO PRINCIPAL** (quien autoriza el sub-encargo):

**Zanovix** (en adelante, "el Encargado Principal")  
- Domicilio: [Dirección de Zanovix — completar]  
- NIF: [NIF de Zanovix — completar]  
- Representado por: [Nombre — completar]  
- En nombre y por cuenta de: MSI Automotive S.L.  
- Email de contacto: [email de Zanovix — completar]  

**SUB-ENCARGADO** (destinatario de este contrato):

**OpenRouter, Inc.** (en adelante, "el Sub-encargado" o "OpenRouter")  
- Domicilio: [Dirección de OpenRouter — verificar y completar]  
- País: Estados Unidos de América  
- Email de contacto RGPD/Legal: [verificar en openrouter.ai — completar]  
- DPA disponible en: [verificar en openrouter.ai/privacy — completar]  

**RESPONSABLE DEL TRATAMIENTO** (cuya autorización es necesaria):

**MSI Automotive S.L.** (en adelante, "el Responsable")  
- NIF: [NIF — completar]  
- Domicilio social: [Dirección — completar]  
- Su consentimiento para este sub-encargo: ✅ Dado en virtud del Contrato de Encargo con Zanovix  

---

## 2. Objeto y Estructura del Encargo

### 2.1 Objeto

El presente contrato regula el sub-encargo del tratamiento de datos personales a **OpenRouter, Inc.** en el contexto del uso de su API de enrutamiento de modelos de lenguaje grande (LLM) para el sistema MSI-a de MSI Automotive S.L., de conformidad con el **Art. 28.4 RGPD**.

### 2.2 Naturaleza del Sub-encargo

OpenRouter actúa como **sub-encargado** de Zanovix (encargado principal), con autorización expresa de MSI Automotive S.L. (responsable del tratamiento).

OpenRouter **no es responsable** del tratamiento. No puede tomar decisiones sobre el tratamiento de los datos más allá de las instrucciones recibidas.

### 2.3 Ámbito del Tratamiento

OpenRouter únicamente tratará datos personales en la medida necesaria para:
1. Recibir la consulta de API enviada por el sistema MSI-a
2. Enrutar la consulta al modelo LLM seleccionado
3. Devolver la respuesta del modelo LLM al sistema MSI-a

**OpenRouter NO está autorizado a**:
- Retener datos más tiempo del necesario para procesar la solicitud
- Usar datos para entrenamiento de modelos propios o de terceros
- Compartir datos con terceros para sus propios fines
- Crear perfiles de usuarios basados en las consultas
- Agregar o combinar datos con otras fuentes

---

## 3. Descripción del Tratamiento

Ver **Anexo I** para descripción completa. Resumen:

| Elemento | Descripción |
|----------|-------------|
| **Finalidad** | Enrutamiento de consultas a modelos LLM para procesamiento de lenguaje natural |
| **Naturaleza** | Transmisión, procesamiento temporal y devolución de respuestas |
| **Tipo de datos** | Mensajes de conversación (pueden contener datos personales) |
| **Duración del procesamiento** | Tiempo de respuesta de la API (segundos) |
| **Retención por OpenRouter** | [Verificar política de retención de OpenRouter] |

---

## 4. Cláusulas Contractuales Tipo (SCCs) — Módulo 3

### 4.1 Aplicabilidad

Dado que OpenRouter, Inc. está establecida en **EE.UU.** (país sin decisión de adecuación general, salvo EU-US DPF), la transferencia de datos personales requiere garantías adecuadas conforme al **Art. 46 RGPD**.

**Mecanismo seleccionado**:

| Opción | Condición | Estado |
|--------|-----------|--------|
| **EU-US Data Privacy Framework** | Si OpenRouter está adherida al DPF | ✅ Preferida — verificar en dataprivacyframework.gov |
| **SCCs Módulo 3 (Encargado-a-Encargado)** | Si OpenRouter no está en DPF | Fallback |

### 4.2 Verificación del DPF

> 📋 **Acción previa a firma**: Verificar si OpenRouter, Inc. está inscrita en el Data Privacy Framework en:
> https://www.dataprivacyframework.gov/list
>
> Si está inscrita → Las transferencias se basan en el DPF (Decisión 2023/1795). Las SCCs son una garantía adicional opcional.
> Si NO está inscrita → Las SCCs Módulo 3 son obligatorias para la transferencia.

### 4.3 SCCs Módulo 3 — Incorporación por Referencia

Las partes acuerdan quedar vinculadas por las **Cláusulas Contractuales Tipo para la transferencia de datos personales a terceros países** adoptadas por la Decisión de Ejecución (UE) 2021/914 de la Comisión Europea, específicamente el **Módulo 3 (Transferencia encargado del tratamiento a encargado del tratamiento)**, que se incorporan por referencia a este contrato.

El texto completo de las SCCs está disponible en:
https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX%3A32021D0914

**Información complementaria de las SCCs (Anexo I de las SCCs)**:

**Exportador de datos** (Cláusula 1 de las SCCs):
- Nombre: Zanovix (en nombre de MSI Automotive S.L.)
- Dirección: [completar]
- Contacto DPD: privacidad@msiautomotive.es
- Actividades de tratamiento: Agente conversacional IA para atención al cliente

**Importador de datos** (Cláusula 1 de las SCCs):
- Nombre: OpenRouter, Inc.
- Dirección: [completar]
- Actividades de tratamiento: Enrutamiento de consultas LLM

**Medidas técnicas y organizativas** (Cláusula 4 de las SCCs): Ver Sección 8 de este contrato.

---

## 5. Obligaciones de OpenRouter como Sub-encargado

### 5.1 Instrucciones

OpenRouter tratará los datos personales **únicamente según las instrucciones** de Zanovix (encargado principal), que a su vez actúa según las instrucciones de MSI Automotive S.L. (responsable).

### 5.2 Confidencialidad

Garantizará que el personal con acceso a los datos personales está sujeto a compromisos de confidencialidad.

### 5.3 Seguridad

Implementará las medidas técnicas y organizativas descritas en la Sección 8.

### 5.4 Sub-subcontratación (Modelos LLM)

OpenRouter **informará** a Zanovix de los modelos LLM disponibles y sus ubicaciones. Cualquier cambio que implique nuevos terceros con acceso a datos personales requiere **autorización previa** de Zanovix/MSI Automotive.

### 5.5 Asistencia

Asistirá al encargado principal y al responsable en el ejercicio de derechos de los interesados y en la gestión de brechas de seguridad.

### 5.6 Eliminación

Al finalizar el servicio, eliminará los datos personales procesados conforme a este contrato.

---

## 6. Prohibición de Uso para Entrenamiento

### 6.1 Cláusula Anti-entrenamiento (CRÍTICA)

> **OpenRouter y los modelos LLM a los que enruta las consultas NO están autorizados a utilizar los datos personales procesados en virtud de este contrato para el entrenamiento, ajuste fino (fine-tuning), evaluación o mejora de ningún modelo de inteligencia artificial, salvo autorización expresa y previa de MSI Automotive S.L.**

### 6.2 Acción Requerida

Verificar que los **Términos de Servicio de OpenRouter** contemplan esta exclusión. Si no lo hacen:
1. Negociar una cláusula contractual específica con OpenRouter
2. Verificar si existe opción de opt-out en la configuración de la API

**URL de términos de OpenRouter**: [verificar en openrouter.ai/terms]

### 6.3 Modelos Propios de OpenRouter

Si OpenRouter tiene modelos propios que se mejoran con los datos de uso, se debe:
- Confirmar que los datos de MSI-a están excluidos
- Obtener confirmación escrita de esta exclusión

---

## 7. Tratamiento del Problema DeepSeek/China

### 7.1 Situación Actual

Como se documenta en el **borrador-tia-openrouter.md**, la transferencia a DeepSeek AI (operada desde China) no tiene base legal adecuada bajo el Art. 46 RGPD, dado que:
- China no tiene decisión de adecuación de la UE
- El Art. 7 de la Ley de Inteligencia Nacional china hace ineficaces las SCCs
- No existe mecanismo de tutela equivalente para ciudadanos europeos

### 7.2 Opciones y Acción Requerida

El Responsable (MSI Automotive) debe adoptar **una de las siguientes opciones** antes de que este contrato entre en vigor:

**Opción A — RECOMENDADA: Migrar Tier 3 a Mistral AI (UE)**

```
Acción técnica: Cambiar LLM_MODEL=deepseek/deepseek-chat
                     a LLM_MODEL=mistral/mistral-large-latest

Beneficio: Elimina la transferencia a China y simplifica el compliance
Coste técnico: Bajo (~1 día de trabajo de Zanovix)
Coste económico: Verificar precios de Mistral vs DeepSeek en OpenRouter
```

Si se adopta la Opción A, este contrato con OpenRouter **no necesita cláusulas especiales sobre DeepSeek**, ya que las consultas se enrutarán a Mistral AI (empresa francesa, UE).

**Opción B: Consentimiento explícito (Art. 49.1.a RGPD)**

Si se mantiene DeepSeek, implementar el formulario de consentimiento descrito en `borrador-consentimiento.md`, Sección 7.2.

**Opción C: Habilitar DeepSeek solo para datos no personales**

Implementar pseudonimización (MST-01 de la TIA) antes de enviar datos a OpenRouter cuando se usa DeepSeek como modelo de destino.

### 7.3 Cláusula Transitoria

Hasta que MSI Automotive adopte una de las opciones anteriores, **OpenRouter queda instruida de NO enrutar consultas del sistema MSI-a al modelo `deepseek/deepseek-chat`** ni a ningún otro modelo operado por entidades establecidas en la República Popular China.

> 📋 **Implementación técnica**: Esto puede configurarse en la API de OpenRouter seleccionando modelos específicos y excluyendo los de DeepSeek. Verificar con Zanovix la configuración actual.

---

## 8. Medidas de Seguridad

### 8.1 Medidas Técnicas Mínimas Exigidas a OpenRouter

| Medida | Descripción |
|--------|-------------|
| **TLS 1.2+** | Todas las comunicaciones API cifradas en tránsito |
| **Autenticación API** | API keys seguras, rotación periódica |
| **Rate limiting** | Prevención de abuso y DDoS |
| **Logs de acceso** | Registro de todas las llamadas API |
| **Cifrado en reposo** | Datos almacenados cifrados |
| **Incident response** | Plan de respuesta ante incidentes documentado |

### 8.2 Medidas del Encargado Principal (Zanovix) Aplicadas Antes de la Transferencia

| Medida | Estado | Descripción |
|--------|--------|-------------|
| Pseudonimización del número de teléfono | ❌ Pendiente (MST-01 del TIA) | Hash del teléfono antes de envío |
| Minimización del historial de conversación | ⚠️ Parcial | Limitar a últimas N interacciones |
| Validación del contenido | ✅ Implementado | Filtros anti-prompt injection |
| HTTPS en todas las llamadas | ✅ Implementado | Cifrado en tránsito |

---

## 9. Notificación de Brechas

OpenRouter notificará a Zanovix **sin dilación indebida** (máximo 24 horas) cualquier brecha de seguridad que afecte a los datos procesados bajo este contrato.

Zanovix notificará a MSI Automotive, quien notificará a la AEPD en el plazo de 72 horas si procede (Art. 33 RGPD).

---

## 10. Derechos de los Interesados

OpenRouter asistirá a Zanovix/MSI Automotive en el ejercicio de derechos de los interesados, especialmente en la **supresión de datos** que pudieran haber sido retenidos temporalmente en los sistemas de OpenRouter.

---

## 11. Auditoría y Supervisión

OpenRouter:
- Proporcionará información sobre sus medidas de seguridad a petición
- Facilitará certificados de seguridad (SOC 2, ISO 27001) si disponibles
- Permitirá auditorías de sus sistemas en los términos acordados

---

## 12. Duración y Extinción

### 12.1 Duración

Vigente mientras el sistema MSI-a utilice la API de OpenRouter.

### 12.2 Extinción

A la extinción, OpenRouter eliminará los datos procesados bajo este contrato y certificará la eliminación en 30 días.

---

## 13. Responsabilidad

OpenRouter responderá de los daños causados por:
- Incumplimiento de las instrucciones del encargado principal
- Incumplimiento de las obligaciones de este contrato
- Uso de datos para fines propios no autorizados

Conforme al Art. 82 RGPD, cada parte responde de los daños causados por sus propios incumplimientos.

---

## 14. Disposiciones Finales

### 14.1 Legislación Aplicable

RGPD (UE) 2016/679 y legislación española de protección de datos. Para cuestiones no cubiertas por el RGPD, se aplicará el Derecho del Estado de California (EE.UU.) en lo que respecta a los compromisos contractuales de OpenRouter.

### 14.2 Jurisdicción

Las partes se someten a la jurisdicción de los Juzgados y Tribunales de [ciudad de MSI Automotive] para controversias relacionadas con el RGPD, sin perjuicio del derecho del interesado a presentar reclamación ante la AEPD.

### 14.3 Prevalencia sobre Términos de Servicio Generales

En lo relativo a protección de datos personales, este contrato prevalece sobre los Términos de Servicio generales de OpenRouter.

---

## 15. Firmas

En _________________, a _____ de _____________ de 2026.

**Por Zanovix (Encargado Principal, en nombre de MSI Automotive S.L.)**

Nombre: _________________________________  
Cargo: _________________________________  
Firma: _________________________________  
Fecha: _________________________________  

**Visto bueno de MSI Automotive S.L. (Responsable del Tratamiento)**

Nombre: _________________________________  
Cargo: _________________________________  
Firma: _________________________________  
Fecha: _________________________________  

**Por OpenRouter, Inc. (Sub-encargado)**

Nombre: _________________________________  
Cargo: _________________________________  
Firma: _________________________________  
Fecha: _________________________________  

---

## 16. Anexo I — Descripción del Tratamiento

### A. Finalidad y Naturaleza

| Aspecto | Descripción |
|---------|-------------|
| **Finalidad** | Procesamiento de lenguaje natural para atención al cliente de homologaciones |
| **Naturaleza del tratamiento** | Transmisión y procesamiento temporal (sin almacenamiento permanente) |
| **Instrucciones del Responsable** | Procesar la consulta y devolver respuesta; sin retención ni uso para entrenamiento |

### B. Datos Personales Transferidos

| Categoría | Datos Específicos | Frecuencia |
|-----------|-----------------|------------|
| Mensajes de conversación | Texto de la consulta del usuario (puede incluir nombre, teléfono si mencionado) | Por cada llamada API Tier 3 |
| Historial de conversación | Últimas N interacciones del usuario | Por cada llamada API Tier 3 |
| Identificador de sesión | Conversation ID (seudonimizado) | Por cada llamada API Tier 3 |

**Categorías especiales**: ❌ No se transfieren intencionalmente. Si un usuario menciona datos de salud, orientación sexual u otras categorías especiales en su mensaje, estos se transferirían involuntariamente.

### C. Volumen Estimado

- Frecuencia: ~30-50% de las conversaciones activas (las que requieren Tier 3)
- Volumen diario: Dependiente del tráfico de MSI-a
- Tamaño de cada llamada: ~1-5 KB (prompt + historial)

### D. Retención

- **Durante el procesamiento**: Solo el tiempo necesario para generar la respuesta (segundos)
- **Logs de OpenRouter**: [Verificar política de retención en términos de OpenRouter]
- **Petición de eliminación**: OpenRouter debe eliminar a petición del Responsable

---

## 17. Anexo II — SCCs Módulo 3 (Referencia)

Las Cláusulas Contractuales Tipo aplicables son las adoptadas por la **Decisión de Ejecución (UE) 2021/914** de la Comisión Europea, de 4 de junio de 2021.

**Texto completo en español**: https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX%3A32021D0914

**Módulo 3 — Transferencia encargado del tratamiento a encargado del tratamiento**:
- Aplica cuando exportador e importador son ambos encargados del tratamiento
- Requiere que el exportador tenga autorización del responsable para el sub-encargo
- El importador solo puede actuar según instrucciones del exportador

---

## Historial de Versiones

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0 | Febrero 2026 | Versión inicial (borrador Zanovix) |
| — | — | Pendiente verificación DPF de OpenRouter |
| — | — | Pendiente decisión sobre DeepSeek (Sección 7) |
| — | — | Pendiente validación abogado RGPD |
| — | — | Pendiente firma de todas las partes |

---

> 💡 **Nota para el equipo**: OpenRouter puede tener su propio DPA/MSA. Antes de usar este borrador en su totalidad, solicitar el DPA oficial de OpenRouter. Si cumple con el Art. 28 RGPD, puede ser más eficiente usarlo como base e incorporar las cláusulas específicas de este borrador (especialmente anti-entrenamiento y cláusula sobre DeepSeek/China).

*Este documento es un borrador técnico redactado por Zanovix. No tiene valor jurídico hasta ser validado por abogado especialista en RGPD y aprobado y firmado por todas las partes.*
