# /security-review Command

Perform security analysis focused on OWASP Top 10 and LLM vulnerabilities.

## Usage

```
/security-review <file, directory, or feature>
/security-review                              # Review entire codebase
```

## Examples

```
/security-review api/routes/auth.py
/security-review agent/nodes/
/security-review the webhook handling code
```

## Behavior

1. Delegates to the **security-reviewer** agent
2. Scans for common vulnerabilities
3. Checks LLM-specific security (prompt injection)
4. Provides remediation guidance

## Security Focus Areas

### OWASP Top 10
- Injection (SQL, Command, LDAP)
- Broken Authentication
- Sensitive Data Exposure
- XML External Entities
- Broken Access Control
- Security Misconfiguration
- Cross-Site Scripting (XSS)
- Insecure Deserialization
- Using Components with Known Vulnerabilities
- Insufficient Logging & Monitoring

### LLM-Specific (Critical for MSI-a)
- Prompt Injection
- Data Leakage
- Inadequate Sandboxing
- Unauthorized Code Execution
- Over-reliance on LLM Output

## Output

```markdown
## Security Review

### Risk Level: Critical/High/Medium/Low

### Vulnerabilities Found
[Detailed findings with locations and fixes]

### Security Recommendations
[Proactive improvements]

### Passed Checks
[What's already secure]
```

## When to Use

- Before deploying to production
- When handling user input
- When working with authentication
- When modifying LLM interactions
- During security audits

## Notes

- Always fix Critical issues immediately
- Security review should be part of PR process
- Consider running `pip-audit` and `npm audit` too
