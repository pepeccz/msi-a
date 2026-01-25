# Context Optimization Quick Rules

## Do

1. **Delegate to agents** - `/code-review`, `/security-review`
2. **Compact often** - After each major task
3. **Search before read** - Grep → targeted read
4. **Batch operations** - Multiple files in parallel
5. **Summarize, don't repeat** - Reference past context

## Don't

1. **Don't read entire files** - Use line ranges
2. **Don't repeat long outputs** - Summarize
3. **Don't load all skills** - On-demand only
4. **Don't explore endlessly** - Note findings, compact, continue

## Warning Signs

- Slow responses
- AI forgets context
- Repetitive questions
- Degraded suggestions

## Recovery

1. Complete current task
2. Save state to `.session-context.md`
3. Compact
4. Reload minimal context
5. Continue

## Session Context Template

```markdown
## Active Task
[What you're doing]

## Key Files  
[File:lines that matter]

## Decisions
[Important choices made]
```

## Model Selection

| Task | Model |
|------|-------|
| Simple edits | Haiku |
| Complex work | Sonnet |
| Quick questions | Haiku |
