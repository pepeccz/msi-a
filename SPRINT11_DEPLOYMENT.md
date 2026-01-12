# SPRINT 11: Production Deployment & Monitoring

**Objective:** Safely deploy the element system to production with comprehensive monitoring and rollback capabilities.

**Duration:** 3-5 days (including monitoring period)
**Risk Level:** Medium (Feature flag allows instant rollback)

## Deployment Strategy

### Principle: Gradual Rollout with Feature Flags

The element system will be deployed using a **three-phase approach** with feature flags:

1. **Phase 1 (Day 1):** Deploy with system DISABLED
   - New code deployed but `USE_ELEMENT_SYSTEM=false`
   - Verify no errors, database migrations successful
   - Legacy system continues unchanged

2. **Phase 2 (Days 2-3):** Enable Compare Mode
   - Set `ELEMENT_SYSTEM_COMPARE_MODE=true`
   - Both systems run in parallel
   - Log discrepancies for analysis
   - Monitor for 24-48 hours

3. **Phase 3 (Days 4-5):** Switch to New System
   - Set `USE_ELEMENT_SYSTEM=true`, `ELEMENT_SYSTEM_COMPARE_MODE=false`
   - Monitor intensively for 24 hours
   - Rollback plan ready

## Pre-Deployment Checklist

### Code Review
- [ ] All tests pass locally
- [ ] Code review completed
- [ ] No security vulnerabilities
- [ ] Documentation updated
- [ ] CHANGELOG updated

### Testing
- [ ] Unit tests: 100% pass
- [ ] Integration tests: 100% pass
- [ ] Performance tests: All benchmarks met
- [ ] Regression tests: Legacy system works
- [ ] Load tests: 100 req/s sustained

### Database
- [ ] Migration script tested on backup
- [ ] Rollback script prepared
- [ ] Backup taken before deployment
- [ ] No data loss in migration

### Configuration
- [ ] Environment variables documented
- [ ] Feature flags configured
- [ ] Redis cache configured
- [ ] Logging configured for new system
- [ ] Monitoring/alerting configured

### Team Readiness
- [ ] Team notified of deployment
- [ ] Oncall engineer assigned
- [ ] Runbooks prepared
- [ ] Communication channels open

## Phase 1: Deploy with System Disabled

### Timeline: Day 1 (1-2 hours)

### Step 1: Pre-Deployment Verification (15 minutes)
```bash
# Verify current system health
curl https://api.msi-a.com/health

# Check database status
psql -U msia -d msia_db -c "SELECT count(*) FROM customers;"

# Verify no uncommitted transactions
psql -U msia -d msia_db -c "SELECT * FROM pg_stat_activity WHERE xact_start IS NOT NULL;"
```

### Step 2: Backup Database (10 minutes)
```bash
# Full backup
pg_dump msia_db | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Backup size check
du -h backup_*.sql.gz

# Store in S3
aws s3 cp backup_*.sql.gz s3://msia-backups/
```

### Step 3: Deploy Code (15 minutes)
```bash
# Pull latest code
git pull origin main

# Verify no uncommitted changes in target
git status

# Deploy via CI/CD (example with GitHub Actions)
git tag v1.11.0-element-system
git push origin v1.11.0-element-system

# CI/CD pipeline automatically:
# - Runs tests
# - Builds Docker images
# - Pushes to registry
# - Updates deployment manifest
```

### Step 4: Run Database Migrations (5 minutes)
```bash
# In docker-compose environment
docker-compose exec api alembic upgrade head

# Verify migration succeeded
docker-compose exec postgres psql -U msia -d msia_db -c "
  SELECT version FROM alembic_version;
"

# Verify tables created
docker-compose exec postgres psql -U msia -d msia_db -c "
  SELECT tablename FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY tablename;
"
```

### Step 5: Verify Feature Flag Disabled (5 minutes)
```bash
# Check environment variables
echo $USE_ELEMENT_SYSTEM  # Should be: false

# Verify in code (optional health check endpoint)
curl https://api.msia-a.com/health/features | jq '.USE_ELEMENT_SYSTEM'
# Expected: false
```

### Step 6: Smoke Tests (10 minutes)
```bash
# Test legacy system still works
curl -X POST https://api.msi-a.com/api/agent/calculate-tariff \
  -H "Content-Type: application/json" \
  -d '{
    "categoria": "autocaravanas-profesional",
    "descripcion": "escalera mecánica"
  }'
# Expected: 200 OK with tariff result

# Verify new tables exist but aren't used
curl https://api.msi-a.com/api/admin/elements \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.total'
# Expected: 0 or whatever count (shouldn't error)

# Test admin panel loads
curl https://admin.msi-a.com/elementos
# Expected: 200 OK
```

