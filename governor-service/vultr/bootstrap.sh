#!/usr/bin/env bash
# --------------------------------------------------------------------------
# cloud-init / first-boot provisioning script for a Vultr VPS
#
# Tested on: Ubuntu 22.04 / 24.04 LTS
#
# Usage (run as root on a fresh Vultr instance):
#   curl -sSL https://raw.githubusercontent.com/othnielObasi/openclaw-runtime-governor/main/governor-service/vultr/bootstrap.sh | bash
#
# Or paste into Vultr's "Startup Script" field when creating the instance.
# --------------------------------------------------------------------------
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

echo "▸ Updating packages..."
apt-get update -qq && apt-get upgrade -y -qq

echo "▸ Installing Docker..."
apt-get install -y -qq ca-certificates curl gnupg lsb-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources-list.d/docker.list 2>/dev/null || \
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

echo "▸ Enabling Docker..."
systemctl enable --now docker

echo "▸ Creating deploy user..."
id -u deploy &>/dev/null || useradd -m -s /bin/bash -G docker deploy

echo "▸ Cloning repository..."
REPO_DIR=/home/deploy/openclaw-runtime-governor
if [ ! -d "$REPO_DIR" ]; then
  git clone https://github.com/othnielObasi/openclaw-runtime-governor.git "$REPO_DIR"
  chown -R deploy:deploy "$REPO_DIR"
fi

echo "▸ Setting up .env..."
VULTR_DIR="$REPO_DIR/governor-service/vultr"
if [ ! -f "$VULTR_DIR/.env" ]; then
  cp "$VULTR_DIR/.env.vultr.example" "$VULTR_DIR/.env"
  echo ""
  echo "⚠  IMPORTANT: Edit $VULTR_DIR/.env with real secrets before starting!"
  echo "   Then run:  cd $VULTR_DIR && docker compose up -d"
  echo ""
fi

echo "▸ Setting up UFW firewall..."
apt-get install -y -qq ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP  (Caddy redirects to HTTPS)
ufw allow 443/tcp  # HTTPS
ufw --force enable

echo "▸ Setting up unattended upgrades..."
apt-get install -y -qq unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

echo ""
echo "✅ Bootstrap complete."
echo "   Next steps:"
echo "   1. su - deploy"
echo "   2. cd openclaw-runtime-governor/governor-service/vultr"
echo "   3. nano .env            # fill in secrets"
echo "   4. export DOMAIN=governor.yourdomain.com   # or skip for HTTP-only"
echo "   5. docker compose up -d"
echo "   6. curl http://localhost:8000/healthz"
echo ""
