# Borrador: Contrato de Encargado del Tratamiento (Zanovix)

> **Documento**: Borrador para revisión legal y firma
> **Redactado por**: Zanovix (agencia de desarrollo y encargado propuesto)
> **Fecha**: 2026-02-19
> **Estado**: BORRADOR — Pendiente de validación por abogado RGPD

---

## CONTRATO DE ENCARGADO DEL TRATAMIENTO

En [CIUDAD], a [DÍA] de [MES] de 2026

### REUNIDOS

**De una parte**, MSI Automotive S.L., con CIF [CIF], con domicilio social en [DIRECCIÓN], en adelante **EL RESPONSABLE**.

**De otra parte**, [ZANOVIX / RAZÓN SOCIAL COMPLETA DE LA AGENCIA], con CIF [CIF], con domicilio social en [DIRECCIÓN], representada en este acto por [NOMBRE] en su condición de [CARGO], en adelante **EL ENCARGADO**.

Ambas partes se reconocen mutuamente la capacidad legal suficiente para suscribir el presente contrato y, a tal efecto,

### EXPONEN

**I.** EL RESPONSABLE es responsable del tratamiento de datos personales en el marco de su actividad de homologación de vehículos.

**II.** EL RESPONSABLE utiliza un sistema de IA agéntica denominado "MSI-a" para la atención al cliente a través de WhatsApp.

**III.** EL ENCARGADO es una empresa especializada en desarrollo de software y sistemas de inteligencia artificial.

**IV.** EL RESPONSABLE necesita los servicios de EL ENCARGADO para el desarrollo, mantenimiento y operación del sistema MSI-a.

**V.** En virtud de dichos servicios, EL ENCARGADO tendrá acceso a datos personales tratados por EL RESPONSABLE, por lo que es necesario formalizar la relación jurídica entre ambas partes de conformidad con el artículo 28 del Reglamento (UE) 2016/679 (RGPD).

**VI.** Por todo lo expuesto, ambas partes acuerdan suscribir el presente CONTRATO DE ENCARGADO DEL TRATAMIENTO, que se regirá por las siguientes:

### ESTIPULACIONES

#### PRIMERA. Objeto del contrato

El presente contrato tiene por objeto regular las condiciones en las que EL ENCARGADO tratará los datos personales a los que tenga acceso con motivo de la prestación de los servicios de desarrollo, mantenimiento y operación del sistema MSI-a, de conformidad con las instrucciones de EL RESPONSABLE.

#### SEGUNDA. Duración

El presente contrato entrará en vigor en la fecha de su firma y tendrá vigencia durante todo el período en que EL ENCARGADO preste servicios a EL RESPONSABLE y tenga acceso a datos personales.

En caso de extinción del contrato, EL ENCARGADO devolverá o destruirá los datos personales conforme a la estipulación octava.

#### TERCERA. Naturaleza, duración y finalidad del tratamiento

| Aspecto | Descripción |
|---------|-------------|
| **Naturaleza del tratamiento** | Almacenamiento, acceso, consulta, modificación y, en su caso, supresión de datos personales contenidos en las bases de datos del sistema MSI-a |
| **Duración del tratamiento** | Durante toda la vigencia del presente contrato |
| **Finalidad del tratamiento** | Desarrollo, mantenimiento, operación, soporte técnico y mejora del sistema MSI-a de atención al cliente por WhatsApp |

#### CUARTA. Tipología de datos personales

EL ENCARGADO tendrá acceso a las siguientes categorías de datos personales:

| Categoría | Datos específicos |
|-----------|-------------------|
| Datos identificativos | Nombre, apellidos, teléfono, email, NIF/CIF |
| Datos de contacto | Dirección postal, localidad, provincia, código postal |
| Datos de vehículo | Marca, modelo, matrícula, bastidor, año |
| Datos de comunicación | Contenido de conversaciones por WhatsApp, historial de interacciones |
| Datos técnicos | Direcciones IP, logs de acceso, métricas de uso |

#### QUINTA. Categoría de interesados

Los datos personales pertenecen a:

- Clientes y potenciales clientes de EL RESPONSABLE
- Personas que contactan vía WhatsApp para consultas de homologación
- Personas que solicitan presupuestos de servicios
- Personas que inician expedientes de homologación

#### SEXTA. Obligaciones del Encargado

EL ENCARGADO se compromete a:

**6.1** Tratar los datos personales únicamente siguiendo las instrucciones documentadas de EL RESPONSABLE, salvo que esté obligado a actuar de otra manera por la normativa aplicable.

**6.2** Garantizar que las personas autorizadas para tratar los datos personales:
- Se han comprometido a respetar la confidencialidad
- Conocen y cumplen las medidas de seguridad aplicables
- Solo acceden a los datos estrictamente necesarios para sus funciones

**6.3** Implementar y mantener las medidas técnicas y organizativas apropiadas para proteger los datos personales, incluyendo:

| Medida | Descripción |
|--------|-------------|
| Cifrado | Cifrado TLS en comunicaciones, cifrado de datos sensibles en reposo |
| Control de acceso | Autenticación mediante JWT, autorización basada en roles (RBAC) |
| Registro de actividad | Logs de acceso y operaciones sobre datos personales |
| Protección perimetral | Firewalls, segmentación de red, sandboxing Docker |
| Copias de seguridad | Backups cifrados y segregados |
| Formación | Personal formado en protección de datos y seguridad |

**6.4** No subencargar el tratamiento a terceros sin autorización previa, específica o general, por escrito de EL RESPONSABLE. En caso de autorización general, EL ENCARGADO mantendrá informado a EL RESPONSABLE de cualquier cambio en los subencargados.

