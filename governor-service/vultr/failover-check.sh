#!/usr/bin/env bash
# --------------------------------------------------------------------------
# failover-check.sh — Standby health monitor & DNS failover helper
#
# Checks the primary (Fly.io) backend. If it's down, prints instructions
# or (optionally) calls the Vultr Standby into service.
#
# Designed to run from cron every 60 seconds:
#   * * * * * /home/deploy/openclaw-runtime-governor/governor-service/vultr/failover-check.sh >> /var/log/governor-failover.log 2>&1
# --------------------------------------------------------------------------
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
PRIMARY_URL="${PRIMARY_URL:-https://openclaw-governor.fly.dev/healthz}"
STANDBY_URL="${STANDBY_URL:-http://localhost:8000/healthz}"
TIMEOUT=8          # seconds
MAX_FAILURES=3     # consecutive primary failures before alerting
STATE_FILE="/tmp/governor_failover_state"

# ── Functions ──────────────────────────────────────────────────────────────
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

check_endpoint() {
    local url="$1"
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout "$TIMEOUT" -m "$TIMEOUT" "$url" 2>/dev/null || echo "000")
    echo "$status"
}

# ── Main ───────────────────────────────────────────────────────────────────
PRIMARY_STATUS=$(check_endpoint "$PRIMARY_URL")
STANDBY_STATUS=$(check_endpoint "$STANDBY_URL")

# Track consecutive failures
FAILURES=0
[ -f "$STATE_FILE" ] && FAILURES=$(cat "$STATE_FILE")

if [ "$PRIMARY_STATUS" = "200" ]; then
    # Primary healthy — reset counter
    echo 0 > "$STATE_FILE"
    echo "$(ts) PRIMARY=OK(${PRIMARY_STATUS}) STANDBY=${STANDBY_STATUS} failures=0"
    exit 0
fi

# Primary unhealthy
FAILURES=$((FAILURES + 1))
echo "$FAILURES" > "$STATE_FILE"
echo "$(ts) PRIMARY=DOWN(${PRIMARY_STATUS}) STANDBY=${STANDBY_STATUS} failures=${FAILURES}"

if [ "$FAILURES" -ge "$MAX_FAILURES" ]; then
    echo "$(ts) ⚠ PRIMARY DOWN for ${FAILURES} consecutive checks."

    if [ "$STANDBY_STATUS" = "200" ]; then
        echo "$(ts) ✅ Vultr standby is HEALTHY. Ready for failover."
        echo "$(ts)    → Update Vercel env: NEXT_PUBLIC_GOVERNOR_API=https://<vultr-domain>"
        echo "$(ts)    → Or update DNS CNAME for governor API to point to Vultr IP."
    else
        echo "$(ts) ❌ Vultr standby is also DOWN (${STANDBY_STATUS}). Manual intervention needed."
    fi

    # ── Optional: auto-notify via webhook ──
    # Uncomment and configure to get Slack/Discord/email alerts:
    #
    # WEBHOOK_URL="${WEBHOOK_URL:-}"
    # if [ -n "$WEBHOOK_URL" ]; then
    #     curl -s -X POST "$WEBHOOK_URL" \
    #       -H "Content-Type: application/json" \
    #       -d "{\"text\":\"🚨 OpenClaw Governor primary (Fly.io) DOWN for ${FAILURES} checks. Standby status: ${STANDBY_STATUS}\"}" \
    #       > /dev/null 2>&1 || true
    # fi
fi
