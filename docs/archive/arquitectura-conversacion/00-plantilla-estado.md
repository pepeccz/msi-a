# Arquitectura de Conversación - Estado: [NOMBRE_DEL_ESTADO]

## 📋 Metadatos del Estado

| Campo | Valor |
|-------|-------|
| **Nombre del Estado** | [Nombre identificador único] |
| **Código del Estado** | [Identificador técnico] |
| **Versión** | [Versión de esta definición] |
| **Fecha de Creación** | [DD/MM/AAAA] |
| **Última Modificación** | [DD/MM/AAAA] |
| **Responsable** | [Área/Equipo responsable] |
| **Estado de Implementación** | [En diseño / En desarrollo / En producción / Obsoleto] |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
[Descripción clara y concisa de qué debe lograr este estado. Una sola oración que capture la esencia.]

### Objetivos Secundarios
- [Objetivo adicional 1]
- [Objetivo adicional 2]
- [Objetivo adicional 3]

### Definición del Éxito
[¿Cómo se sabe que este estado ha cumplido su propósito? ¿Qué condición indica que se puede transicionar al siguiente estado?]

---

## 🔄 Contexto de Navegación

### Estados Predecesores
[Estados desde los cuales puede llegarse a este estado]

| Estado Origen | Activador de Transición | Condiciones |
|---------------|------------------------|-------------|
| [Estado A] | [Evento/acción que dispara] | [Condiciones que deben cumplirse] |
| [Estado B] | [Evento/acción que dispara] | [Condiciones que deben cumplirse] |

### Estados Sucesores
[Estados a los cuales puede transicionarse desde este estado]

| Estado Destino | Activador de Transición | Condiciones |
|----------------|------------------------|-------------|
| [Estado X] | [Evento/acción que dispara] | [Condiciones que deben cumplirse] |
| [Estado Y] | [Evento/acción que dispara] | [Condiciones que deben cumplirse] |

---

## 🎬 Activadores de Entrada

### Eventos que Inician este Estado
1. **[Nombre del Evento 1]**
   - **Descripción**: [Qué sucede]
   - **Origen**: [Usuario / Sistema / Evento externo]
   - **Datos asociados**: [Qué información acompaña al evento]

2. **[Nombre del Evento 2]**
   - **Descripción**: [Qué sucede]
   - **Origen**: [Usuario / Sistema / Evento externo]
   - **Datos asociados**: [Qué información acompaña al evento]

### Condiciones de Entrada
[Requisitos que deben cumplirse para poder entrar a este estado]

- [Condición 1]
- [Condición 2]
- [Condición 3]

---

## 🛠️ Capacidades del Agente

### Herramientas Disponibles
[Listado de acciones que el agente puede ejecutar estando en este estado]

#### Herramientas de Consulta
| Herramienta | Propósito | Datos Requeridos | Datos Producidos |
|-------------|-----------|------------------|------------------|
| [Nombre] | [Para qué sirve] | [Qué necesita] | [Qué devuelve] |

#### Herramientas de Acción
| Herramienta | Propósito | Efecto en el Estado | Efecto en el Sistema |
|-------------|-----------|---------------------|---------------------|
| [Nombre] | [Para qué sirve] | [Cambia algo del estado actual] | [Persiste/afecta algo externo] |

#### Herramientas de Transición
| Herramienta | Propósito | Estado Resultante | Condiciones |
|-------------|-----------|-------------------|-------------|
| [Nombre] | [Para qué sirve] | [A dónde lleva] | [Cuándo puede usarse] |

### Herramientas Restringidas
[Herramientas que NO están disponibles en este estado y por qué]

| Herramienta | Razón de Restricción | Alternativa Disponible |
|-------------|---------------------|------------------------|
| [Nombre] | [Por qué no se puede usar] | [Qué usar en su lugar] |

---

## 📊 Datos del Estado

### Datos de Entrada
[Información que debe estar disponible al entrar a este estado]

| Dato | Tipo | Obligatorio | Fuente | Descripción |
|------|------|-------------|--------|-------------|
| [Nombre] | [Tipo conceptual] | [Sí/No] | [De dónde viene] | [Para qué se usa] |

### Datos de Salida
[Información que debe producirse al completar este estado]

| Dato | Tipo | Obligatorio | Destino | Descripción |
|------|------|-------------|---------|-------------|
| [Nombre] | [Tipo conceptual] | [Sí/No] | [Adónde va] | [Qué representa] |

### Datos Temporales
[Información que se maneja solo durante este estado, no persiste]

| Dato | Tipo | Duración | Descripción |
|------|------|----------|-------------|
| [Nombre] | [Tipo conceptual] | [Durante este estado / Hasta transición] | [Qué representa] |

### Estado Interno
[Variables de estado que afectan el comportamiento dentro de este estado]

| Variable | Valores Posibles | Significado | Transiciones Internas |
|----------|-------------------|-------------|----------------------|
| [Nombre] | [Valor1, Valor2...] | [Qué significa cada valor] | [Cambia comportamiento cómo] |

---

## 📜 Reglas de Negocio

### Reglas de Entrada
[Condiciones que deben verificarse al entrar]

1. **[Nombre de la Regla]**
   - **Condición**: [Qué debe cumplirse]
   - **Acción si falla**: [Qué hacer si no se cumple]
   - **Mensaje al usuario**: [Qué comunicar]

### Reglas de Ejecución
[Restricciones sobre cómo debe comportarse el agente]

