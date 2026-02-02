# Arquitectura de Conversación - Estado: COLLECT_WORKSHOP

## 📋 Metadatos del Estado

| Campo | Valor |
|-------|-------|
| **Nombre del Estado** | Selección de Taller y Certificado |
| **Código del Estado** | `collect_workshop` |
| **Versión** | 1.0 |
| **Fecha de Creación** | Febrero 2026 |
| **Responsable** | Equipo de Conversación |
| **Estado de Implementación** | En producción |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
Determinar quién proporcionará el certificado del taller requerido para la homologación: MSI (con coste adicional) o un taller propio del cliente (requiere datos del taller).

### Decisión Principal

| Opción | Coste | Acción Requerida |
|--------|-------|------------------|
| MSI proporciona certificado | +85 EUR | Solo confirmar selección |
| Taller propio del cliente | Incluido en presupuesto | Recolectar datos completos del taller |

### Datos del Taller Propio (si aplica)

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `nombre` | Texto | Sí | Nombre del taller |
| `responsable` | Texto | Sí | Persona responsable |
| `domicilio` | Texto | Sí | Dirección del taller |
| `provincia` | Texto | Sí | Provincia |
| `ciudad` | Texto | Sí | Ciudad/Localidad |
| `telefono` | Teléfono | Sí | Teléfono de contacto |
| `registro_industrial` | Texto | Sí | Número de registro industrial |
| `actividad` | Texto | Sí | Descripción de actividad del taller |

---

## 🔄 Contexto de Navegación

### Estados Predecesores

| Estado Origen | Activador | Condiciones |
|---------------|-----------|-------------|
| COLLECT_VEHICLE | Datos de vehículo completos | Todos los campos de vehículo guardados |
| REVIEW_SUMMARY | Edición de sección "taller" | Usuario solicita cambiar decisión de taller |

### Estados Sucesores

| Estado Destino | Activador | Condiciones |
|----------------|-----------|-------------|
| REVIEW_SUMMARY | `actualizar_datos_taller()` | Decisión de taller guardada (MSI o taller propio completo) |

---

## 🛠️ Capacidades

### Herramientas Disponibles

| Herramienta | Propósito | Entrada | Salida |
|-------------|-----------|---------|--------|
| `actualizar_datos_taller` | Guardar decisión de taller | `taller_propio` (booleano) + `datos_taller` (si aplica) | Confirmación + campos faltantes (si aplica) |

---

## 📜 Reglas de Negocio

### Reglas de Negocio Críticas

1. **Comunicación del Coste MSI**
   - **Descripción**: SIEMPRE mencionar +85 EUR si elige MSI
   - **Prioridad**: Crítica
   - **Consecuencia**: Cliente desinformado sobre costes

2. **Datos Completos para Taller Propio**
   - **Descripción**: Si elige taller propio, TODOS los campos son obligatorios
   - **Prioridad**: Crítica
   - **Consecuencia**: Certificado inválido, rechazo de homologación

3. **Decisión Binaria Clara**
   - **Descripción**: Debe ser "MSI" o "Propio", sin medias tintas
   - **Prioridad**: Alta
   - **Consecuencia**: Ambigüedad retrasa el proceso

### Manejo de Respuestas

| Respuesta del Usuario | Interpretación | Acción |
|----------------------|----------------|--------|
| "MSI", "ustedes", "vosotros" | MSI gestiona | `actualizar_datos_taller(taller_propio=False)` |
| "Propio", "mío", "tengo taller" | Taller del cliente | Solicitar todos los datos del taller |
| "No tengo", "no sé" | Ambiguo | Aclarar opciones, mencionar coste MSI |
| "Es obligatorio?" | Consulta | Explicar obligatoriedad, luego decidir |

---

## 🎭 Casos de Uso

### Caso Principal: MSI Gestiona

**Flujo**:
1. Agente: "Ahora necesito saber sobre el certificado del taller.
            
            ¿Quieres que MSI aporte el certificado del taller 
            (coste adicional de 85€), o usarás tu propio taller?"
