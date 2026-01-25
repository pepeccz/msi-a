# /architecture Command

Get architectural guidance and create decision records.

## Usage

```
/architecture <question or design problem>
```

## Examples

```
/architecture How should I implement real-time notifications?
/architecture Should we use Redis or PostgreSQL for session storage?
/architecture Design the document processing pipeline
```

## Behavior

1. Delegates to the **architect** agent
2. Analyzes the architectural question
3. Considers MSI-a's existing patterns
4. Provides recommendation with trade-offs
5. Creates ADR if needed

## MSI-a Architecture Context

```
WhatsApp → Chatwoot → API → Redis Streams → Agent → LLM
                       ↓
                  PostgreSQL
                       ↓
              Admin Panel (Next.js)
```

## Output

```markdown
## Architecture Recommendation

### Problem
[What we're solving]

### Recommended Approach
[Detailed recommendation]

### Trade-offs
| Aspect | Pro | Con |
|--------|-----|-----|

### ADR Required?
[Yes/No with draft if yes]
```

## When to Use

- Before implementing new features
- When choosing between approaches
- When adding new services/components
- When patterns seem inconsistent
- When making breaking changes

## Architecture Principles

1. **Async Everything** - No blocking I/O
2. **Event-Driven** - Use Redis Streams
3. **Single Responsibility** - Clear component boundaries
4. **Stateless Services** - State in DB/Redis
5. **Type Safety** - Pydantic + TypeScript strict

## Notes

- Check `docs/decisions/` for existing ADRs
- Consistency with existing patterns is preferred
- Major decisions should be documented
