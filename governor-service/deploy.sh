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

echo "▸ Building and deploying to Fly.io..."
cd "$SCRIPT_DIR"

# Build locally & push — avoids Depot remote builder ignoring _modules/ via .gitignore
# Read app name from fly.toml
APP_NAME=$(grep '^app' fly.toml | head -1 | sed 's/.*= *"\(.*\)"/\1/')
IMAGE_TAG="registry.fly.io/${APP_NAME}:deploy-$(date +%s)"
docker build -t "$IMAGE_TAG" .
fly auth docker
docker push "$IMAGE_TAG"
fly deploy --image "$IMAGE_TAG" "$@"

echo "▸ Cleaning up vendored modules..."
rm -rf "$SCRIPT_DIR/_modules"

echo "✓ Deploy complete"
