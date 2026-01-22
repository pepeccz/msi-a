# msia-agent Critical Rules

**Quick refresh for long sessions (~50 tokens)**

## ALWAYS

- `async def` for all nodes and tools
- Return `dict` from nodes (state updates)
- Use `.get()` for state access
- `skip_validation=True` after identification
- **Price BEFORE images** - state price, then send images
- **Mention ALL warnings** from `calcular_tarifa_con_elementos` - they are MANDATORY
- **Calculate tariff BEFORE sending images** - images depend on tariff result
- **Ask before sending images** (unless user explicitly asked for documentation)

## NEVER

- `identificar_y_resolver_elementos()` for variant responses -> use `seleccionar_variante_por_respuesta()`
- Send images twice (check `pending_images`)
- Modify state directly -> return updates
- Invent variants not in `preguntas_variantes`
- Invent content like "Incluye gestion completa, informe tecnico..." - ONLY use data from tools
- Omit warnings from tool results
- Call `enviar_imagenes_ejemplo` without `calcular_tarifa_con_elementos` first