### Step 7: Monitor for Stability (30 minutes)
```bash
# Watch logs for errors
docker-compose logs -f api | grep -i error

# Monitor metrics
# - Error rate: should be <0.1%
# - Response time p95: should be <500ms
# - CPU/Memory: should be stable

# Check no alerts firing
# (From monitoring dashboard or alert system)
```

### Exit Criteria for Phase 1
✅ Code deployed without errors
✅ Database migrations successful
✅ Legacy system functioning normally
✅ No new errors in logs
✅ Performance metrics stable
✅ Feature flag confirmed disabled

---

## Phase 2: Enable Compare Mode (48 hours)

### Timeline: Days 2-3 (Passive monitoring)

### Step 1: Enable Compare Mode (5 minutes)
```bash
# Update environment variable
# In docker-compose.yml or Kubernetes manifests:
ELEMENT_SYSTEM_COMPARE_MODE: "true"
USE_ELEMENT_SYSTEM: "false"

# Redeploy (or restart service)
docker-compose restart api
# or
kubectl rollout restart deployment/msia-api
```

### Step 2: Verify Both Systems Running (10 minutes)
```bash
# Make a test query
curl -X POST https://api.msi-a.com/api/agent/calculate-tariff \
  -H "Content-Type: application/json" \
  -d '{
    "categoria": "autocaravanas-profesional",
    "descripcion": "escalera mecánica"
  }'

# Check logs for DISCREPANCIA_SISTEMAS entries
docker-compose logs api | grep "DISCREPANCIA"
# Should NOT see discrepancies initially (both systems same code path)
```

### Step 3: Monitor Discrepancies (24-48 hours)

**What to look for:**

```bash
# View discrepancies
docker-compose logs api | grep "DISCREPANCIA" | head -20

# Count discrepancies
docker-compose logs api | grep "DISCREPANCIA" | wc -l
```

**Expected Scenarios:**

1. **No Discrepancies (BEST CASE)**
   - Both systems return same result
   - This means new system is correct
   → Proceed to Phase 3

2. **Discrepancies Found**
   - New system returns different tariff
   - Analyze each discrepancy
   - Fix seed data or algorithm if needed
   - Return to testing before retry

3. **Errors in New System**
   - New system throws exceptions
   - Review error logs
   - Fix bugs
   - Re-test before retry

**Analysis Process:**

```bash
# Export discrepancies to file for analysis
docker-compose logs api | grep "DISCREPANCIA" > discrepancies.log

# Parse each discrepancy
# Format: DISCREPANCIA_SISTEMAS: old_tier=T3, new_tier=T2, input="escalera..."

# Verify which is correct
# - Check PDF: does escalera require T3 or T2?
# - Check seed data: are limits configured correctly?
# - Check algorithm: is tier resolution correct?

# Example verification
# If discrepancy shows T3 vs T2 for single escalera:
# - T3 includes 1 escalera (max) → cost 180€
# - T2 includes T3 (max 2) → cost 230€
# - Single escalera should be T2 (includes T3 which has escalera)
# - But we want CHEAPEST → should be T3 if it fits
# - So if new system returns T2 instead of T3, it's WRONG
```

### Step 4: Generate Daily Report (End of each day)

Create JSON log file:

```json
{
  "phase": "compare_mode",
  "date": "2026-01-15",
  "total_queries": 1254,
  "discrepancies": 0,
  "errors": 0,
  "status": "OK - no issues detected",
  "samples": [
    {
      "input": "escalera mecánica",
      "legacy_result": "T2 (230€)",
      "new_result": "T2 (230€)",
      "match": true
    },
    {
      "input": "antena parabólica",
      "legacy_result": "T6 (59€)",
      "new_result": "T6 (59€)",
      "match": true
    }
  ]
}
```

### Exit Criteria for Phase 2
✅ No discrepancies found (or all explained and fixed)
✅ No errors in new system
✅ Performance unchanged
✅ 24-48 hour monitoring complete

---

## Phase 3: Switch to New System (24 hours intensive monitoring)

### Timeline: Days 4-5

### Step 1: Update Feature Flags (5 minutes)
```bash
# Update environment
USE_ELEMENT_SYSTEM: "true"
ELEMENT_SYSTEM_COMPARE_MODE: "false"

# Redeploy
docker-compose restart api
```

