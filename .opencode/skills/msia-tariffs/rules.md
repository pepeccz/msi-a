# msia-tariffs Critical Rules

**Quick refresh for long sessions (~40 tokens)**

## ALWAYS

- Match categories by `(slug, client_type)` tuple
- Use keywords for element matching (case-insensitive)
- Include base documentation in results
- Check for applicable warnings
- Let element count determine tier automatically

## NEVER

- Hardcode prices → fetch from database
- Skip variant resolution when `elementos_con_variantes` present
- Forget client_type when querying categories
