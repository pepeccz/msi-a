# Estándares Shared Utilities

---

## 1. Pydantic Settings (OBLIGATORIO)

```python
# ✅ CORRECTO
from shared.config import get_settings

settings = get_settings()
database_url = settings.DATABASE_URL
llm_model = settings.LLM_MODEL

# ❌ INCORRECTO
import os
database_url = os.getenv("DATABASE_URL")  # NEVER!
```

---

## 2. Redis Streams

```python
from shared.redis_client import get_redis_client, add_to_stream, INCOMING_STREAM

redis = get_redis_client()

# Add message
await add_to_stream(
    redis,
    INCOMING_STREAM,
    {
        "message_id": str(message_id),
        "content": message_content,
    }
)

# Read with consumer group
messages = await redis.xreadgroup(
    "my_group",
    "consumer_1",
    {INCOMING_STREAM: ">"},
    count=1,
    block=5000,
)
```

---

## 3. Hybrid LLM Router

```python
from shared.llm_router import get_llm_router, TaskType

router = get_llm_router()

# Conversation (cloud)
response = await router.invoke(
    task_type=TaskType.CONVERSATION,
    messages=[{"role": "user", "content": "Hola"}],
)

# Simple RAG (local)
response = await router.invoke(
    task_type=TaskType.SIMPLE_RAG,
    messages=[...],
)
```

---

## 4. Chatwoot Client

```python
from shared.chatwoot_client import ChatwootClient

client = ChatwootClient()

# Send message
await client.send_message(
    conversation_id=123,
    content="Hola, ¿cómo estás?",
    message_type="outgoing",
)

# Send images
await client.send_images(
    conversation_id=123,
    image_urls=["https://..."],
)
```

---

## 5. Image Security

```python
from shared.image_security import validate_image_full, sanitize_filename

# Validate image
mime_type, width, height = validate_image_full(image_bytes)

# Sanitize filename
safe_name = sanitize_filename("../../etc/passwd")  # → "passwd"
```

---

## 6. Settings Cache

```python
from shared.settings_cache import get_cached_setting, invalidate_setting_cache

# Get cached setting (5s TTL)
panic_mode = await get_cached_setting("PANIC_MODE_ENABLED")

# Invalidate after update
await invalidate_setting_cache("PANIC_MODE_ENABLED")
```

---

**Última actualización:** Febrero 2026
