# Texto de Consentimiento Granular para el Tratamiento de Datos
## Sistema MSI-a — WhatsApp Chatbot

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

1. [Análisis de Bases Jurídicas](#1-análisis-de-bases-jurídicas)
2. [Mapa de Tratamientos y Bases Jurídicas](#2-mapa-de-tratamientos-y-bases-jurídicas)
3. [Texto del Aviso de Primera Interacción](#3-texto-del-aviso-de-primera-interacción)
4. [Formulario de Consentimiento Granular (cuando aplica)](#4-formulario-de-consentimiento-granular-cuando-aplica)
5. [Flujo de Obtención del Consentimiento](#5-flujo-de-obtención-del-consentimiento)
6. [Gestión del Consentimiento (Registro y Revocación)](#6-gestión-del-consentimiento-registro-y-revocación)
7. [Consentimiento Específico para Transferencias Internacionales](#7-consentimiento-específico-para-transferencias-internacionales)
8. [Textos para Diferentes Canales](#8-textos-para-diferentes-canales)
9. [Aprobación](#9-aprobación)

---

## 1. Análisis de Bases Jurídicas

### 1.1 Principio General

El consentimiento (Art. 6.1.a RGPD) NO es la única base jurídica posible ni siempre la más adecuada. Antes de solicitar consentimiento, debe analizarse si existe otra base jurídica más apropiada.

Requisitos del consentimiento válido (Art. 7 RGPD):
- **Libre**: Sin condicionarlo al acceso al servicio (salvo que sea estrictamente necesario)
- **Específico**: Para finalidades concretas y determinadas
- **Informado**: El interesado conoce exactamente para qué consiente
- **Inequívoco**: Acción positiva y afirmativa (no casillas pre-marcadas)
- **Revocable**: En cualquier momento, sin perjuicio para el interesado

### 1.2 ¿Cuándo Usar el Consentimiento vs. Otras Bases?

| Tratamiento | Base Más Adecuada | Justificación |
|-------------|-------------------|---------------|
| Atender consulta de homologación | **Interés legítimo** (Art. 6.1.f) o **ejecución de contrato** | El usuario contacta para obtener información comercial |
| Calcular presupuesto | **Ejecución de contrato** / **Interés legítimo** | Es el objeto de la interacción |
| Abrir expediente de homologación | **Ejecución de contrato** (Art. 6.1.b) | Relación contractual con MSI Automotive |
| Marketing / comunicaciones comerciales | **Consentimiento** (Art. 6.1.a) | Obligatorio para marketing directo |
| Transferencia a LLM en China (DeepSeek) | **Consentimiento explícito** (Art. 49.1.a) | No hay base adecuada alternativa |
| Retención para mejora del servicio | **Interés legítimo** (Art. 6.1.f) | Con ponderación de intereses |
| Compartir con terceros para sus propios fines | **Consentimiento** (Art. 6.1.a) | Obligatorio |

---

## 2. Mapa de Tratamientos y Bases Jurídicas

### 2.1 Tabla Completa de Tratamientos MSI-a

| ID | Tratamiento | Datos | Base Jurídica | Legitimación Detallada |
|----|-------------|-------|---------------|------------------------|
| **T-01** | Atención consultas WhatsApp | Teléfono, mensajes, tipo vehículo | Art. 6.1.b/f | Ejecución precontractual + interés legítimo |
| **T-02** | Cálculo presupuestos | Tipo vehículo, elementos, teléfono | Art. 6.1.b/f | Ejecución precontractual |
| **T-03** | Apertura expediente homologación | Datos personales, vehículo, docs | Art. 6.1.b | Ejecución del contrato de homologación |
| **T-04** | Registro en sistema CRM (Chatwoot) | Nombre, teléfono, historial | Art. 6.1.b/f | Gestión comercial + interés legítimo |
| **T-05** | Logs de auditoría y trazabilidad | Conversación, acciones del agente | Art. 6.1.f | Interés legítimo (seguridad y cumplimiento) |
| **T-06** | Métricas de uso del servicio | Datos anonimizados/seudonimizados | Art. 6.1.f | Interés legítimo (mejora del servicio) |
| **T-07** | Comunicaciones comerciales posteriores | Teléfono, email | **Art. 6.1.a** | **Requiere consentimiento** |
| **T-08** | Transferencia a OpenRouter (EE.UU.) | Mensajes de conversación | Art. 46 RGPD (SCCs/DPF) | Garantías adecuadas |
| **T-09** | Transferencia a DeepSeek (China) | Mensajes de conversación | **Art. 49.1.a RGPD** | **Requiere consentimiento explícito** |
| **T-10** | Uso de datos para entrenamiento LLM | Mensajes de conversación | **Art. 6.1.a** | **Requiere consentimiento (si aplica)** |

> 💡 **Nota**: Los tratamientos T-01 a T-06 **no requieren consentimiento** si se basan correctamente en interés legítimo o ejecución de contrato. Se recomienda no solicitar consentimiento para estos tratamientos para no crear una falsa expectativa de que todos los tratamientos son opcionales.

---

## 3. Texto del Aviso de Primera Interacción

Este es el mensaje que MSI-a enviará **al inicio de cada primera conversación** con un usuario nuevo.

### 3.1 Versión Completa (Recomendada)

```
¡Hola! 👋 Soy el asistente virtual de MSI Automotive.

Soy una inteligencia artificial (no soy un agente humano). Puedo ayudarte con consultas sobre homologaciones de vehículos y presupuestos.

ℹ️ INFORMACIÓN SOBRE TUS DATOS

Para atenderte, necesitamos tratar algunos de tus datos personales:

• Tu número de WhatsApp y los mensajes que nos envíes
• Información sobre tu vehículo y las modificaciones que quieras homologar

📋 ¿Para qué usamos tus datos?
Únicamente para gestionar tu consulta y, si lo solicitas, para abrir un expediente de homologación. No los cedemos a terceros para sus propios fines.

⚙️ ¿Quién trata tus datos?
MSI Automotive S.L. (Responsable). Utilizamos herramientas de inteligencia artificial que procesan tus mensajes para poder responderte.

📖 Más información: [enlace política de privacidad]

🗑️ Puedes solicitar la eliminación de tus datos en: privacidad@msiautomotive.es

¿Podemos continuar y ayudarte?
```

**Acciones del usuario**:
- Escribir cualquier mensaje → Se interpreta como consentimiento para T-01 a T-06 bajo interés legítimo / precontractual (no consentimiento formal)
- El usuario puede preguntar más información antes de continuar

### 3.2 Versión Compacta (Para implementación técnica)

```
👋 Soy el asistente virtual IA de MSI Automotive.

Usaré tu número de WhatsApp y los mensajes que me envíes para gestionar tu consulta sobre homologaciones. Más info: [enlace]. Para eliminar tus datos: privacidad@msiautomotive.es

¿En qué puedo ayudarte?
```

### 3.3 Consideraciones sobre el Aviso de Primera Interacción

**¿Es un consentimiento?** No estrictamente. Es una **información** (Art. 13 RGPD) que se proporciona al inicio de la relación. Los tratamientos T-01 a T-06 se basan en interés legítimo/precontractual, no en consentimiento.

**¿Qué pasa si el usuario no responde?** Si el usuario no responde al aviso pero después envía un mensaje, se entiende que acepta el tratamiento bajo las bases jurídicas de interés legítimo/precontractual para la gestión de su consulta.

**¿Qué pasa si el usuario dice que no quiere sus datos tratados?** El servicio no puede prestarse sin tratar los datos mínimos. Se le debe informar de esta limitación y ofrecer alternativas (contacto telefónico o presencial).

---

## 4. Formulario de Consentimiento Granular (cuando aplica)

El consentimiento granular se solicita **solo para tratamientos que lo requieren** (T-07, T-09, T-10).

### 4.1 Consentimiento para Comunicaciones Comerciales (T-07)

Se solicita al finalizar la primera interacción satisfactoria:

```
¿Te gustaría recibir información sobre nuestras promociones y novedades en homologaciones?

Puedes escribir:
✅ "SÍ" → Recibirás información comercial ocasional por WhatsApp
❌ "NO" → No recibirás comunicaciones comerciales

Puedes cambiar tu preferencia en cualquier momento escribiendo "no quiero publicidad".
```

**Base jurídica si acepta**: Art. 6.1.a RGPD (consentimiento)  
**Revocación**: El usuario puede escribir "no quiero publicidad" / "baja comunicaciones" en cualquier momento

### 4.2 Consentimiento para Transferencia a DeepSeek/China (T-09)

> ⚠️ **NOTA**: Este consentimiento solo es necesario **si se mantiene DeepSeek como proveedor LLM**. Si se migra a Mistral AI (UE), este consentimiento **no es necesario**. Se recomienda prioritariamente migrar a Mistral AI y eliminar esta complejidad.

Si se mantiene DeepSeek, se debe solicitar consentimiento **previo y explícito** con la siguiente información:

```
⚠️ INFORMACIÓN IMPORTANTE SOBRE TUS DATOS

Para responder a consultas complejas, utilizamos un servicio de inteligencia 
artificial cuyo proveedor puede estar localizado fuera de la Unión Europea, 
incluyendo en China.

Esto significa que tus mensajes pueden ser procesados por servidores en 
países que no garantizan el mismo nivel de protección de datos que la UE.

Los riesgos específicos incluyen:
• Posible acceso a tus datos por autoridades del país de destino
• Menor capacidad de ejercer tus derechos de protección de datos

¿Aceptas que tus mensajes puedan ser procesados fuera de la UE para 
que podamos responderte mejor?

✅ "ACEPTO" → Activaremos el servicio de IA avanzado
❌ "NO ACEPTO" → Solo usaremos servicios de IA dentro de la UE 
               (las respuestas pueden ser más limitadas)

Este consentimiento es voluntario y puedes revocarlo escribiendo 
"revocar consentimiento IA" en cualquier momento.
```

**Requisitos legales para este consentimiento**:
- ✅ Libre (el servicio básico sigue disponible sin este consentimiento)
- ✅ Específico (solo para transferencia a país tercero)
- ✅ Informado (se explican los riesgos específicos)
- ✅ Inequívoco (acción positiva "ACEPTO")
- ✅ Revocable

### 4.3 Consentimiento para Uso en Entrenamiento LLM (T-10)

Solo aplicable si OpenRouter/DeepSeek usan los datos para entrenamiento:

```
¿Nos permites usar tus conversaciones (de forma anónima) para mejorar 
nuestro servicio de atención al cliente?

✅ "SÍ AL ENTRENAMIENTO" → Aceptas el uso anónimo de datos
❌ "NO AL ENTRENAMIENTO" → No se usarán tus datos para entrenamiento

Nota: En ambos casos recibirás el mismo servicio.
```

> 💡 **Recomendación**: Negociar con OpenRouter términos que excluyan el uso de datos para entrenamiento (Data Processing Agreement con cláusula opt-out). Esto evitaría solicitar este consentimiento.

---

## 5. Flujo de Obtención del Consentimiento

### 5.1 Diagrama de Flujo

```
Usuario envía primer mensaje
          ↓
¿Es usuario nuevo en el sistema?
    ↙ SÍ                 NO ↘
Enviar aviso        Continuar normalmente
primera interacción
    ↓
Usuario responde
    ↓
¿Responde con mensaje normal?
    ↙ SÍ                 NO ↘
Continuar con        Esperar o
tratamiento bajo     preguntar
interés legítimo
    ↓
Primera interacción completa
    ↓
[Opcional] Preguntar sobre comunicaciones comerciales (T-07)
    ↓
[Si aplica DeepSeek] Solicitar consentimiento transferencia (T-09)
    ↓
Registrar estado del consentimiento en PostgreSQL
```

### 5.2 Momentos de Solicitud de Consentimiento

| Consentimiento | Momento | Canal | Obligatorio |
|----------------|---------|-------|-------------|
| Info primera interacción (Art. 13) | Primer mensaje | WhatsApp | ✅ Sí |
| Comunicaciones comerciales (T-07) | Fin primera conversación | WhatsApp | Solo si se va a hacer marketing |
| Transferencia DeepSeek (T-09) | Antes de primera llamada a DeepSeek | WhatsApp | ✅ Sí (si se usa DeepSeek) |
| Entrenamiento LLM (T-10) | Primer mensaje o configuración | WhatsApp/Web | Solo si el proveedor entrena con datos |

---

## 6. Gestión del Consentimiento (Registro y Revocación)

### 6.1 Modelo de Datos para Registro del Consentimiento

Se debe implementar una tabla en PostgreSQL para registrar los consentimientos:

```sql
-- Tabla propuesta para registro de consentimientos
CREATE TABLE user_consents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type VARCHAR(50) NOT NULL,
    -- Valores: 'marketing', 'third_country_transfer', 'llm_training'
    granted BOOLEAN NOT NULL,
    granted_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    consent_text TEXT NOT NULL,  -- Texto exacto que vio el usuario
    collection_method VARCHAR(50) NOT NULL,  -- 'whatsapp', 'web', 'phone'
    ip_address INET,  -- Si aplica
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices
CREATE INDEX idx_user_consents_user_id ON user_consents(user_id);
CREATE INDEX idx_user_consents_type ON user_consents(consent_type);
```

### 6.2 Implementación en el Agente

```python
# Propuesta para agent/services/consent_service.py

from enum import Enum
from datetime import datetime, UTC
from uuid import UUID

class ConsentType(str, Enum):
    MARKETING = "marketing"
    THIRD_COUNTRY_TRANSFER = "third_country_transfer"
    LLM_TRAINING = "llm_training"

async def record_consent(
    user_id: UUID,
    consent_type: ConsentType,
    granted: bool,
    consent_text: str,
    collection_method: str = "whatsapp",
) -> None:
    """Record user consent decision in PostgreSQL."""
    async with get_async_session() as session:
        consent = UserConsent(
            user_id=user_id,
            consent_type=consent_type.value,
            granted=granted,
            granted_at=datetime.now(UTC) if granted else None,
            consent_text=consent_text,
            collection_method=collection_method,
        )
        session.add(consent)
        await session.commit()

async def has_valid_consent(
    user_id: UUID,
    consent_type: ConsentType,
) -> bool:
    """Check if user has valid (non-revoked) consent."""
    async with get_async_session() as session:
        result = await session.execute(
            select(UserConsent)
            .where(UserConsent.user_id == user_id)
            .where(UserConsent.consent_type == consent_type.value)
            .where(UserConsent.granted == True)
            .where(UserConsent.revoked_at == None)
            .order_by(UserConsent.granted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

async def revoke_consent(
    user_id: UUID,
    consent_type: ConsentType,
) -> None:
    """Revoke all active consents of given type for user."""
    async with get_async_session() as session:
        await session.execute(
            update(UserConsent)
            .where(UserConsent.user_id == user_id)
            .where(UserConsent.consent_type == consent_type.value)
            .where(UserConsent.revoked_at == None)
            .values(revoked_at=datetime.now(UTC))
        )
        await session.commit()
```

### 6.3 Palabras Clave para Revocación (en el Agente)

El agente debe reconocer las siguientes expresiones como solicitudes de revocación:

```python
REVOCATION_KEYWORDS = [
    "no quiero publicidad",
    "baja comunicaciones",
    "no más mensajes",
    "quiero borrar mis datos",
    "elimina mis datos",
    "revocar consentimiento",
    "retirar consentimiento",
    "no quiero que uses mis datos",
    "derecho de supresión",
    "derecho al olvido",
]

DERECHOS_KEYWORDS = [
    "mis derechos",
    "protección de datos",
    "quién tiene mis datos",
    "qué datos tenéis",
    "acceso a mis datos",
    "rectificar",
    "portabilidad",
]
```

---

## 7. Consentimiento Específico para Transferencias Internacionales

### 7.1 Cuándo Aplica

El Art. 49.1.a RGPD permite transferencias a terceros países sin base adecuada **si el interesado ha dado consentimiento explícito** habiendo sido informado de:
- Los riesgos de la transferencia
- La ausencia de decisión de adecuación
- La ausencia o insuficiencia de garantías adecuadas

### 7.2 Texto Completo para Consentimiento de Transferencia Internacional

Para la transferencia a DeepSeek (China):

```
INFORMACIÓN SOBRE TRANSFERENCIA DE DATOS FUERA DE LA UNIÓN EUROPEA

MSI Automotive S.L., para responder a tus consultas más complejas, 
puede utilizar un servicio de inteligencia artificial cuyos servidores 
están ubicados en China (DeepSeek AI).

IMPORTANTE — Antes de continuar, necesitas saber:

1. China NO tiene una decisión de adecuación de la UE, lo que significa 
   que las leyes chinas de protección de datos no garantizan el mismo 
   nivel de protección que el RGPD europeo.

2. La legislación china (Ley de Inteligencia Nacional, Art. 7) obliga 
   a las empresas chinas a cooperar con los servicios de inteligencia 
   del Estado si así se les requiere.

3. Puede resultar difícil o imposible ejercer tus derechos de protección 
   de datos (acceso, rectificación, supresión) frente a entidades chinas.

4. Este consentimiento es completamente voluntario. Si no lo otorgas, 
   tu consulta será atendida por nuestros sistemas de IA dentro de la UE, 
   aunque con capacidades más limitadas.

¿OTORGAS TU CONSENTIMIENTO EXPLÍCITO para que tus mensajes puedan ser 
procesados por el servicio de IA ubicado en China?

Responde:
✅ "ACEPTO TRANSFERENCIA" → Consientes la transferencia a China
❌ "NO ACEPTO" → Solo usaremos IA ubicada en la UE

Puedes revocar este consentimiento en cualquier momento escribiendo 
"revocar consentimiento transferencia" o contactando con nosotros en 
privacidad@msiautomotive.es
```

**Versión resumida para WhatsApp** (máx. recomendado ~500 caracteres):

```
⚠️ Para respuestas más completas, usamos IA en servidores de China 
(sin garantías RGPD equivalentes — riesgo de acceso gubernamental).

¿Consientes el uso de IA en China?
✅ "SÍ ACEPTO" | ❌ "NO ACEPTO" (usaremos solo IA en la UE)

Info completa: [enlace]. Puedes revocar escribiendo "revocar consentimiento".
```

---

## 8. Textos para Diferentes Canales

### 8.1 WhatsApp (Canal Principal)

**Restricciones técnicas**:
- Mensajes largos pueden fragmentarse
- No hay botones interactivos en todos los tipos de cuenta WhatsApp Business
- Los emojis son útiles para claridad

**Estrategia**: Usar mensajes cortos con enlace a información completa en web.

### 8.2 Sitio Web MSI Automotive (Información Complementaria)

Se recomienda crear una página `/privacidad/whatsapp` con:
- Texto completo de la política de privacidad (borrador ya redactado)
- FAQs sobre el chatbot de IA
- Formulario de ejercicio de derechos

### 8.3 Recordatorio Periódico

Se recomienda enviar un recordatorio anual a usuarios activos:

```
Hola de nuevo. Queremos recordarte que seguimos gestionando tus 
datos de acuerdo con nuestra Política de Privacidad: [enlace]

Si quieres modificar tus preferencias o eliminar tus datos, 
escríbenos a privacidad@msiautomotive.es o escribe "mis derechos".
```

---

## 9. Aprobación

Este documento debe ser aprobado por:

| Rol | Nombre | Fecha | Firma |
|-----|--------|-------|-------|
| Representante Legal MSI Automotive S.L. | _________________ | _______ | _______ |
| Delegado de Protección de Datos (si designado) | _________________ | _______ | _______ |
| Abogado RGPD externo | _________________ | _______ | _______ |
| Responsable Técnico (Zanovix) | _________________ | _______ | _______ |

---

## Anexo A — Palabras de Ejercicio de Derechos

El agente debe reconocer las siguientes expresiones y redirigir al canal adecuado:

```python
# Para integrar en agent/utils/gdpr_keywords.py

GDPR_EXERCISE_KEYWORDS = {
    "acceso": [
        "qué datos tenéis de mí",
        "quiero ver mis datos",
        "acceso a mis datos",
        "derecho de acceso",
    ],
    "rectificacion": [
        "corregir mis datos",
        "mis datos están mal",
        "rectificar",
        "actualizar mis datos",
    ],
    "supresion": [
        "borrar mis datos",
        "eliminar mis datos",
        "derecho al olvido",
        "quiero que borréis todo",
        "supresión",
    ],
    "portabilidad": [
        "mis datos en formato electrónico",
        "portabilidad",
        "quiero una copia de mis datos",
    ],
    "oposicion": [
        "no quiero que uséis mis datos",
        "me opongo al tratamiento",
        "oposición",
    ],
    "limitacion": [
        "limitar el tratamiento",
        "que no uséis mis datos temporalmente",
    ],
}

GDPR_RESPONSE_TEMPLATE = """
Para ejercer tus derechos de protección de datos, puedes:

📧 Email: privacidad@msiautomotive.es
📬 Correo postal: MSI Automotive S.L., [dirección], [ciudad], España

Tienes derecho a:
• Acceder a tus datos
• Rectificarlos si son incorrectos
• Solicitar su eliminación
• Portabilidad de tus datos
• Oponerte al tratamiento
• Presentar reclamación ante la AEPD: www.aepd.es

Responderemos en un máximo de 30 días.
"""
```

---

## Anexo B — Historial de Versiones

| Versión | Fecha | Autor | Cambios |
|---------|-------|-------|---------|
| 1.0 | Febrero 2026 | Zanovix (borrador) | Versión inicial |
| — | — | Abogado RGPD | Pendiente validación jurídica |
| — | — | MSI Automotive | Pendiente aprobación y firma |

---

*Este documento es un borrador técnico redactado por Zanovix. No tiene valor jurídico hasta ser validado por abogado especialista en RGPD y aprobado y firmado por MSI Automotive S.L.*
