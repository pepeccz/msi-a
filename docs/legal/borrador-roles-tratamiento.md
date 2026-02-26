# Borrador: Determinación de Roles de Tratamiento

> **Documento**: Análisis de roles RGPD para el sistema MSI-a
> **Redactado por**: Zanovix (agencia de desarrollo)
> **Fecha**: 2026-02-19
> **Estado**: BORRADOR — Pendiente de validación por abogado RGPD

---

## 1. Introducción

Este documento determina el rol que cada parte interviniente en el sistema MSI-a tiene bajo el Reglamento (UE) 2016/679 (RGPD), conforme a los artículos 4, 24, 26, 28 y 29.

### Definiciones clave del RGPD

| Término | Definición (Art. 4 RGPD) |
|---------|--------------------------|
| **Responsable del tratamiento** | Persona física o jurídica que determina los fines y medios del tratamiento |
| **Encargado del tratamiento** | Persona física o jurídica que trata datos por cuenta del responsable |
| **Subencargado** | Encargado contratado por otro encargado para realizar actividades de tratamiento específicas |
| **Responsable conjunto** | Dos o más responsables que determinan conjuntamente los fines y medios |

---

## 2. Identificación del Responsable del Tratamiento

### Responsable principal

**MSI Automotive S.L.**

| Aspecto | Detalle |
|---------|---------|
| CIF | [Completar] |
| Dirección | [Completar] |
| Actividad | Homologación de vehículos |
| Decisión sobre tratamiento | Determina qué datos se recogen, para qué finalidad, durante cuánto tiempo |

**Justificación**:
- MSI Automotive es quien decide implementar el sistema de atención al cliente por WhatsApp
- Determina qué datos solicitar a los clientes
- Fija las finalidades del tratamiento (consultas, presupuestos, expedientes)
- Establece los plazos de conservación
- Es quien responde ante los interesados y la AEPD

---

## 3. Identificación de Encargados del Tratamiento

### 3.1 Zanovix (Agencia de desarrollo)

| Aspecto | Detalle |
|---------|---------|
| Rol | **Encargado del tratamiento** |
| Actividad | Desarrollo, mantenimiento y operación del sistema MSI-a |
| Datos a los que accede | Todos los datos del sistema (BD, Redis, logs) |
| Ubicación | [Completar] |
| Base contractual | Contrato Art. 28 RGPD (ver borrador) |

**Justificación**:
- Trata datos por cuenta de MSI Automotive
- Sigue instrucciones del responsable para el desarrollo y mantenimiento
- No determina los fines del tratamiento
- Acceso completo al sistema para soporte técnico

---

### 3.2 Chatwoot (Plataforma de mensajería)

| Aspecto | Detalle |
|---------|---------|
| Rol | **Encargado del tratamiento** |
| Actividad | Gestión de conversaciones WhatsApp, almacenamiento de mensajes |
| Datos a los que accede | Contenido de mensajes, datos de contacto de usuarios |
| Ubicación | [Cloud (indicar país) / Self-hosted (servidor propio)] |
| Base contractual | Contrato Art. 28 RGPD o Terms of Service |

**Justificación**:
- Procesa mensajes por cuenta de MSI Automotive
- No determina los fines del tratamiento
- Almacena temporalmente conversaciones

**Nota**: Verificar si Chatwoot está desplegado en cloud o en servidor propio. Si es cloud, verificar su DPA (Data Processing Agreement).

---

### 3.3 OpenRouter / DeepSeek (Procesamiento LLM)

| Aspecto | Detalle |
|---------|---------|
| Rol | **Encargado del tratamiento** (vía subencargado) |
| Actividad | Procesamiento de lenguaje natural para generar respuestas |
| Datos a los que accede | Contenido parcial de conversaciones (prompts y respuestas) |
| Ubicación | Estados Unidos (OpenRouter) / China (DeepSeek) |
| Base contractual | Términos de servicio + cláusulas Art. 28 + SCCs |

**Justificación**:
- Procesa datos por cuenta de MSI Automotive (a través del sistema MSI-a)
- No determina los fines del tratamiento
- Procesamiento necesario para la funcionalidad del sistema

**ATENCIÓN - Transferencia internacional**:
- DeepSeek puede procesar datos en China (tercer país sin decisión de adecuación)
- Requiere SCCs + medidas suplementarias (ver TIA)
- Se recomienda anonimización de PII antes de envío

---

### 3.4 Proveedor de Hosting / Infraestructura

