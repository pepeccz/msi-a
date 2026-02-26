# Procedimiento Interno de Gestión de Brechas de Seguridad
## Art. 33-34 RGPD — MSI Automotive S.L. / Sistema MSI-a

**Versión**: 1.0 (BORRADOR — pendiente validación abogado RGPD)  
**Fecha**: Febrero 2026  
**Responsable del tratamiento**: MSI Automotive S.L.  
**Encargado del tratamiento**: Zanovix (agencia de desarrollo)  
**Redactado por**: Zanovix (para revisión y aprobación de MSI Automotive S.L.)  
**Clasificación**: ⚖️ Requiere validación jurídica externa  

---

> ⚠️ **NOTA LEGAL IMPORTANTE**
>
> Este documento es un **borrador técnico** redactado por Zanovix en su calidad de encargado del tratamiento.
> Antes de ser adoptado oficialmente, **debe ser revisado y validado por un abogado especialista en RGPD**,
> y posteriormente **aprobado y firmado por MSI Automotive S.L.** como responsable del tratamiento.

---

## Índice

1. [Marco Normativo](#1-marco-normativo)
2. [Alcance y Definiciones](#2-alcance-y-definiciones)
3. [Roles y Responsabilidades](#3-roles-y-responsabilidades)
4. [Clasificación de Brechas](#4-clasificación-de-brechas)
5. [Procedimiento de Detección y Notificación Interna](#5-procedimiento-de-detección-y-notificación-interna)
6. [Evaluación de la Brecha](#6-evaluación-de-la-brecha)
7. [Notificación a la AEPD (Art. 33 RGPD)](#7-notificación-a-la-aepd-art-33-rgpd)
8. [Notificación a los Interesados (Art. 34 RGPD)](#8-notificación-a-los-interesados-art-34-rgpd)
9. [Contención y Remediación](#9-contención-y-remediación)
10. [Registro de Brechas (Art. 33.5 RGPD)](#10-registro-de-brechas-art-335-rgpd)
11. [Revisión Post-Incidente](#11-revisión-post-incidente)
12. [Plantillas de Notificación](#12-plantillas-de-notificación)
13. [Aprobación y Revisiones](#13-aprobación-y-revisiones)

---

## 1. Marco Normativo

| Norma | Artículo | Obligación |
|-------|---------|------------|
| **RGPD (UE) 2016/679** | Art. 33 | Notificación de brecha a la autoridad supervisora en 72h |
| **RGPD (UE) 2016/679** | Art. 34 | Comunicación a interesados cuando el riesgo sea alto |
| **RGPD (UE) 2016/679** | Art. 33.5 | Registro interno de todas las brechas |
| **RGPD (UE) 2016/679** | Art. 28.3.f | Encargado notifica al responsable sin dilación |
| **Orientaciones AEPD sobre IA Agéntica** | 2026 | Gestión de incidentes en sistemas de IA |
| **WP29 Guidelines on Personal Data Breach Notification** | Guidelines 01/2018 | Metodología de evaluación |

---

## 2. Alcance y Definiciones

### 2.1 Alcance

Este procedimiento aplica a:
- El sistema **MSI-a** (agente conversacional WhatsApp de MSI Automotive)
- Todos los componentes del sistema: API, Agent, Base de datos (PostgreSQL, Redis, Qdrant), Admin Panel
- Los sistemas de terceros que procesan datos de MSI Automotive: Chatwoot, OpenRouter, proveedor de hosting

### 2.2 Definiciones

| Término | Definición |
|---------|-----------|
| **Brecha de seguridad** | Violación de la seguridad que ocasione la destrucción, pérdida o alteración accidental o ilícita de datos personales transmitidos, conservados o tratados de otra forma, o la comunicación o acceso no autorizados (Art. 4.12 RGPD) |
| **Responsable** | MSI Automotive S.L. |
| **Encargado** | Zanovix (agencia de desarrollo) |
| **Interesado** | Los usuarios que contactan a MSI Automotive vía WhatsApp |
| **AEPD** | Agencia Española de Protección de Datos |
| **DPD** | Delegado de Protección de Datos (si designado) |

### 2.3 Tipos de Brechas

| Tipo | Descripción | Ejemplo en MSI-a |
|------|-------------|------------------|
| **Confidencialidad** | Divulgación no autorizada de datos | Acceso no autorizado a conversaciones en Chatwoot |
| **Integridad** | Alteración no autorizada de datos | Modificación de expedientes en PostgreSQL |
| **Disponibilidad** | Pérdida de acceso a datos | Corrupción de la base de datos Redis |

---

## 3. Roles y Responsabilidades

### 3.1 Equipo de Respuesta a Incidentes

| Rol | Persona/Entidad | Responsabilidades |
|-----|-----------------|-------------------|
| **Coordinador de incidentes** | [Responsable designado en MSI Automotive — completar] | Coordina la respuesta, decide notificaciones |
| **Responsable técnico** | Zanovix (equipo de desarrollo) | Análisis técnico, contención, remediación |
| **Responsable legal** | Abogado RGPD externo | Evaluación jurídica, redacción notificaciones |
| **DPD (si designado)** | [Completar si aplica] | Asesoramiento, supervisión del proceso |
| **Comunicación** | [Responsable en MSI Automotive — completar] | Comunicación con interesados y medios |

### 3.2 Cadena de Notificación Interna

```
Detección (cualquier fuente)
         ↓ INMEDIATAMENTE
Zanovix / Equipo Técnico (análisis inicial)
         ↓ < 4 HORAS
MSI Automotive (coordinador de incidentes)
         ↓ < 12 HORAS
Abogado RGPD externo (evaluación jurídica)
         ↓ < 24 HORAS
Decisión: ¿Notificar a AEPD?
         ↓ < 72 HORAS desde detección
AEPD (si procede)
         ↓ Sin dilación indebida (si riesgo alto)
Interesados afectados (si procede)
```

---

## 4. Clasificación de Brechas

### 4.1 Niveles de Severidad

| Nivel | Criterios | Tiempo de Respuesta |
|-------|-----------|---------------------|
| **CRÍTICO** | Exposición masiva de datos, acceso no autorizado a sistemas, ransomware | Inmediato — activar protocolo de emergencia |
| **ALTO** | Exposición de datos de un número significativo de usuarios, pérdida de integridad | < 2 horas |
| **MEDIO** | Exposición limitada, incidente contenido, riesgo bajo para interesados | < 8 horas |
| **BAJO** | Incidente con impacto mínimo o nulo en interesados, recuperable | < 24 horas |

### 4.2 Escenarios Específicos de MSI-a

| Escenario | Nivel | ¿Notificar AEPD? | ¿Notificar Interesados? |
|-----------|-------|-------------------|------------------------|
| Acceso no autorizado a toda la BD PostgreSQL | CRÍTICO | ✅ Sí | ✅ Sí (riesgo alto) |
| Filtración de conversaciones de WhatsApp | CRÍTICO | ✅ Sí | ✅ Sí (riesgo alto) |
| Acceso no autorizado a Chatwoot (todos los usuarios) | CRÍTICO | ✅ Sí | ✅ Sí |
| Brecha en OpenRouter/DeepSeek (datos procesados) | ALTO | ✅ Sí | ⚠️ Evaluar caso a caso |
| Exposición de logs de auditoría (tool_call_logs) | ALTO | ✅ Sí | ⚠️ Evaluar |
| Acceso no autorizado a un expediente individual | MEDIO | ✅ Sí | ✅ Sí (para el afectado) |
| Corrupción de datos de Redis (sin exposición) | MEDIO | ⚠️ Evaluar | ❌ Probablemente no |
| Error de configuración corregido en < 1 hora | BAJO | ⚠️ Evaluar | ❌ Probablemente no |
| Acceso interno no autorizado por empleado | Depende | ✅ Generalmente sí | Depende del alcance |

---

## 5. Procedimiento de Detección y Notificación Interna

### 5.1 Canales de Detección

| Canal | Descripción |
|-------|-------------|
| **Monitorización automática** | Alertas del sistema (logs, métricas) — Zanovix |
| **Reporte interno** | Empleados de MSI Automotive detectan algo anómalo |
| **Notificación de tercero** | Chatwoot, OpenRouter, proveedor hosting notifican una brecha |
| **Usuario afectado** | Un usuario reporta acceso no autorizado a sus datos |
| **Investigador externo** | Reporte de vulnerabilidad o brecha por tercero |

### 5.2 Primer Paso: Contención Inmediata

Al detectar un posible incidente, **antes de cualquier evaluación**:

```
1. NO borrar ningún log ni evidencia (preservar para investigación)
2. Si es activo: aislar el sistema afectado (sin apagarlo si es posible)
3. Cambiar credenciales de acceso comprometidas
4. Documentar la hora exacta de detección
5. Notificar a Zanovix y MSI Automotive INMEDIATAMENTE
```

### 5.3 Formulario de Reporte Inicial (Interno)

Cuando se detecta un posible incidente, rellenar este formulario y enviar a [email de incidentes — completar]:

```
REPORTE INICIAL DE INCIDENTE DE SEGURIDAD
==========================================
Fecha y hora de detección: _______________
Reportado por: ___________________________
Canal de detección: ______________________

Descripción del incidente:
__________________________________________

Sistemas afectados (marcar):
[ ] PostgreSQL (base de datos principal)
[ ] Redis (caché y streams)
[ ] Chatwoot (CRM)
[ ] Admin Panel
[ ] Agente LangGraph
[ ] API FastAPI
[ ] Qdrant (vectores)
[ ] OpenRouter/LLM externo
[ ] Otro: ________________

Datos afectados (estimación):
[ ] Datos de contacto (teléfonos)
[ ] Conversaciones de WhatsApp
[ ] Expedientes de homologación
[ ] Métricas/logs internos
[ ] Credenciales de acceso
[ ] Otro: ________________

Número estimado de usuarios afectados: ______

¿Se ha contenido el incidente? [ ] Sí [ ] No [ ] Parcialmente

Acciones inmediatas tomadas:
__________________________________________

FIRMA: _______________ HORA: ____________
```

---

## 6. Evaluación de la Brecha

### 6.1 Metodología de Evaluación

Seguir la metodología del **WP29 Guidelines 01/2018** y las **Directrices 01/2021 del EDPB** sobre notificación de brechas:

#### Paso 1: Confirmar que es una brecha de datos personales

Una brecha de seguridad solo requiere notificación RGPD si afecta a **datos personales**. Preguntarse:
- ¿Los datos afectados pueden identificar a personas físicas?
- ¿Incluyen nombres, teléfonos, correos, conversaciones de usuarios?
- ¿Incluyen datos de vehículos vinculados a personas identificables?

Si la respuesta es **no** a todas → No es brecha RGPD (pero sí puede ser incidente de seguridad).

#### Paso 2: Evaluar probabilidad de riesgo para interesados

| Factor | Peso |
|--------|------|
| **Tipo de datos** — sensibilidad (datos de contacto, financieros, especiales) | Alto |
| **Número de interesados afectados** — más = mayor riesgo | Alto |
| **Naturaleza de la violación** — confidencialidad, integridad, disponibilidad | Medio |
| **Identificabilidad** — ¿se puede identificar directamente a los afectados? | Alto |
| **Consecuencias potenciales** — discriminación, fraude, suplantación | Alto |
| **Características especiales de los interesados** — menores, vulnerables | Medio |

#### Paso 3: Determinar el nivel de riesgo

| Nivel | Criterio | Acción |
|-------|----------|--------|
| **Sin riesgo** | Datos cifrados, no identificables, error interno sin exposición | No notificar |
| **Riesgo bajo** | Exposición limitada, datos no sensibles, pocas personas | Registrar internamente |
| **Riesgo medio** | Posible impacto en derechos de interesados | **Notificar a AEPD** |
| **Riesgo alto** | Probable perjuicio significativo para interesados | **Notificar a AEPD + Interesados** |

### 6.2 Árbol de Decisión para Notificación a AEPD

```
¿Es una brecha de datos personales?
    ↙ NO                        SÍ ↘
No notificar              ¿Puede causar riesgo para
Registrar internamente    derechos de personas físicas?
                              ↙ NO              SÍ ↘
                          Registrar         Notificar a AEPD
                          internamente      en < 72 horas
                                                ↓
                                    ¿El riesgo es ALTO?
                                        ↙ NO       SÍ ↘
                                    Solo AEPD   AEPD + Interesados
```

---

## 7. Notificación a la AEPD (Art. 33 RGPD)

### 7.1 Plazo

**72 horas** desde que el Responsable tenga conocimiento de la brecha.

> ⚠️ El plazo empieza cuando el **Responsable (MSI Automotive)** tiene conocimiento, no cuando Zanovix lo detecta. Por eso Zanovix debe notificar a MSI Automotive lo antes posible.

Si no es posible proporcionar toda la información en 72 horas, se puede notificar por fases (Art. 33.4 RGPD), indicando que la información se completará próximamente.

### 7.2 Canal de Notificación

**Sede Electrónica de la AEPD**: https://sedeagpd.gob.es  
**Formulario**: "Notificación de brechas de seguridad (Art. 33 RGPD)"  
**Alternativa**: Notificación en papel en la sede de la AEPD

### 7.3 Información Mínima a Incluir (Art. 33.3 RGPD)

| Información | Descripción |
|-------------|-------------|
| **Naturaleza de la violación** | Tipo de brecha (confidencialidad/integridad/disponibilidad), cómo ocurrió |
| **Categorías de datos** | Qué tipo de datos personales se vieron afectados |
| **Categorías de interesados** | Quiénes son las personas afectadas (clientes, empleados, etc.) |
| **Número aproximado** | Cuántas personas y registros afectados (estimación si no es posible exacto) |
| **Contacto DPD** | Nombre y datos del Delegado de Protección de Datos (si designado) |
| **Consecuencias probables** | Qué impacto puede tener la brecha |
| **Medidas adoptadas** | Qué se ha hecho para contener y remediar la brecha |

### 7.4 Proceso Interno Previo a la Notificación

```
1. Zanovix completa el análisis técnico (documentar hallazgos)
2. Abogado RGPD redacta el borrador de la notificación
3. MSI Automotive revisa y aprueba
4. MSI Automotive presenta en sede electrónica AEPD
5. Guardar acuse de recibo en el Registro de Brechas
```

---

## 8. Notificación a los Interesados (Art. 34 RGPD)

### 8.1 Cuándo Notificar

Solo obligatorio cuando la brecha **probablemente entrañe un alto riesgo para los derechos y libertades de las personas físicas** (Art. 34.1 RGPD).

Ejemplos de **riesgo alto** en MSI-a:
- Exposición de conversaciones completas de WhatsApp (datos de contacto + contenido)
- Exposición de datos de expedientes de homologación (puede incluir datos del vehículo y personales)
- Acceso no autorizado que permita suplantación de identidad

### 8.2 Excepciones a la Notificación a Interesados (Art. 34.3 RGPD)

No es necesario notificar a los interesados si:
- Se han aplicado medidas de cifrado adecuadas (los datos son ilegibles)
- Se han tomado medidas que garanticen que el riesgo no se va a materializar
- La notificación individual implicaría un esfuerzo desproporcionado (entonces: comunicación pública)

### 8.3 Canal de Notificación a Interesados

Para MSI-a, el canal más directo es el **WhatsApp** (el mismo canal de la relación con el usuario):

```
[Si es posible contactar individualmente]
→ Mensaje directo por WhatsApp a cada usuario afectado

[Si no es posible contactar individualmente — esfuerzo desproporcionado]
→ Comunicación pública en web de MSI Automotive
→ Aviso en el chat al inicio de la próxima conversación
```

### 8.4 Información Mínima a Incluir (Art. 34.2 RGPD)

| Información | Descripción |
|-------------|-------------|
| **Naturaleza de la brecha** | Qué ocurrió, en términos claros y sencillos |
| **Nombre y contacto** | Del DPD o punto de contacto de MSI Automotive |
| **Consecuencias probables** | Qué impacto puede tener en el interesado |
| **Medidas adoptadas** | Qué ha hecho MSI Automotive para remediar la situación |
| **Acciones recomendadas** | Qué puede hacer el interesado para protegerse |

---

## 9. Contención y Remediación

### 9.1 Acciones de Contención Inmediata

| Acción | Responsable | Plazo |
|--------|-------------|-------|
| Aislar sistema afectado | Zanovix | Inmediato |
| Revocar credenciales comprometidas | Zanovix | < 1 hora |
| Activar modo de solo lectura si necesario | Zanovix | < 1 hora |
| Preservar evidencias (logs, capturas) | Zanovix | < 1 hora |
| Notificar a proveedores afectados (Chatwoot, etc.) | MSI Automotive | < 4 horas |

### 9.2 Acciones de Remediación

| Acción | Descripción |
|--------|-------------|
| **Análisis forense** | Determinar vector de ataque, alcance exacto |
| **Parche de seguridad** | Corregir la vulnerabilidad explotada |
| **Rotación de credenciales** | Cambiar todas las credenciales potencialmente comprometidas |
| **Revisión de logs** | Identificar accesos no autorizados en el período de la brecha |
| **Refuerzo de medidas** | Implementar medidas adicionales para prevenir recurrencia |
| **Pruebas de penetración** | Verificar que la brecha ha sido completamente cerrada |

### 9.3 Checklist de Remediación MSI-a

```
CONTENCIÓN:
[ ] Servicio afectado aislado o desconectado
[ ] Credenciales de BD revocadas y regeneradas
[ ] Tokens JWT invalidados (blacklist Redis)
[ ] Claves API de Chatwoot/OpenRouter rotadas
[ ] Acceso SSH/admin bloqueado temporalmente
[ ] Logs preservados (NO borrar)

ANÁLISIS:
[ ] Vector de ataque identificado
[ ] Período de la brecha determinado
[ ] Datos afectados catalogados (qué, cuánto, de quién)
[ ] Usuarios afectados identificados

REMEDIACIÓN:
[ ] Vulnerabilidad parchada
[ ] Todas las credenciales rotadas
[ ] Medidas adicionales implementadas
[ ] Tests de seguridad ejecutados
[ ] Servicio restaurado con validación

COMUNICACIÓN:
[ ] AEPD notificada (si procede) — adjuntar acuse de recibo
[ ] Interesados notificados (si procede)
[ ] Proveedores notificados (Chatwoot, OpenRouter)
[ ] Documentación del incidente completada
[ ] Registro de brechas actualizado
```

---

## 10. Registro de Brechas (Art. 33.5 RGPD)

### 10.1 Obligación Legal

El Art. 33.5 RGPD obliga al Responsable a **documentar todas las violaciones de seguridad de los datos personales**, incluyendo las que no requieren notificación a la AEPD.

### 10.2 Plantilla del Registro

**Ubicación**: `docs/compliance/registro-brechas.md` (o sistema interno de MSI Automotive)  
**Acceso**: Responsable + DPD (si designado) + Abogado RGPD externo

```markdown
## Registro de Violaciones de Seguridad
### Incidente #[NUMERO] — [YYYY-MM-DD]

**IDENTIFICACIÓN**
- Número de referencia: BRECHA-YYYY-NNN
- Fecha y hora de detección: 
- Detectado por:
- Fecha y hora de notificación a MSI Automotive:

**NATURALEZA DE LA VIOLACIÓN**
- Tipo: [ ] Confidencialidad  [ ] Integridad  [ ] Disponibilidad
- Descripción:
- Causa probable:
- Sistemas afectados:

**ALCANCE**
- Categorías de datos afectados:
- Número de interesados afectados (estimación):
- Número de registros afectados (estimación):
- Período temporal de la brecha (desde — hasta):

**EVALUACIÓN DE RIESGO**
- Nivel de riesgo: [ ] Sin riesgo  [ ] Bajo  [ ] Medio  [ ] Alto
- Justificación:

**ACCIONES TOMADAS**
- Contención:
- Remediación:
- Fecha de resolución:

**NOTIFICACIONES**
- AEPD notificada: [ ] Sí  [ ] No (razón: ___)
  - Fecha de notificación:
  - Número de referencia AEPD:
- Interesados notificados: [ ] Sí  [ ] No (razón: ___)
  - Canal utilizado:
  - Fecha de notificación:
  - Número de interesados notificados:

**LECCIONES APRENDIDAS**
- Medidas adicionales implementadas:
- Cambios en procedimientos:

**APROBACIÓN**
- Revisado por: _____________ Fecha: _______
- Abogado RGPD: _____________ Fecha: _______
```

---

## 11. Revisión Post-Incidente

Dentro de los **30 días posteriores a la resolución** del incidente, el equipo realizará una revisión que incluya:

1. **Análisis de causa raíz**: ¿Por qué ocurrió? ¿Era prevenible?
2. **Evaluación de la respuesta**: ¿Se siguió el procedimiento? ¿Fue efectivo?
3. **Lecciones aprendidas**: ¿Qué se puede mejorar?
4. **Actualización del procedimiento**: Si es necesario, actualizar este documento
5. **Informe final**: Para el responsable de MSI Automotive y el abogado RGPD

---

## 12. Plantillas de Notificación

### 12.1 Notificación a Interesados — WhatsApp

```
⚠️ AVISO IMPORTANTE DE SEGURIDAD — MSI Automotive

Hola, te contactamos porque eres cliente de MSI Automotive.

Lamentamos informarte que hemos detectado un incidente de seguridad 
que puede haber afectado a tus datos personales.

¿Qué ha ocurrido?
[DESCRIPCIÓN CLARA Y SENCILLA — completar para cada incidente]

¿Qué datos pueden estar afectados?
[DATOS ESPECÍFICOS — completar para cada incidente]

¿Qué hemos hecho?
[MEDIDAS ADOPTADAS — completar para cada incidente]

¿Qué puedes hacer tú?
[ACCIONES RECOMENDADAS — completar para cada incidente, ej:]
• Desconfía de mensajes sospechosos que parezcan de MSI Automotive
• Si crees que alguien tiene acceso a tu cuenta, contáctanos
• Puedes pedir información sobre tus datos: privacidad@msiautomotive.es

¿Tienes dudas?
📧 privacidad@msiautomotive.es
📞 [teléfono de contacto — completar]

También puedes presentar una reclamación ante la AEPD: www.aepd.es

MSI Automotive S.L. — NIF: [completar]
[Dirección]
```

### 12.2 Notificación a Encargados (Chatwoot/OpenRouter)

```
Estimado equipo de [Chatwoot / OpenRouter],

En virtud del contrato de encargo de tratamiento suscrito entre MSI Automotive S.L. 
y [nombre del encargado], les informamos de la siguiente incidencia de seguridad:

Fecha de detección: [fecha]
Descripción del incidente: [descripción técnica]
Sistemas afectados: [sistemas]
Datos potencialmente afectados: [descripción de datos]

Solicitamos su colaboración para:
1. [Acciones específicas solicitadas]
2. Proporcionarnos información sobre si sus sistemas han sido afectados
3. Notificarnos cualquier brecha en sus sistemas que pudiera afectar a los datos de MSI Automotive

Por favor, respondan a este email con carácter urgente.

[Firma MSI Automotive S.L.]
```

---

## 13. Aprobación y Revisiones

### 13.1 Aprobación del Procedimiento

| Rol | Nombre | Fecha | Firma |
|-----|--------|-------|-------|
| Representante Legal MSI Automotive S.L. | _________________ | _______ | _______ |
| DPD (si designado) | _________________ | _______ | _______ |
| Abogado RGPD externo | _________________ | _______ | _______ |
| Responsable Técnico (Zanovix) | _________________ | _______ | _______ |

### 13.2 Calendario de Revisiones

| Evento | Acción |
|--------|--------|
| Anualmente | Revisión completa del procedimiento |
| Tras cada incidente | Revisión de la sección afectada |
| Cambios significativos en el sistema MSI-a | Actualización del alcance y escenarios |
| Cambios normativos (RGPD, guías AEPD) | Actualización de requisitos legales |

### 13.3 Historial de Versiones

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0 | Febrero 2026 | Versión inicial (borrador Zanovix) |
| — | — | Pendiente validación abogado RGPD |
| — | — | Pendiente aprobación MSI Automotive |

---

## Contactos de Emergencia

| Contacto | Nombre | Teléfono | Email |
|----------|--------|----------|-------|
| **Responsable técnico principal (Zanovix)** | [completar] | [completar] | [completar] |
| **Responsable en MSI Automotive** | [completar] | [completar] | [completar] |
| **Abogado RGPD externo** | [completar] | [completar] | [completar] |
| **DPD (si designado)** | [completar] | [completar] | [completar] |
| **AEPD — Sede Electrónica** | — | — | sedeagpd.gob.es |
| **AEPD — Teléfono** | — | 901 100 099 | — |

---

*Este documento es un borrador técnico redactado por Zanovix. No tiene valor jurídico hasta ser validado por abogado especialista en RGPD y aprobado y firmado por MSI Automotive S.L.*

*El incumplimiento de la obligación de notificación del Art. 33 RGPD puede conllevar multas de hasta 10.000.000 € o el 2% del volumen de negocio mundial anual (Art. 83.4 RGPD).*
