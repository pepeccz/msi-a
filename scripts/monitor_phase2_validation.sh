#!/bin/bash
# Phase 2 Semantic Validation Monitoring Script
# Monitor validation events, cache performance, and errors

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Phase 2 Semantic Validation - Live Monitoring"
echo "Started: $(date)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Function to count events in last N minutes
count_events() {
    local pattern="$1"
    local minutes="$2"
    local cutoff=$(date -u -d "$minutes minutes ago" +"%Y-%m-%d %H:%M:%S")
    
    docker-compose logs --since "$minutes"m agent 2>&1 | grep -c "$pattern" || echo "0"
}

# Function to get latest N events
get_latest() {
    local pattern="$1"
    local count="${2:-5}"
    
    docker-compose logs agent 2>&1 | grep "$pattern" | tail -n "$count"
}

while true; do
    clear
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Phase 2 Semantic Validation - Live Monitoring"
    echo "Time: $(date)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # Validation Event Counts (Last 5 Minutes)
    echo "📊 Validation Events (Last 5 Minutes)"
    echo "────────────────────────────────────────────────────────────"
    
    syntax_failed=$(count_events "syntax_validation_failed" 5)
    state_failed=$(count_events "state_validation_failed" 5)
    semantic_failed=$(count_events "semantic_validation_failed" 5)
    validation_passed=$(count_events "tool_validation_passed" 5)
    
    echo "  Syntax Validation Failed:    $syntax_failed"
    echo "  State Validation Failed:     $state_failed"
    echo "  Semantic Validation Failed:  $semantic_failed (NEW!)"
    echo "  All Validations Passed:      $validation_passed"
    echo ""
    
    # Cache Performance (Last 5 Minutes)
    echo "⚡ Cache Performance (Last 5 Minutes)"
    echo "────────────────────────────────────────────────────────────"
    
    cache_hits=$(count_events "cached_db_lookup.*hit=True" 5)
    cache_misses=$(count_events "cached_db_lookup.*hit=False" 5)
    
    total_cache=$((cache_hits + cache_misses))
    
    if [ $total_cache -gt 0 ]; then
        hit_rate=$(awk "BEGIN {printf \"%.1f\", ($cache_hits / $total_cache) * 100}")
        echo "  Cache Hits:     $cache_hits"
        echo "  Cache Misses:   $cache_misses"
        echo "  Hit Rate:       $hit_rate%"
        
        if [ $(echo "$hit_rate < 90.0" | bc -l) -eq 1 ]; then
            echo "  ⚠️  WARNING: Cache hit rate below 90%!"
        fi
    else
        echo "  No cache events in last 5 minutes"
    fi
    echo ""
    
    # Error Events (Last 5 Minutes)
    echo "❌ Errors (Last 5 Minutes)"
    echo "────────────────────────────────────────────────────────────"
    
    errors=$(count_events "level.*ERROR" 5)
    
    if [ "$errors" -gt 0 ]; then
        echo "  ⚠️  $errors errors detected!"
        echo ""
        echo "  Latest errors:"
        get_latest "ERROR" 3 | sed 's/^/    /'
    else
        echo "  ✅ No errors detected"
    fi
    echo ""
    
    # Latest Semantic Validation Events
    echo "🔍 Latest Semantic Validation Events"
    echo "────────────────────────────────────────────────────────────"
    
    latest_semantic=$(get_latest "semantic_validation" 3)
    
    if [ -n "$latest_semantic" ]; then
        echo "$latest_semantic" | sed 's/^/  /'
    else
        echo "  No semantic validation events yet"
    fi
    echo ""
    
    # System Health
    echo "💚 System Health"
    echo "────────────────────────────────────────────────────────────"
    
    agent_status=$(docker-compose ps agent | grep -E "(Up|Exit)" | awk '{print $4}')
    
    if echo "$agent_status" | grep -q "Up"; then
        echo "  ✅ Agent: Running (healthy)"
    else
        echo "  ❌ Agent: $agent_status"
    fi
    
    # Agent uptime
    agent_started=$(docker inspect msia-agent --format='{{.State.StartedAt}}' 2>/dev/null || echo "unknown")
    echo "  Started: $agent_started"
    echo ""
    
    # Instructions
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Press Ctrl+C to stop monitoring"
    echo "Refreshing in 30 seconds..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    sleep 30
done
