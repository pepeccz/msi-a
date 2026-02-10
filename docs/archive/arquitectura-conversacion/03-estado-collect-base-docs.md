# Arquitectura de Conversación - Estado: COLLECT_BASE_DOCS

## 📋 Metadatos del Estado

| Campo | Valor |
|-------|-------|
| **Nombre del Estado** | Recolección de Documentación Base |
| **Código del Estado** | `collect_base_docs` |
| **Versión** | 1.0 |
| **Fecha de Creación** | Febrero 2026 |
| **Última Modificación** | Febrero 2026 |
| **Responsable** | Equipo de Conversación |
| **Estado de Implementación** | En producción |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
Recopilar la documentación base del vehículo que es requisito legal para cualquier homologación: ficha técnica, permiso de circulación y vistas generales del vehículo.

### Objetivos Secundarios
- Validar que la documentación es del vehículo correcto
- Asegurar que todos los documentos obligatorios estén presentes
- Preparar la transición hacia la recolección de datos personales

### Definición del Éxito
El estado se considera completado cuando el usuario confirma haber enviado toda la documentación base requerida para la categoría específica del vehículo.

---

## 🔄 Contexto de Navegación

### Estados Predecesores

| Estado Origen | Activador de Transición | Condiciones |
|---------------|------------------------|-------------|
| COLLECT_ELEMENT_DATA | `completar_elemento_actual()` | Último elemento completado |

### Estados Sucesores

| Estado Destino | Activador de Transición | Condiciones |
|----------------|------------------------|-------------|
| COLLECT_PERSONAL | `confirmar_documentacion_base()` | Usuario confirma documentación enviada |

---

## 🛠️ Capacidades del Agente

### Herramientas Disponibles

#### Herramientas de Consulta

| Herramienta | Propósito | Datos Requeridos | Datos Producidos |
|-------------|-----------|------------------|------------------|
| `enviar_imagenes_ejemplo` (tipo="documentacion_base") | Mostrar ejemplos de documentación base | Categoría del vehículo | Lista de imágenes de ejemplo |

#### Herramientas de Acción

| Herramienta | Propósito | Efecto en el Estado | Efecto en el Sistema |
|-------------|-----------|---------------------|---------------------|
| `confirmar_documentacion_base` | Confirmar recepción de documentación base | Marca `base_docs_received=true`, transiciona a COLLECT_PERSONAL | Actualiza estado del caso en base de datos |

### Documentación Requerida por Categoría

| Categoría | Documentos Base | Variaciones |
|-----------|----------------|-------------|
| Motos | Ficha técnica, Permiso de circulación, Vistas del vehículo | Estándar |
| Autocaravanas | Ficha técnica, Permiso de circulación, Vistas, Documentación ITV | Más extensivo |
| Coches | Ficha técnica, Permiso de circulación, Vistas | Estándar |

---

## 📜 Reglas de Negocio

### Reglas de Ejecución

1. **Documentación Completa Requerida**
   - **Descripción**: El usuario debe enviar TODOS los documentos base listados para su categoría
   - **Prioridad**: Crítica
   - **Consecuencia**: No puede avanzar sin confirmación

2. **Ejemplos Opcionales**
   - **Descripción**: Las imágenes de ejemplo son opcionales (solo si el usuario las solicita)
   - **Prioridad**: Media
   - **Consecuencia**: Envío innecesario si el usuario ya conoce los requisitos

### Reglas de Salida

1. **Confirmación Explícita Requerida**
   - **Condición**: Usuario debe indicar explícitamente "listo" o equivalente
   - **Validación**: Verificación de que todos los documentos base están presentes
   - **Rollback**: No permitido (no se puede volver a este estado desde estados posteriores)

---

## 🎭 Casos de Uso

### Caso Principal: Documentación Completa

**Flujo**:
1. Agente: "¡Perfecto! Ya tengo toda la información de los elementos.
            Ahora necesito la documentación base del vehículo:
            • Ficha técnica
            • Permiso de circulación  
            • Vistas del vehículo (frontal, laterales, trasera)
            Puedes enviar fotos o PDF. Cuando termines, escribe 'listo'."
2. Usuario: [Envía documentos]
3. Usuario: "Listo"
4. Agente: [Llama `confirmar_documentacion_base`]
5. Agente: Transiciona a COLLECT_PERSONAL

### Caso Alternativo: Usuario Solicita Ejemplos

**Flujo**:
1. Agente: "Necesito la documentación base..."
2. Usuario: "¿Puedes mostrarme ejemplos?"
3. Agente: [Llama `enviar_imagenes_ejemplo` tipo="documentacion_base"]
4. Agente: [Muestra ejemplos de ficha técnica, permiso, vistas]
5. Usuario: [Envía documentos] + "Listo"
6. [Continúa flujo normal]

---

## 💬 Interacción Típica

```
Agente: ¡Perfecto! Ya tenemos toda la información de los elementos.

       Ahora necesito la documentación base del vehículo:
       • Ficha técnica del vehículo
       • Permiso de circulación
       • Vistas del vehículo (frontal, laterales, trasera)

       Puedes enviar fotos o PDF de estos documentos.
       Cuando hayas enviado todo, escribe "listo".

Usuario: [Envía PDF de ficha técnica]
Usuario: [Envía foto del permiso]
Usuario: [Envía 3 fotos del vehículo]
Usuario: Listo

Agente: [Confirma documentación]

       ¡Gracias! Ahora pasamos a tus datos personales...
       [Transiciona a COLLECT_PERSONAL]
```

---

## ⚠️ Consideraciones

### Decisiones de Diseño

1. **Confirmación Manual vs Automática**
   - **Decisión**: El usuario debe decir "listo" explícitamente
   - **Justificación**: Evita corte prematuro si el usuario está subiendo documentos lentamente
   - **Consecuencia**: Menor riesgo de documentación incompleta

2. **No Validación OCR**
   - **Decisión**: No se valida contenido de documentos en este estado
   - **Justificación**: Complejidad técnica, se deja para revisión humana
   - **Consecuencia**: Depende del usuario enviar documentos correctos

### Limitaciones

- No se valida que los documentos correspondan al vehículo declarado
- No se detecta automáticamente si faltan documentos
- No se puede solicitar documentos específicos faltantes individualmente

---

## 📚 Referencias

- **Anterior**: [02-estado-collect-element-data.md](02-estado-collect-element-data.md)
- **Siguiente**: [04-estado-collect-personal.md](04-estado-collect-personal.md)
- **Transiciones**: [08-transiciones-fsm.md](08-transiciones-fsm.md)

---

**Nota**: Estado relativamente simple pero crítico para el cumplimiento legal de la homologación.