| Aspecto | Detalle |
|---------|---------|
| Rol | **Encargado del tratamiento** |
| Actividad | Alojamiento de servidores, bases de datos |
| Datos a los que accede | Acceso técnico a todos los datos (administradores de sistemas) |
| Ubicación | [Completar: Hetzner, OVH, AWS, etc.] |
| Base contractual | Contrato Art. 28 RGPD (DPA) |

**Justificación**:
- Almacena datos por cuenta de MSI Automotive
- Acceso técnico pero no funcional
- No determina fines del tratamiento

---

## 4. Terceros que NO son encargados

### 4.1 WhatsApp / Meta

| Aspecto | Detalle |
|---------|---------|
| Rol | **Responsable independiente** (no relacionado) |
| Actividad | Prestación del servicio de mensajería WhatsApp |
| Relación con MSI Automotive | Comunicación entre dos responsables independientes |

**Justificación**:
- WhatsApp/Meta es responsable de su propio tratamiento de datos
- Tiene sus propios fines (seguridad, mejora del servicio)
- Existe comunicación de datos, pero cada parte es responsable de su tratamiento
- Verificar cumplimiento de términos de servicio de WhatsApp Business API

---

### 4.2 Qdrant (Base de datos vectorial para RAG)

| Aspecto | Detalle |
|---------|---------|
| Rol | Parte del sistema MSI-a (no tercero si es self-hosted) |
| Ubicación | Servidor propio (Docker) |

**Nota**: Si Qdrant está desplegado como parte del stack Docker de MSI-a, forma parte del sistema propio y no es un encargado externo. Si se usara Qdrant Cloud, sería encargado.

---

## 5. Cadena de encargados y subencargados

```
MSI Automotive S.L. (RESPONSABLE)
    │
    ├── Zanovix (ENCARGADO) — Desarrollo y mantenimiento
    │
    ├── Chatwoot (ENCARGADO) — Mensajería WhatsApp
    │       [Verificar si tiene subencargados propios]
    │
    ├── OpenRouter (ENCARGADO)
    │       └── DeepSeek (SUBENCARGADO) — Procesamiento LLM
    │
    └── [Proveedor hosting] (ENCARGADO) — Infraestructura
```

---

## 6. Obligaciones por rol

### Responsable (MSI Automotive)
- [ ] Informar a los interesados (Arts. 13-14 RGPD)
- [ ] Gestionar el ejercicio de derechos
- [ ] Realizar EIPD si procede (Art. 35 RGPD)
- [ ] Notificar brechas a la AEPD (Art. 33 RGPD)
- [ ] Mantener el RAT (Art. 30 RGPD)
- [ ] Firmar contratos Art. 28 con todos los encargados
- [ ] Garantizar cumplimiento de medidas de seguridad

### Encargado (Zanovix)
- [ ] Tratar datos solo según instrucciones documentadas
- [ ] Garantizar confidencialidad del personal
- [ ] Implementar medidas de seguridad (Art. 32 RGPD)
- [ ] No subencargar sin autorización
- [ ] Asistir al responsable en ejercicio de derechos
- [ ] Notificar breches al responsable sin dilución
- [ ] Devolver/destruir datos al finalizar

---

## 7. Contratos necesarios

| Encargado | Tipo de contrato | Estado |
|-----------|------------------|--------|
| Zanovix | Contrato Art. 28 RGPD | Borrador preparado |
| Chatwoot | DPA / Terms of Service | Verificar |
| OpenRouter | Términos de servicio + SCCs | Verificar |
| Proveedor hosting | DPA / Contrato Art. 28 | Verificar |

---

## 8. Resumen de determinación

| Entidad | Rol | Relación con MSI Automotive |
|---------|-----|----------------------------|
| MSI Automotive S.L. | Responsable del tratamiento | — |
| Zanovix | Encargado del tratamiento | Contrato Art. 28 |
| Chatwoot | Encargado del tratamiento | DPA / ToS |
| OpenRouter | Encargado del tratamiento | ToS + SCCs |
| DeepSeek | Subencargado (de OpenRouter) | Via OpenRouter |
| [Hosting] | Encargado del tratamiento | DPA |
| WhatsApp/Meta | Responsable independiente | Sin relación RGPD |

---

## Checklist de aprobación

- [ ] Análisis revisado por MSI Automotive
- [ ] Verificada ubicación de cada servicio
- [ ] Verificados términos de servicio de Chatwoot, OpenRouter
- [ ] Validado por abogado RGPD ⚠️
- [ ] Contratos Art. 28 en proceso con todos los encargados

---

**Notas del abogado**:
> [Espacio para observaciones del abogado RGPD]

**Fecha de validación**: _______________
