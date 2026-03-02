#!/usr/bin/env bash
# Deploy governor-service to Fly.io with all external modules vendored in.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "▸ Vendoring external modules into _modules/..."
rm -rf "$SCRIPT_DIR/_modules"
mkdir -p "$SCRIPT_DIR/_modules"

# Copy each external module directory
for mod in compliance-modules agent-fingerprinting surge-v2 impact-assessment integrations; do
  if [ -d "$ROOT_DIR/$mod" ]; then
    cp -r "$ROOT_DIR/$mod" "$SCRIPT_DIR/_modules/$mod"
    echo "  ✓ $mod"
  else
    echo "  ✗ $mod (not found, skipping)"
  fi
done

echo "▸ Deploying to Fly.io..."
cd "$SCRIPT_DIR"
fly deploy --remote-only "$@"

echo "▸ Cleaning up vendored modules..."
rm -rf "$SCRIPT_DIR/_modules"

echo "✓ Deploy complete"
