# Borrador: Aviso de Primera Interacción RGPD

> **Documento**: Borrador para revisión de MSI Automotive y validación de abogado RGPD
> **Redactado por**: Zanovix (agencia de desarrollo)
> **Fecha**: 2026-02-19
> **Estado**: BORRADOR — Pendiente de aprobación

---

## Contexto

Este es el mensaje que el agente de IA de MSI-a enviará automáticamente en la PRIMERA interacción de cada usuario por WhatsApp. Cumple con el deber de información del Art. 13 RGPD y el Art. 50 del AI Act (identificación como sistema de IA).

**Requisitos**:
- Breve (formato WhatsApp)
- Incluye información esencial RGPD
- Enlace a política completa
- Identificación como IA

---

## Propuesta de texto

### Opción A: Texto completo en primer mensaje

```
👋 ¡Hola! Soy el asistente virtual de MSI Automotive.

Antes de continuar, información importante:

📍 Responsable: MSI Automotive S.L.
📋 Finalidad: Gestionar tu consulta, presupuesto o expediente de homologación.
🤖 Soy un sistema de inteligencia artificial.

Tus derechos: Puedes ejercer tus derechos de acceso, rectificación, supresión y otros escribiendo a privacidad@msiautomotive.es

Más información: msiautomotive.es/privacidad

---

¿En qué puedo ayudarte?
```

**Longitud**: ~380 caracteres (apto para WhatsApp)

---

### Opción B: Texto breve + enlace

```
👋 ¡Hola! Soy el asistente virtual de MSI Automotive.

🤖 Soy un sistema de IA que te ayudará con tu consulta de homologación.

Antes de continuar, te informo de que tus datos serán tratados según nuestra política de privacidad: msiautomotive.es/privacidad

Para ejercer tus derechos ARCO+: privacidad@msiautomotive.es

---

¿En qué puedo ayudarte?
```

**Longitud**: ~320 caracteres (apto para WhatsApp)

---

### Opción C: Mínimo legal (más corto)

```
👋 Soy el asistente IA de MSI Automotive.

Te ayudo con presupuestos y expedientes de homologación.

ℹ️ Política de privacidad: msiautomotive.es/privacidad
✉️ Derechos ARCO+: privacidad@msiautomotive.es

¿En qué puedo ayudarte?
```

**Longitud**: ~220 caracteres

---

## Recomendación de Zanovix

Recomendamos la **Opción A** por las siguientes razones:

1. **Incluye todos los elementos exigidos por Art. 13 RGPD**:
   - Identidad del responsable (MSI Automotive S.L.)
   - Finalidad del tratamiento
   - Derechos del interesado
   - Cómo ejercerlos

2. **Cumple Art. 50 AI Act**:
   - Identificación clara como sistema de IA

3. **Transparencia proactiva**:
   - El usuario sabe desde el principio con quién habla y qué pasa con sus datos

4. **Longitud razonable**:
   - 380 caracteres es aceptable para un mensaje único de bienvenida

---

## Campos que MSI Automotive debe completar

| Campo | Valor pendiente |
|-------|-----------------|
| Email privacidad | `privacidad@msiautomotive.es` → Confirmar o cambiar |
| URL política privacidad | `msiautomotive.es/privacidad` → Confirmar o crear |
| Razón social completa | `MSI Automotive S.L.` → Confirmar |
| Dirección (si se quiere incluir) | Pendiente |
| DPO (si existe) | Pendiente |

---

## Implementación técnica

Una vez aprobado el texto:

1. Se configura en `shared/config.py` como `PRIVACY_NOTICE_TEXT`
2. Se implementa en el agente (P0-02 del plan)
3. Se envía UNA sola vez por usuario (flag `privacy_notice_sent_at` en DB)
4. Se envía ANTES de la respuesta del agente

---

## Checklist de aprobación

- [ ] Texto revisado por MSI Automotive
- [ ] Campos pendientes completados
- [ ] Email de privacidad operativo
- [ ] URL de política de privacidad operativa
- [ ] Validado por abogado RGPD
- [ ] Aprobado para implementación

---

**Notas del abogado**:
> [Espacio para observaciones del abogado RGPD]

**Fecha de aprobación**: _______________

**Firma responsable MSI Automotive**: _______________
