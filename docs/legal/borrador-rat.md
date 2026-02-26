# Borrador: Registro de Actividades de Tratamiento (RAT)

> **Documento**: Art. 30 RGPD — Registro de Actividades de Tratamiento
> **Redactado por**: Zanovix (agencia de desarrollo)
> **Fecha**: 2026-02-19
> **Estado**: BORRADOR — Pendiente de completar por MSI Automotive

---

## Registro de Actividades de Tratamiento

**Responsable del tratamiento**:

| Campo | Valor |
|-------|-------|
| Razón social | MSI Automotive S.L. |
| CIF | [Completar] |
| Dirección | [Completar] |
| Email contacto | [Completar] |
| Delegado de Protección de Datos (DPO) | [Si aplica, completar] |

---

## Actividad 1: Atención al cliente por WhatsApp con IA agéntica (MSI-a)

### Descripción general

Sistema de atención al cliente automatizado mediante inteligencia artificial agéntica que gestiona consultas, elaboración de presupuestos orientativos y recopilación de datos para expedientes de homologación de vehículos.

### Fines del tratamiento

- Responder consultas sobre servicios de homologación
- Elaborar presupuestos orientativos de servicios
- Recopilar datos necesarios para expedientes de homologación
- Gestionar la comunicación con clientes y potenciales clientes

### Base jurídica

| Finalidad | Base legitimadora | Art. RGPD |
|-----------|-------------------|-----------|
| Gestión de consultas | Interés legítimo | Art. 6.1.f |
| Elaboración de presupuestos | Medidas precontractuales | Art. 6.1.b |
| Gestión de expedientes | Ejecución de contrato | Art. 6.1.b |
| Atención mediante IA | Ejecución de contrato | Art. 6.1.b |

### Categorías de interesados

- Clientes actuales de MSI Automotive
- Potenciales clientes que contactan por WhatsApp
- Personas que solicitan presupuestos
- Personas que inician expedientes de homologación

### Categorías de datos personales

| Categoría | Datos concretos | Origen |
|-----------|-----------------|--------|
| Identificativos | Nombre, apellidos, teléfono, email, NIF/CIF | Interesado |
| Contacto | Dirección postal, localidad, provincia, CP | Interesado |
| Vehículo | Marca, modelo, matrícula, bastidor, año | Interesado |
| Comunicación | Contenido conversaciones WhatsApp, historial | Generado en interacción |
| Técnicos | IP, dispositivo, hora de conexión | Automático |

### Destinatarios o categorías de destinatarios

| Destinatario | Categoría | Finalidad | Ubicación | Garantías |
|--------------|-----------|-----------|-----------|-----------|
| Zanovix | Encargado | Desarrollo/mantenimiento sistema | [Completar] | Contrato Art. 28 |
| Chatwoot | Encargado | Plataforma mensajería | [Completar] | DPA/ToS |
| OpenRouter | Encargado | Procesamiento LLM | EE.UU. | SCCs |
| DeepSeek | Subencargado | Procesamiento LLM | China | SCCs + TIA |
| [Hosting] | Encargado | Infraestructura | [Completar] | DPA |

### Transferencias internacionales a terceros países

| Destinatario | País | Garantías aplicadas |
|--------------|------|---------------------|
| OpenRouter | EE.UU. | SCCs (Decisión de Ejecución UE 2021/914) |
| DeepSeek | China | SCCs + TIA + medidas suplementarias (anonimización) |

### Plazos de supresión

| Tipo de dato | Plazo de conservación | Criterio |
|--------------|----------------------|----------|
| Datos de usuario | Hasta solicitud de supresión o fin relación | Necesidad de gestión |
| Mensajes conversación | 180 días desde última interacción | Interés legítimo |
| Presupuestos | Relación comercial + 3 años | Obligaciones fiscales |
| Expedientes | Tramitación + 6 años | Obligaciones legales |
| Métricas LLM | 90 días | Interés legítimo |
| Tool logs | 90 días | Interés legítimo |
| Logs acceso admin | 365 días | Seguridad |

### Medidas de seguridad técnicas y organizativas

**Técnicas**:
- Cifrado TLS en comunicaciones
- Cifrado de datos sensibles en reposo
- Autenticación JWT + RBAC
- Sistema de detección de intrusiones
- Validación multi-capa de archivos
- Copias de seguridad cifradas
- Sandbox Docker para aislamiento de servicios

**Organizativas**:
- Política de seguridad de la información
- Formación en protección de datos
- Control de acceso físico
- Procedimiento de gestión de incidencias
- Contratos Art. 28 con encargados

### Sistema de IA agéntica: información adicional

| Aspecto | Descripción |
|---------|-------------|
| Tipo de IA | Sistema agéntico conversacional basado en LLM |
| Decisiones automatizadas | No produce efectos jurídicos (presupuestos orientativos) |
| Supervisión humana | Escalado a humano disponible bajo demanda |
| Transparencia | Usuario informado de que habla con IA |
| Derecho a no ser perfilado | N/A (no se realiza perfilado) |

---

## Actividad 2: [Si existe otra actividad, añadir aquí]

*Ejemplo: Gestión de la página web, Marketing, etc.*

---

## Documentación de referencia

| Documento | Ubicación |
|-----------|-----------|
| Política de privacidad | docs/legal/borrador-politica-privacidad.md |
| Contrato encargado Zanovix | docs/legal/borrador-contrato-encargado-zanovix.md |
| Determinación de roles | docs/legal/borrador-roles-tratamiento.md |
| EIPD | docs/legal/borrador-eipd.md |
| TIA OpenRouter | docs/legal/borrador-tia-openrouter.md |

---

## Campos que MSI Automotive debe completar

- [ ] CIF completo
- [ ] Dirección fiscal
- [ ] Email contacto general
- [ ] DPO (si existe)
- [ ] Ubicación servidor hosting
- [ ] Nombre proveedor hosting
- [ ] Ubicación instancia Chatwoot (cloud/local)
- [ ] Otras actividades de tratamiento si las hay

---

## Validación

| Revisión | Fecha | Firmado |
|----------|-------|---------|
| Redacción técnica (Zanovix) | 2026-02-19 | _____________ |
| Revisión MSI Automotive | | _____________ |
| Validación abogado RGPD | | _____________ |

---

**Fecha última actualización del registro**: 2026-02-19

**Próxima revisión programada**: 2027-02-19 (anual)