### Step 2: Smoke Tests (10 minutes)
```bash
# Verify new system in use
curl -X POST https://api.msi-a.com/api/agent/calculate-tariff \
  -H "Content-Type: application/json" \
  -d '{
    "categoria": "autocaravanas-profesional",
    "descripcion": "escalera mecánica"
  }'

# Should still work (now using new system)
# Check logs for element matching
docker-compose logs api | grep "matching\|resolve\|select" | head -5
```

### Step 3: Intensive Monitoring (24 hours)

**Key Metrics to Track:**

```
1. Error Rate
   - Target: < 0.1%
   - Alert if: > 0.5%

2. Response Time (p95)
   - Target: < 500ms
   - Alert if: > 1s

3. Element Matching Success
   - Target: > 95% matches with confidence > 0.6
   - Alert if: < 90%

4. Tariff Selection Correctness
   - Target: 100% matches expectations
   - Track: "Did user accept the tariff offered?"

5. Cache Hit Rate
   - Target: > 80% for resolve_tier_elements
   - Info: Indicates good caching

6. User Feedback
   - Monitor chat channel for complaints
   - Track: "Did element identification work?"
```

**Monitoring Dashboard:**

Create a real-time dashboard showing:

```
┌─────────────────────────────────────────────────┐
│          ELEMENT SYSTEM PRODUCTION               │
├─────────────────────────────────────────────────┤
│                                                  │
│  Status: ✓ HEALTHY                              │
│                                                  │
│  Error Rate:        0.02%     [████░░░░░░]     │
│  Response Time:     234ms      [███░░░░░░░]     │
│  Element Match:     97.3%      [██████████]     │
│  Cache Hit Rate:    84.5%      [████████░░]     │
│                                                  │
│  Last Hour:                                      │
│  Queries Processed:  1,284                       │
│  Errors:             0                          │
│  Match Success:      1,247/1,284 (97.1%)       │
│                                                  │
│  Recent Samples:                                 │
│  ✓ escalera → ESC_MEC → T3 (180€)               │
│  ✓ antena → ANTENA_PAR → T6 (59€)              │
│  ✓ escalera + toldo → ESC_MEC+TOLDO → T2       │
│                                                  │
└─────────────────────────────────────────────────┘
```

### Step 4: Document Observations

```markdown
# Day 4 Observations

## Positive
- Element identification working perfectly
- Tariff selection accurate
- Performance excellent (avg 234ms)
- Cache hit rate high (84.5%)

## Issues Found
- None

## Recommendations
- Keep running, system is stable
- Can proceed with full production rollout
```

### Step 5: Automated Testing

```bash
# Run full test suite every hour
(cd /path/to/project && pytest tests/ --tb=short)

# Run load test
locust -f tests/load/locustfile.py \
  --headless -u 100 -r 10 --run-time 10m

# Check database health
psql -U msia -d msia_db -c "SELECT NOW(), count(*) FROM elements;"
```

### Exit Criteria for Phase 3
✅ No errors in production
✅ Error rate < 0.1%
✅ Response time meets targets
✅ Element matching > 95% success
✅ User feedback positive
✅ 24 hour monitoring complete

---

## Rollback Procedures

### Quick Rollback (5 minutes)
**If critical issues found, immediate rollback:**

```bash
# Disable new system immediately
USE_ELEMENT_SYSTEM: "false"
ELEMENT_SYSTEM_COMPARE_MODE: "false"

# Redeploy
docker-compose restart api

# Verify legacy system
curl -X POST https://api.msi-a.com/api/agent/calculate-tariff \
  -d '{"categoria": "autocaravanas-profesional", "descripcion": "test"}'

# Should return to normal
```

### Full Rollback (15 minutes)
**If database issues detected:**

```bash
# 1. Restore database from backup
docker-compose down
rm -rf postgres_data/

# 2. Restore from backup
gunzip < backup_20260115_143022.sql.gz | \
  docker-compose exec -T postgres psql -U msia -d msia_db

# 3. Revert code to previous version
git checkout v1.10.0
docker-compose up -d

# 4. Verify system
curl https://api.msi-a.com/health
```

### No Rollback Needed
**If minor issues found that don't affect users:**

```bash
# Document issue
echo "Issue: Element X has no images" >> issues.log

# Fix in next deployment
# Example: Re-run seed for missing data

# Patch: Update element directly
docker-compose exec postgres psql -U msia -d msia_db -c "
  UPDATE element_images
  SET image_url = 'https://...'
  WHERE element_id = 'xxx'
  AND image_url IS NULL;
"
```

## Monitoring & Alerts

### Prometheus Metrics

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'msia-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

### Key Metrics to Track