1. **[Nombre de la Regla]**
   - **Descripción**: [Qué restricción aplica]
   - **Prioridad**: [Alta/Media/Baja]
   - **Consecuencia de incumplimiento**: [Qué sucede si se viola]

### Reglas de Salida
[Condiciones que deben cumplirse para poder salir]

1. **[Nombre de la Regla]**
   - **Condición de completitud**: [Qué debe estar listo]
   - **Validación requerida**: [Qué verificaciones hacer]
   - **Rollback posible**: [Si se puede deshacer o no]

---

## 🎭 Casos de Uso

### Caso de Uso Principal
**Nombre**: [Nombre descriptivo]

**Descripción**: [Breve descripción del flujo principal]

**Actores**: [Quién participa]

**Precondiciones**: [Qué debe ser cierto antes de empezar]

**Flujo Normal**:
1. [Paso 1]
2. [Paso 2]
3. [Paso 3]

**Flujos Alternativos**:
- **A1**: [Descripción de alternativa] → [Resultado]
- **A2**: [Descripción de alternativa] → [Resultado]

**Excepciones**:
- **E1**: [Condición de error] → [Manejo]
- **E2**: [Condición de error] → [Manejo]

**Postcondiciones**: [Qué debe ser cierto al finalizar]

### Casos de Uso Adicionales
[Listado de otros escenarios soportados]

| ID | Nombre | Descripción | Complejidad |
|----|--------|-------------|-------------|
| CU-02 | [Nombre] | [Descripción] | [Alta/Media/Baja] |
| CU-03 | [Nombre] | [Descripción] | [Alta/Media/Baja] |

---

## 💬 Interacciones Típicas

### Escenario 1: [Nombre descriptivo]
```
Usuario: [Mensaje del usuario]
Agente: [Respuesta del agente]
Usuario: [Mensaje del usuario]
Agente: [Respuesta del agente]
[...]
```
**Resultado**: [Qué se logra]

### Escenario 2: [Nombre descriptivo]
```
Usuario: [Mensaje del usuario]
Agente: [Respuesta del agente]
[...]
```
**Resultado**: [Qué se logra]

### Escenario 3: Manejo de Error
```
Usuario: [Mensaje del usuario]
Agente: [Respuesta del agente - detecta problema]
Usuario: [Intento de corrección]
Agente: [Validación y continuación]
```
**Resultado**: [Cómo se recupera]

---

## ⚠️ Consideraciones de Diseño

### Decisiones Arquitectónicas
[Decisiones clave que afectan este estado]

1. **[Decisión]**
   - **Contexto**: [Por qué se tuvo que decidir]
   - **Opciones consideradas**: [Alternativas]
   - **Decisión tomada**: [Qué se eligió]
   - **Justificación**: [Por qué]
   - **Consecuencias**: [Implicaciones]

### Limitaciones y Restricciones
[Cosas que este estado NO puede hacer o NO hace]

- [Limitación 1]
- [Limitación 2]
- [Limitación 3]

### Supuestos
[Cosas que se dan por sentado]

- [Supuesto 1]
- [Supuesto 2]
- [Supuesto 3]

---

## 🔗 Dependencias

### Dependencias de Entrada
[Qué necesita este estado de otros componentes/estados]

| Dependencia | Tipo | Descripción | Crítica |
|-------------|------|-------------|---------|
| [Estado/Sistema X] | [Estado previo / Datos / Servicio] | [Qué se necesita] | [Sí/No] |

### Dependencias de Salida
[Qué produce este estado que otros necesitan]

| Dependencia | Tipo | Descripción | Consumidor |
|-------------|------|-------------|------------|
| [Dato/Resultado Y] | [Estado siguiente / Datos / Evento] | [Qué se produce] | [Quién lo usa] |

### Acoplamiento
[Nivel de dependencia con otros estados]

- **Acoplamiento de entrada**: [Alto/Medio/Bajo] - [Justificación]
- **Acoplamiento de salida**: [Alto/Medio/Bajo] - [Justificación]
- **Acoplamiento temporal**: [Alto/Medio/Bajo] - [Justificación]

---

## 📈 Métricas y Monitoreo

### Indicadores de Éxito
[Cómo medir que este estado funciona bien]

| Métrica | Definición | Objetivo | Frecuencia |
|---------|------------|----------|------------|
| [Nombre] | [Cómo se calcula] | [Valor objetivo] | [Medición] |

### Indicadores de Problemas
[Señales de alerta]

| Señal | Descripción | Umbral | Acción |
|-------|-------------|--------|--------|
| [Nombre] | [Qué indica] | [Cuándo preocuparse] | [Qué hacer] |

---

## 📝 Glosario

|Término | Definición |
|--------|------------|
| [Término 1] | [Significado en este contexto] |
| [Término 2] | [Significado en este contexto] |

---

## 📚 Referencias

### Documentación Relacionada
- [Enlace a documento relacionado 1]
- [Enlace a documento relacionado 2]

### Decisiones de Arquitectura
- [ADR relacionado con este estado]

### Historial de Cambios
| Versión | Fecha | Autor | Cambios |
|---------|-------|-------|---------|
| 1.0 | [Fecha] | [Autor] | Creación inicial |
| 1.1 | [Fecha] | [Autor] | [Descripción del cambio] |

---

## 🤔 Preguntas Abiertas

[Preguntas que aún no tienen respuesta y que pueden afectar este estado]

1. [Pregunta 1]
2. [Pregunta 2]

---

**Nota**: Esta es una definición arquitectónica. La implementación técnica debe alinearse con estas especificaciones pero puede incluir detalles adicionales propios de la tecnología utilizada.