2. Usuario: "Que lo gestionen ustedes"
3. Agente: [Llama `actualizar_datos_taller(taller_propio=False)`]
4. Agente: "Perfecto, MSI se encargará del certificado (+85€).
            Pasamos al resumen final..."
5. [Transiciona a REVIEW_SUMMARY]

### Caso Principal: Taller Propio

**Flujo**:
1. Agente: [Pregunta sobre taller]
2. Usuario: "Tengo mi propio taller"
3. Agente: "Perfecto, necesito los datos de tu taller:
            • Nombre del taller
            • Responsable
            • Dirección
            • Provincia
            • Ciudad
            • Teléfono
            • Número de Registro Industrial
            • Actividad
            
            Puedes enviarlos todos juntos."
4. Usuario: [Envía todos los datos]
5. Agente: [Llama `actualizar_datos_taller(taller_propio=True, datos_taller={...})`]
6. [Transiciona a REVIEW_SUMMARY]

### Caso de Consulta: Pregunta sobre Obligatoriedad

**Flujo**:
1. Usuario: "¿Es obligatorio el certificado del taller?"
2. Agente: "Sí, es obligatorio para la homologación. 
            Puedes elegir:
            • Que MSI lo gestione (+85€)
            • Usar tu propio taller si tienes uno
            
            ¿Qué prefieres?"
3. [Usuario decide y continúa flujo normal]

---

## 💬 Interacciones Típicas

### Escenario 1: MSI Gestiona

```
Agente: Ahora necesito saber sobre el certificado del taller.

       ¿Quieres que MSI aporte el certificado del taller 
       (coste adicional de 85€), o usarás tu propio taller?

       Responde:
       • "MSI" si quieres que nosotros lo gestionemos (+85€)
       • "Propio" si usarás tu taller y nos proporcionarás sus datos

Usuario: MSI, que lo gestionen ustedes

Agente: [Guarda decisión]

       Perfecto, MSI se encargará del certificado del taller.
       
       ¡Ya casi terminamos! Vamos a revisar todo antes de enviar...
       [Transiciona a REVIEW_SUMMARY]
```

### Escenario 2: Taller Propio

```
Agente: [Pregunta sobre taller]

Usuario: Tengo taller propio

Agente: Perfecto, necesito los datos de tu taller:

       • Nombre del taller
       • Responsable
       • Dirección (calle y número)
       • Provincia
       • Ciudad
       • Teléfono
       • Número de Registro Industrial
       • Actividad del taller

       Puedes enviarlo todo junto.

Usuario: Taller MotoRacing, Juan Pérez, C/ Industria 23, 
       Barcelona, Barcelona, 932345678, 
       Registro B-12345678, Reparación y modificación de motocicletas

Agente: [Guarda datos del taller]

       Perfecto, datos del taller guardados.
       
       ¡Ya casi terminamos! Vamos a revisar todo antes de enviar...
       [Transiciona a REVIEW_SUMMARY]
```

---

## ⚠️ Consideraciones

### Importancia Legal

El certificado del taller es obligatorio por normativa española de homologación:
- Acredita que las modificaciones fueron realizadas por establecimiento autorizado
- Es requisito para la ITV
- Sin él, la homologación no puede completarse

### Coste Transparente

El coste de 85€ por certificado MSI debe comunicarse:
- **Siempre** antes de que el usuario decida
- De forma clara y destacada
- En el contexto de la decisión (no como sorpresa al final)

### Validación del Taller Propio

Los datos del taller propio deben ser válidos:
- Registro industrial debe existir en el sistema
- La actividad debe estar relacionada con el tipo de vehículo
- La dirección debe ser de un taller real (no domicilio particular)

---

## 📚 Referencias

- **Anterior**: [05-estado-collect-vehicle.md](05-estado-collect-vehicle.md)
- **Siguiente**: [07-estado-review-summary.md](07-estado-review-summary.md)
- **Transiciones**: [08-transiciones-fsm.md](08-transiciones-fsm.md)

---

**Nota**: Este estado representa una decisión de negocio importante con implicaciones legales y de coste. La comunicación debe ser clara y completa.