```python
# In code (using Prometheus)
from prometheus_client import Counter, Histogram, Gauge

# Element matching success rate
element_match_counter = Counter(
    'element_matches_total',
    'Total element matches',
    ['category', 'success']
)

# Tier resolution time
tier_resolution_time = Histogram(
    'tier_resolution_seconds',
    'Time to resolve tier elements',
)

# Tariff selection accuracy
tariff_selected = Counter(
    'tariff_selected_total',
    'Tariffs selected',
    ['tier_code']
)

# Cache metrics
cache_hits = Counter(
    'cache_hits_total',
    'Cache hits',
    ['key_pattern']
)
```

### Alert Rules

```yaml
# alerting_rules.yml
groups:
  - name: element_system
    rules:
      - alert: ElementSystemErrorRate
        expr: rate(errors_total[5m]) > 0.005
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Element system error rate too high"

      - alert: TierResolutionSlow
        expr: histogram_quantile(0.95, tier_resolution_seconds) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Tier resolution p95 latency high"

      - alert: CacheHitRateLow
        expr: cache_hit_rate < 0.7
        for: 10m
        labels:
          severity: info
        annotations:
          summary: "Cache hit rate below target"
```

### Alert Channels

- **Critical**: Page on-call engineer via PagerDuty
- **Warning**: Slack #msia-alerts channel
- **Info**: Log to monitoring dashboard

## Operational Handoff

### Documentation for Production Team

**Location:** `/docs/element-system-operations.md`

**Contents:**

1. **Architecture Overview**
   - How element system works
   - Key components
   - Data flow diagram

2. **Deployment Guide**
   - Step-by-step deployment
   - Common issues
   - Rollback procedures

3. **Monitoring Guide**
   - Key metrics
   - Alert interpretation
   - Troubleshooting

4. **Maintenance Tasks**
   - Cache management
   - Database tuning
   - Performance optimization

5. **FAQ**
   - "Why is tariff different?"
   - "How do I add new element?"
   - "Why is matching slow?"

### Runbooks for On-Call

**`runbooks/element-system-degradation.md`**
```markdown
# Element System Degradation

## Symptoms
- Element matching returns no results
- Tariff selection times out
- Cache hit rate drops

## Diagnosis
1. Check error logs for exceptions
2. Verify database connectivity
3. Check Redis cache status
4. Review recent deployments

## Resolution
1. If database issue: See database runbook
2. If cache issue: Flush cache and restart
3. If code issue: Rollback to previous version
```

## Success Metrics

### Pre-Deploy Metrics (Baseline)
- Error rate: 0.01%
- Response time p95: 450ms
- Tariff accuracy: 100% (by definition)

### Post-Deploy Metrics (Target)
- Error rate: < 0.1% (5x margin)
- Response time p95: < 500ms (same)
- Element match accuracy: > 95%
- Tariff accuracy: = 100%
- Cache hit rate: > 80%
- User satisfaction: > 90%

### Red Flags (Immediate Rollback)
- Error rate > 1%
- Response time p95 > 2s
- Match accuracy < 80%
- Users reporting wrong tiffs
- Database query timeouts

## Timeline Summary

| Phase | Duration | Status | GO/NO-GO |
|-------|----------|--------|----------|
| Phase 1: Deploy Disabled | 1-2 hours | Run smoketests | GO if all pass |
| Phase 2: Compare Mode | 24-48 hours | Monitor discrepancies | GO if 0 discrepancies |
| Phase 3: Live Monitoring | 24 hours | Intensive tracking | GO if metrics healthy |
| **Total** | **2-4 days** | | |

## Post-Deployment Review

**After 1 week in production:**

1. **Metrics Review**
   - All metrics performing as expected?
   - Any anomalies?
   - Performance trending positive/negative?

2. **User Feedback**
   - Element identification working?
   - Tariff selection accurate?
   - Any complaints?

3. **Team Feedback**
   - Operations team comments?
   - Support team feedback?
   - Any deployment issues?

4. **Decision**
   - ✅ System stable, monitor normally
   - ⚠️ Minor issues, create tickets for fixes
   - ❌ Major issues, escalate

---

## Contact & Escalation

**During Deployment:**
- On-call Engineer: `+34-XXX-XXX-XXXX`
- Slack: `#msia-deployment`
- Bridge: `https://zoom.us/...` (deployment war room)

**Escalation Path:**
1. On-call engineer (immediate)
2. Engineering manager (if urgent, > P1)
3. Tech lead (if architectural issue)
4. CTO (if company-wide impact)

---

**SPRINT 11 Ready for Execution**

