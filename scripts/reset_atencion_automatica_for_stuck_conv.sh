#!/usr/bin/env bash
# reset_atencion_automatica_for_stuck_conv.sh
#
# Operator hotfix: Reset atencion_automatica=true for a stuck conversation.
#
# This sets the legacy display attribute back to true on a specific Chatwoot
# conversation. Useful if a conversation was previously stuck with the old gate
# and the admin panel shows incorrect display state.
#
# NOTE: After C2.9 is deployed, the actual bot gate is controlled by
# ConversationHistory.bot_paused_at (in the DB), NOT atencion_automatica.
# Use the admin panel's "Reanudar bot" button to resume the bot properly.
# This script only fixes the display attribute for legacy dashboards.
#
# Usage:
#   CHATWOOT_API_URL=https://... CHATWOOT_API_TOKEN=... \
#   CHATWOOT_ACCOUNT_ID=1 \
#   ./scripts/reset_atencion_automatica_for_stuck_conv.sh <conversation_id>
#
# Requirements: curl, jq
#
# Example:
#   CHATWOOT_API_URL=https://chatwoot.example.com CHATWOOT_API_TOKEN=abc123 \
#   CHATWOOT_ACCOUNT_ID=1 \
#   ./scripts/reset_atencion_automatica_for_stuck_conv.sh 12345

set -euo pipefail

CONV_ID="${1:-}"

if [[ -z "$CONV_ID" ]]; then
    echo "ERROR: conversation_id is required." >&2
    echo "Usage: $0 <conversation_id>" >&2
    exit 1
fi

if [[ -z "${CHATWOOT_API_URL:-}" ]]; then
    echo "ERROR: CHATWOOT_API_URL is not set." >&2
    exit 1
fi

if [[ -z "${CHATWOOT_API_TOKEN:-}" ]]; then
    echo "ERROR: CHATWOOT_API_TOKEN is not set." >&2
    exit 1
fi

if [[ -z "${CHATWOOT_ACCOUNT_ID:-}" ]]; then
    echo "ERROR: CHATWOOT_ACCOUNT_ID is not set." >&2
    exit 1
fi

API_URL="${CHATWOOT_API_URL}/api/v1/accounts/${CHATWOOT_ACCOUNT_ID}/conversations/${CONV_ID}/custom_attributes"
PAYLOAD='{"custom_attributes":{"atencion_automatica":true}}'

echo "Resetting atencion_automatica=true for conversation ${CONV_ID}..."

RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -X POST \
    -H "api_access_token: ${CHATWOOT_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}" \
    "${API_URL}")

HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_STATUS:")

if [[ "$HTTP_STATUS" == "200" ]]; then
    echo "SUCCESS (HTTP ${HTTP_STATUS}):"
    echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
    echo ""
    echo "REMINDER: To resume the bot properly, use the admin panel 'Reanudar bot' button"
    echo "or set ConversationHistory.bot_paused_at = NULL in the database."
else
    echo "ERROR (HTTP ${HTTP_STATUS}):" >&2
    echo "$BODY" >&2
    exit 1
fi
