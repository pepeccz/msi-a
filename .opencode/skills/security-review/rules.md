# Security Quick Rules

## Never Do

1. **No hardcoded secrets** - Use environment variables
2. **No SQL concatenation** - Use parameterized queries
3. **No user input in shell commands** - Validate and escape
4. **No sensitive data in logs** - Redact passwords, tokens
5. **No pickle with untrusted data** - Use JSON

## Always Do

1. **Validate all input** - Pydantic models
2. **Verify webhook signatures** - HMAC comparison
3. **Check authorization** - Verify ownership
4. **Hash passwords** - bcrypt or argon2
5. **Log security events** - Failed logins, access denied

## LLM Security

```python
# Multi-layer defense
1. System prompt boundaries
2. Input sanitization  
3. Output validation
4. Tool permission limits
```

## Quick Checks

```bash
pip-audit    # Python vulnerabilities
npm audit    # Node vulnerabilities
```

## Severity

- **Critical**: RCE, SQL injection, auth bypass
- **High**: Data leak, privilege escalation
- **Medium**: Missing validation, weak crypto
- **Low**: Info disclosure, missing headers
