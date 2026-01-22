# ADR-001: Redis Streams for Message Queue

## Status

Accepted

## Date

2024-12-15

## Context

MSI-a needs to process WhatsApp messages from Chatwoot webhooks. The agent processing can take several seconds (LLM calls, database queries), and we need:

1. Reliable message delivery
2. Message batching (users often send multiple short messages)
3. Decoupling between API and Agent
4. Ordered message processing per conversation

## Decision

Use Redis Streams as the message queue between API (webhook receiver) and Agent (message processor).

### Implementation

```
Chatwoot Webhook → API → Redis Stream → Agent Consumer
                          ↓
                    XADD msi:messages
                    {conversation_id, message, ...}
```

- One stream: `msi:messages`
- Consumer group: `agent-group`
- Message batching: configurable window (default 2 seconds)
- Messages keyed by `conversation_id` for ordering

## Consequences

### Positive

- **Reliability**: Redis Streams provide acknowledgment and replay on failure
- **Batching**: Can accumulate messages before processing (reduces LLM calls)
- **Decoupling**: API responds immediately, agent processes async
- **Scalability**: Can add multiple agent consumers if needed
- **Simplicity**: Uses existing Redis infrastructure

### Negative

- **Complexity**: Additional moving part vs direct processing
- **Latency**: Batching adds delay (configurable)
- **Redis dependency**: Agent cannot function without Redis

### Neutral

- Redis already used for LangGraph checkpointer

## Alternatives Considered

### Alternative A: Direct Processing

Process messages synchronously in webhook handler.

**Rejected because:**
- Webhook timeouts on long LLM calls
- No message batching
- No decoupling

### Alternative B: Celery + RabbitMQ

Use Celery task queue.

**Rejected because:**
- Overkill for single-queue use case
- Additional infrastructure (RabbitMQ/Redis as broker)
- More complex deployment

### Alternative C: PostgreSQL LISTEN/NOTIFY

Use PostgreSQL for pub/sub.

**Rejected because:**
- No persistence for unprocessed messages
- No consumer groups
- Less suited for this pattern

## References

- [Redis Streams Documentation](https://redis.io/docs/data-types/streams/)
- Implementation: `shared/redis_client.py`, `agent/main.py`
