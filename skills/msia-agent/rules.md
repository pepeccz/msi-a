# msia-agent Critical Rules

**Quick refresh for long sessions (~50 tokens)**

## ALWAYS

- `async def` for all nodes and tools
- Return `dict` from nodes (state updates)
- Use `.get()` for state access
- `skip_validation=True` after identification
- **Price BEFORE images** - state price, then send images

## NEVER

- `identificar_y_resolver_elementos()` for variant responses → use `seleccionar_variante_por_respuesta()`
- Send images twice (check `pending_images`)
- Modify state directly → return updates
- Invent variants not in `preguntas_variantes`
