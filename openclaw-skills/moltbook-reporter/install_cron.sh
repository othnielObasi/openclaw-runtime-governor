#!/usr/bin/env bash
# install_cron.sh
# Installs a cron entry for the current user that runs the Moltbook auto-run every 30 minutes.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$(command -v python3)"
SCRIPT="$REPO_DIR/openclaw-skills/moltbook-reporter/moltbook_lablab_poster.py"
LOG="$REPO_DIR/openclaw-skills/moltbook-reporter/auto_run.log"

CRON_CMD="cd $REPO_DIR && PYTHONPATH=./openclaw-skills/moltbook-reporter $PY $SCRIPT >> $LOG 2>&1"

# Run every 30 minutes
CRON_LINE="*/30 * * * * $CRON_CMD"

echo "Installing cron job: $CRON_LINE"
crontab -l 2>/dev/null | grep -Fv "$SCRIPT" | { cat; echo "$CRON_LINE"; } | crontab -
echo "Cron installed. Logs: $LOG"
