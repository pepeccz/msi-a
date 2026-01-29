# Ollama: Servicio Opcional

## Estado Actual

Ollama es ahora un servicio **opcional** en MSI-a. El sistema funciona completamente sin él, utilizando OpenRouter como proveedor LLM principal.

## Funcionalidad Afectada

| Funcionalidad | Sin Ollama | Impacto |
|--------------|-----------|---------|
| **Conversación del agente** | ✅ Funciona con OpenRouter | Ninguno - OpenRouter es el LLM principal |
| **Fallback ante rate-limit** | ❌ No disponible | Bajo - El agente esperará y reintentará con OpenRouter |
| **Clasificación de vehículos** | ✅ Funciona con OpenRouter | Ninguno - Fallback automático a OpenRouter |
| **Embeddings RAG** | ⚠️ Requiere configuración alternativa | Ver sección RAG más abajo |

## Comportamiento del Sistema

### Sin Ollama (Estado Actual)

1. **Arranque:** Todos los servicios arrancan normalmente sin esperar a Ollama
2. **Conversación:** Funciona 100% con OpenRouter (modelo configurado en `LLM_MODEL`)
3. **Rate Limits:** Si OpenRouter retorna 429, el agente esperará y reintentará (backoff exponencial)
4. **Clasificación:** `identificar_tipo_vehiculo` usa OpenRouter directamente

### Con Ollama Funcionando

1. **Arranque:** Igual que sin Ollama (no bloquea)
2. **Conversación:** OpenRouter principal, Ollama como fallback inmediato ante 429
3. **Rate Limits:** Fallback instantáneo a Ollama (llama3:8b) sin espera
4. **Clasificación:** Intenta Ollama primero (qwen2.5:3b), luego OpenRouter

## Cómo Arrancar Ollama

### Requisito: Driver NVIDIA Funcional

```bash
# Verificar driver NVIDIA
nvidia-smi

# Si muestra error "driver/library version mismatch":
sudo reboot  # O actualizar nvidia-docker2
```

### Arrancar Ollama

```bash
cd /home/autohomologacion/msi-a
docker-compose up -d ollama ollama-setup
```

### Verificar que Funciona

```bash
# Ver logs
docker-compose logs -f ollama

# Verificar modelos descargados
docker-compose exec ollama ollama list

# Debe mostrar:
# - nomic-embed-text
# - qwen2.5:3b
# - llama3:8b
```

### Reiniciar Agent (Opcional)

```bash
# No es necesario reiniciar, pero para que use Ollama inmediatamente:
docker-compose restart agent
```

## Configuración RAG sin Ollama

Si necesitas usar RAG sin Ollama, debes configurar un proveedor alternativo de embeddings:

### Opción 1: OpenAI Embeddings

```python
# En api/services/embedding_service.py
# Cambiar de OllamaEmbeddings a OpenAIEmbeddings

from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",  # 1536 dims
    openai_api_key=settings.OPENAI_API_KEY,
)
```

### Opción 2: Sentence Transformers Local

```python
from langchain_huggingface import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2",  # 384 dims
)
```

**Nota:** Cambiar el modelo de embeddings requiere:
1. Modificar `api/services/embedding_service.py`
2. Re-procesar todos los documentos existentes
3. Actualizar la configuración de Qdrant

## Troubleshooting

### "Ollama fallback not available"

**Log:**
```
Ollama not available (expected if GPU unavailable), continuing with rate-limited OpenRouter
```

**Causa:** Ollama no está corriendo o no es accesible.

**Acción:** Normal si no necesitas el fallback. Si quieres activarlo, arranca Ollama (ver arriba).

### "langchain_ollama not available"

**Log:**
```
ImportError: langchain_ollama not available - Ollama fallback disabled
```

**Causa:** El módulo no está instalado (no debería pasar con requirements.txt actual).

**Acción:** Verificar que `langchain-ollama>=0.2.0` está en `requirements.txt` y reconstruir el contenedor.

### Agent no arranca después de cambios

**Síntoma:** El agent crashea al arrancar.

**Verificar:**
```bash
docker-compose logs agent | grep -i error
```

**Solución común:** Reconstruir imagen del agent:
```bash
docker-compose build agent
docker-compose up -d agent
```

## Cambios Técnicos Realizados

| Archivo | Cambio |
|---------|--------|
| `docker-compose.yml` | Eliminada dependencia `ollama:` del servicio `agent` |
| `agent/nodes/conversational_agent.py` | Import condicional de `ChatOllama` con `OLLAMA_AVAILABLE` flag |
| `agent/nodes/conversational_agent.py` | Logging mejorado cuando Ollama no está disponible |
| `agent/tools/vehicle_tools.py` | Timeout reducido a 5s para detección rápida |
| `shared/ollama_client.py` | **NUEVO** - Helper para verificar disponibilidad |
| `api/services/log_monitor.py` | Detecta contenedores corriendo antes de monitorear |

## Filosofía de Diseño

**Degradación Elegante:** El sistema debe funcionar sin servicios opcionales, degradando funcionalidad de manera controlada sin crashear.

**Cloud First:** OpenRouter es el proveedor principal y siempre disponible. Ollama es una optimización (más rápido, más barato) pero no crítica.

**Fail Fast:** Detectar rápido si un servicio no está disponible (timeouts cortos) en vez de bloquear el flujo principal.

---

Última actualización: 2026-01-29
