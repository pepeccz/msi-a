---
titulo: Catálogo de capacidades del sistema
ambito: meta
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Catálogo de capacidades del sistema

## Para qué sirve este archivo

El Arquitecto-AI consulta este catálogo **antes de proponer cualquier comportamiento nuevo** en los specs. Si una funcionalidad requiere capacidades que no están listadas, el Arquitecto no puede prometerla: debe primero pedir autorización para ampliar el catálogo.

El Ingeniero-AI consulta este catálogo para confirmar que lo que le piden implementar encaja con lo que el stack actualmente soporta.

## Qué SÍ podemos hacer hoy

### Canal de comunicación
- ✅ Recibir mensajes por **WhatsApp Business API** (vía Chatwoot como intermediario)
- ✅ Enviar mensajes de texto, imágenes (JPG/PNG), documentos PDF
- ✅ Recibir imágenes y PDFs del cliente, validarlos, guardarlos
- ✅ Ventana de 24h de WhatsApp respetada (Meta platform rule)

### Inteligencia conversacional
- ✅ Clasificación de intenciones con modelo local (Ollama `gemma4:e4b`)
- ✅ Conversación con modelo cloud (OpenRouter `deepseek/deepseek-chat`)
- ✅ Routing híbrido: tier 1 local para tareas simples, tier 2 cloud para razonamiento
- ✅ Fallback automático Cloud → Local si falla la nube
- ✅ State machine conversacional con LangGraph (modos + submodos)
- ✅ Recuperación de sesión vía DraftQuote (el cliente retoma horas después)

### Lógica de negocio
- ✅ Catálogo de categorías de vehículos (PostgreSQL)
- ✅ Catálogo de elementos homologables con variantes
- ✅ Cálculo de tarifas con tiers, inclusiones, servicios adicionales
- ✅ Documentación requerida por elemento (sistema de warnings con asociación dual)
- ✅ RAG sobre documentación oficial (Qdrant vector store)

### Operaciones humanas
- ✅ Escalado a operador humano (mensaje se pasa a Chatwoot inbox)
- ✅ Panel admin Next.js para gestión de casos, elementos, tarifas, usuarios
- ✅ Autenticación JWT con RBAC

### Seguridad
- ✅ Validación SSRF de URLs de imágenes
- ✅ Validación multi-capa de imágenes (formato, tamaño, extensión, contenido)
- ✅ PDFs hasta 30 páginas

### Persistencia
- ✅ Checkpoints de conversación en Redis (LangGraph checkpointer)
- ✅ Datos estructurados en PostgreSQL
- ✅ Logs estructurados JSON (structlog)

## Qué NO podemos hacer hoy (requiere trabajo nuevo)

### Canales
- ❌ Voz / audio (ni TTS ni STT)
- ❌ Video calls
- ❌ SMS / email como canal primario (email se usa solo como canal secundario para escalado, no para conversación completa)
- ❌ Telegram, Instagram, otros canales de mensajería

### IA
- ❌ Generación de imágenes (no hay integración con modelo de imagen)
- ❌ OCR avanzado sobre documentos (hay validación de formato, no extracción de texto)
- ❌ Análisis de vídeo (frames individuales como imagen, sí; video completo, no)

### Operaciones
- ❌ Pagos online (no hay integración con pasarela)
- ❌ Firma electrónica de documentos
- ❌ Emisión de facturas automática
- ❌ Notificaciones push fuera de la ventana de 24h (excepto templates aprobados de WhatsApp, que NO están configurados aún)
- ❌ Llamadas telefónicas automatizadas

### Datos externos
- ❌ Consulta a BOE / BOCE (registro oficial español) en tiempo real
- ❌ Consulta a ITV / DGT
- ❌ Integración con sistemas de gestión de taller (DMS) de terceros

## Qué está EN desarrollo (no disponible pero en roadmap)

_(Vacío por ahora. Esta sección se actualiza cuando el owner y el Arquitecto-AI acuerdan que algo pasa de "no soportado" a "en desarrollo". Cuando pase a "disponible", se mueve a la sección "SÍ podemos".)_

## Reglas del catálogo

1. **Nunca prometer algo que no esté en "SÍ podemos"**. Si el owner pide algo que está en "NO podemos", el Arquitecto-AI responde: *"Esto requiere capacidades nuevas. Antes de actualizar el spec tenemos que añadir [X] a `00-capacidades.md`. ¿Autorizás?"*
2. **Actualizar este archivo es un change aparte**. Ampliar capacidades no es scope de un change de comportamiento; tiene su propio ciclo de SDD.
3. **Cuando una capacidad cambia de estado, commit separado**. Facilita auditoría.