**Subencargados actualmente autorizados**:
- OpenRouter LLC (procesamiento LLM cloud)
- [Proveedor hosting/servidores]

**6.5** Asistir a EL RESPONSABLE, teniendo en cuenta la naturaleza del tratamiento, en el cumplimiento de sus obligaciones respecto a:
- Seguridad de los datos (Art. 32 RGPD)
- Notificación de violaciones de seguridad (Art. 33-34 RGPD)
- Evaluaciones de impacto (Art. 35 RGPD)
- Consulta previa (Art. 36 RGPD)

**6.6** A petición de EL RESPONSABLE, facilitar información que permita demostrar el cumplimiento de las obligaciones establecidas en el artículo 28 del RGPD.

**6.7** Permitir y contribuir a las auditorías o inspecciones realizadas por EL RESPONSABLE o por otro auditor autorizado.

#### SÉPTIMA. Obligaciones del Responsable

EL RESPONSABLE se compromete a:

**7.1** Proporcionar a EL ENCARGADO las instrucciones documentadas sobre el tratamiento de datos personales.

**7.2** Garantizar que ha cumplido y cumple con todas las obligaciones de información a los interesados establecidas en los artículos 13 y 14 del RGPD.

**7.3** Velar por que el tratamiento realizado por EL ENCARGADO cumple con el RGPD.

**7.4** Informar a EL ENCARGADO de cualquier incidencia que pueda afectar al tratamiento de datos.

#### OCTAVA. Devolución o destrucción de datos

A la terminación de la prestación de servicios, y a elección de EL RESPONSABLE, EL ENCARGADO:

**Opción A**: Devolverá a EL RESPONSABLE todos los datos personales tratados, así como cualquier soporte o documento en que consten, procediendo a la eliminación de cualquier copia en su poder.

**Opción B**: Destruirá todos los datos personales tratados, así como cualquier soporte o documento en que consten, certificando dicha destrucción ante EL RESPONSABLE.

No obstante lo anterior, EL ENCARGADO podrá conservar los datos bloqueados durante el tiempo necesario para atender las posibles responsabilidades derivadas del tratamiento.

#### NOVENA. Violaciones de la seguridad

En caso de que EL ENCARGADO tenga conocimiento de una violación de la seguridad de datos personales:

**9.1** Notificará a EL RESPONSABLE sin dilución indebida y, en cualquier caso, antes de transcurrir 24 horas desde que tuvo conocimiento de la misma.

**9.2** La notificación incluirá:
- Descripción de la naturaleza de la violación
- Categorías y número aproximado de interesados afectados
- Categorías de datos afectados
- Posibles consecuencias
- Medidas adoptadas o propuestas

**9.3** Colaborará con EL RESPONSABLE en la investigación de la incidencia y en la adopción de medidas correctivas.

#### DÉCIMA. Responsabilidad

EL ENCARGADO será responsable del tratamiento y responderá directamente frente a EL RESPONSABLE por los daños y perjuicios causados como consecuencia de:

- Incumplimiento de las instrucciones de EL RESPONSABLE
- Incumplimiento de las obligaciones del RGPD aplicables al encargado
- Acceder a los datos sin autorización o fuera del alcance de su autorización

#### UNDÉCIMA. Derecho aplicable y jurisdicción

El presente contrato se regirá por la legislación española.

Para la resolución de cualquier controversia derivada del presente contrato, las partes se someten a los Juzgados y Tribunales de [CIUDAD], con renuncia expresa a cualquier otro fuero que pudiera corresponderles.

#### DUODÉCIMA. Vigencia del RGPD

El presente contrato se entiende sin perjuicio de las obligaciones adicionales que pudieran derivarse de la legislación española de protección de datos (LOPDGDD) o de cualquier otra norma aplicable.

---

Y en prueba de conformidad con cuanto antecede, las partes firman el presente contrato por duplicado ejemplar en el lugar y fecha indicados en el encabezamiento.

<br>

**EL RESPONSABLE**  
MSI Automotive S.L.  

Fdo.: _________________

<br>

**EL ENCARGADO**  
[ZANOVIX / RAZÓN SOCIAL]

Fdo.: _________________

---

## Campos que las partes deben completar

### MSI Automotive (Responsable):
| Campo | Valor |
|-------|-------|
| Razón social completa | _____________ |
| CIF | _____________ |
| Dirección fiscal | _____________ |
| Ciudad de firma | _____________ |
| Nombre persona firmante | _____________ |
| Cargo | _____________ |

### Zanovix (Encargado):
| Campo | Valor |
|-------|-------|
| Razón social completa | _____________ |
| CIF | _____________ |
| Dirección fiscal | _____________ |
| Nombre persona firmante | _____________ |
| Cargo | _____________ |

---

## Checklist de aprobación

- [ ] Borrador revisado por MSI Automotive
- [ ] Datos completados por ambas partes
- [ ] Validado por abogado RGPD de MSI Automotive ⚠️
- [ ] Aprobado para firma
- [ ] Firmado por ambas partes
- [ ] Copia archivada por ambas partes

---

**Notas del abogado**:
> [Espacio para observaciones del abogado RGPD]

**Fecha de aprobación**: _______________

---

## Referencias

- RGPD Art. 28: Encargado del tratamiento
- RGPD Art. 32: Seguridad del tratamiento
- RGPD Art. 33-34: Notificación de violaciones de seguridad
- LOPDGDD Art. 28: Encargado del tratamiento
- AEPD: Guía sobre encargados y responsables del tratamiento
- AEPD: Modelo de contrato de encargado del tratamiento (disponible en www.aepd.es)
