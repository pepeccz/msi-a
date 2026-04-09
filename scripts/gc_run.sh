#!/bin/bash
################################################################################
# Garbage Collection Runner for MSI-a
#
# Calls the GC admin endpoint on the API container to clean up stale
# conversation records and orphaned case images.
#
# Usage:
#   ./scripts/gc_run.sh                    # Dry run (default)
#   ./scripts/gc_run.sh --execute          # Actually delete
#   ./scripts/gc_run.sh --days 60          # Custom retention (60 days)
#   ./scripts/gc_run.sh --execute --days 30
#
# Cron setup (weekly, Sunday 3 AM):
#   0 3 * * 0 cd /path/to/msi-a && ./scripts/gc_run.sh --execute >> logs/gc.log 2>&1
#
################################################################################

set -euo pipefail

# Defaults
DRY_RUN=true
RETENTION_DAYS=""
API_URL="http://localhost:8000"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --execute)
            DRY_RUN=false
            shift
            ;;
        --days)
            RETENTION_DAYS="$2"
            shift 2
            ;;
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--execute] [--days N] [--api-url URL]"
            exit 1
            ;;
    esac
done

# Build JSON body
BODY="{\"dry_run\": $DRY_RUN"
if [[ -n "$RETENTION_DAYS" ]]; then
    BODY="$BODY, \"retention_days\": $RETENTION_DAYS"
fi
BODY="$BODY}"

# Get admin JWT token
if [[ -f .env ]]; then
    source .env 2>/dev/null || true
fi

if [[ -z "${ADMIN_JWT_SECRET:-}" ]]; then
    echo "ERROR: ADMIN_JWT_SECRET not set. Source .env or export it."
    exit 1
fi

# Generate a short-lived admin token via the API login endpoint
TOKEN=$(curl -s -X POST "$API_URL/admin/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\": \"${ADMIN_USERNAME:-admin}\", \"password\": \"${ADMIN_PASSWORD:-}\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

if [[ -z "$TOKEN" ]]; then
    echo "ERROR: Failed to obtain admin token. Check credentials."
    exit 1
fi

# Run GC
echo "$(date -Iseconds) | GC starting | dry_run=$DRY_RUN retention_days=${RETENTION_DAYS:-default}"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/admin/gc/run" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "$BODY")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY_RESPONSE=$(echo "$RESPONSE" | sed '$d')

if [[ "$HTTP_CODE" -eq 200 ]]; then
    echo "$(date -Iseconds) | GC completed | $BODY_RESPONSE"
else
    echo "$(date -Iseconds) | GC FAILED | HTTP $HTTP_CODE | $BODY_RESPONSE"
    exit 1
fi
