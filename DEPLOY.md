# Deployment Guide

## Governor Service → Fly.io

```bash
cd governor-service
fly launch        # first time only
fly deploy
```

Set secrets on Fly:
```bash
fly secrets set GOVERNOR_JWT_SECRET="your-long-random-secret-here"
fly secrets set GOVERNOR_ADMIN_PASSWORD="your-secure-password"
fly secrets set GOVERNOR_DATABASE_URL="postgresql://..."
fly secrets set GOVERNOR_ENVIRONMENT="production"
```

> **Important**: The backend refuses to start in `production` if `GOVERNOR_JWT_SECRET` is still the default.

## Governor Service → Vultr (Standby)

An alternative / standby backend deployment using Docker Compose on a Vultr VPS.
Includes PostgreSQL 16 and Caddy for automatic HTTPS.

### Quick start

```bash
# 1. Provision a Vultr Cloud Compute instance (Ubuntu 24.04, ≥ 1 vCPU / 1 GB)
# 2. SSH in and run the bootstrap script:
curl -sSL https://raw.githubusercontent.com/othnielObasi/openclaw-runtime-governor/main/governor-service/vultr/bootstrap.sh | sudo bash

# 3. Switch to the deploy user and configure:
su - deploy
cd openclaw-runtime-governor/governor-service/vultr
cp .env.vultr.example .env
nano .env                              # fill in real secrets

# 4. (Optional) Set your domain for automatic HTTPS:
export DOMAIN=governor-standby.yourdomain.com

# 5. Start:
docker compose up -d

# 6. Verify:
curl http://localhost:8000/healthz     # → {"status":"ok"}
```

### Manual deploy (existing server)

```bash
git clone https://github.com/othnielObasi/openclaw-runtime-governor.git
cd openclaw-runtime-governor/governor-service/vultr
cp .env.vultr.example .env
nano .env                              # fill in real secrets
docker compose up -d
```

### Failover monitoring

A cron-based health checker watches the primary (Fly.io) and alerts when it's down:

```bash
# Install the cron job (runs every minute):
crontab -l 2>/dev/null | {
  cat
  echo "* * * * * /home/deploy/openclaw-runtime-governor/governor-service/vultr/failover-check.sh >> /var/log/governor-failover.log 2>&1"
} | crontab -

# Check logs:
tail -f /var/log/governor-failover.log
```

To switch traffic to Vultr during a Fly.io outage:
1. Update the Vercel env var: `NEXT_PUBLIC_GOVERNOR_API=https://governor-standby.yourdomain.com`
2. Or update your DNS CNAME to point the API hostname to the Vultr IP
3. Redeploy the dashboard on Vercel for the change to take effect

### Files

| File | Purpose |
|------|---------|
| `vultr/docker-compose.yml` | Governor + Postgres + Caddy stack |
| `vultr/.env.vultr.example` | Template environment variables |
| `vultr/Caddyfile` | Reverse proxy with auto-HTTPS |
| `vultr/bootstrap.sh` | First-boot provisioning script |
| `vultr/failover-check.sh` | Health-check & failover alerting |

## Dashboard → Vercel

```bash
cd dashboard
npm install
npm run build
```

Then import the repo into Vercel and set:

```
NEXT_PUBLIC_GOVERNOR_API=https://your-app.fly.dev
```

## Local Development

```bash
# Backend
cd governor-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Dashboard (new terminal)
cd dashboard
npm install
npm run dev
# open http://localhost:3000
```

---

## Environment Variables

### Governor Service

| Variable | Default | Description |
|----------|---------|-------------|
| `GOVERNOR_DATABASE_URL` | `sqlite:///./governor.db` | Database URL (`postgresql://` in production) |
| `GOVERNOR_JWT_SECRET` | *(must set in prod)* | JWT HS256 signing secret |
| `GOVERNOR_ENVIRONMENT` | `development` | `development` or `production` |
| `GOVERNOR_LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `GOVERNOR_LOG_SQL` | `false` | Print SQL to stdout |
| `GOVERNOR_ALLOW_CORS_ORIGINS` | `["*"]` | CORS allowed origins (JSON array) |
| `GOVERNOR_POLICIES_PATH` | `app/policies/base_policies.yml` | Base policy YAML path |
| `GOVERNOR_POLICY_CACHE_TTL_SECONDS` | `10` | Policy cache TTL |
| `GOVERNOR_JWT_EXPIRE_MINUTES` | `480` | JWT token expiry (8 hours) |
| `GOVERNOR_LOGIN_RATE_LIMIT` | `5/minute` | Login rate limit (slowapi format) |
| `GOVERNOR_EVALUATE_RATE_LIMIT` | `120/minute` | Evaluate rate limit |
| `GOVERNOR_ADMIN_USERNAME` | `admin` | Seed admin username |
| `GOVERNOR_ADMIN_PASSWORD` | `changeme` | Seed admin password |
| `GOVERNOR_SURGE_GOVERNANCE_FEE_ENABLED` | `false` | Enable $SURGE micro-fees |
| `GOVERNOR_SURGE_WALLET_ADDRESS` | *(empty)* | SURGE wallet address |

### Dashboard

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_GOVERNOR_API` | `http://localhost:8000` | Governor service URL |

### Autonomous Agent (`governor_agent.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `GOVERNOR_URL` | `http://localhost:8000` | Governor service URL |
| `GOVERNOR_API_KEY` | *(empty)* | API key (`ocg_…`) for `X-API-Key` auth |
| `GOVERNOR_AGENT_ID` | `governor-agent` | Agent identifier |
| `GOVERNOR_HEARTBEAT_SEC` | `30` | Check interval in seconds |
| `MOLTBOOK_API_KEY` | *(empty)* | Moltbook API key |
| `MOLTBOOK_SUBMOLT` | `lablab` | Target submolt |

### DeFi Demo Agent (`demo_agent.py`)

```bash
# Run against local server
python demo_agent.py

# Run against production
python demo_agent.py --url https://openclaw-governor.fly.dev

# Verbose output (full trace per evaluation)
python demo_agent.py --verbose

# Enable SURGE fee gating (shows wallet depletion)
python demo_agent.py --fee-gating
```

The demo agent authenticates via JWT (logs in as admin) and runs 5 phases of tool calls through the Governor. No additional environment variables are required — it accepts `--url` (default `http://localhost:8000`) and uses the default credentials or the credentials you provide at the prompt.

---

## Auth Setup

### Authentication Methods

The Governor supports two authentication methods that work on every protected endpoint:

| Method | Header | How to get |
|--------|--------|-----------|
| **JWT Bearer** | `Authorization: Bearer <token>` | `POST /auth/login` |
| **API Key** | `X-API-Key: ocg_<key>` | Dashboard → API Keys tab, or `POST /auth/me/rotate-key` |
| **Query Param** | `?token=<jwt>` | For SSE/EventSource (browser can't set headers) |

### Environment Variables for Auth

Add to governor-service (Fly secrets or `.env`):

```
GOVERNOR_JWT_SECRET=your-long-random-secret-here
GOVERNOR_ADMIN_USERNAME=admin
GOVERNOR_ADMIN_PASSWORD=your-secure-password
```

On first startup, a default admin account is created automatically from these env vars.

### Default Credentials (local dev only)

- Username: `admin`
- Password: `changeme`

**Change these before any deployment.**

### API Key Self-Service

Every authenticated user (any role) can rotate their own API key:

```bash
curl -X POST https://your-app.fly.dev/auth/me/rotate-key \
  -H "Authorization: Bearer $TOKEN"
```

The new key is returned in the response. Keys use the `ocg_` prefix and are ~43 characters long.

The **API Keys** tab in the dashboard provides a GUI for:
- Viewing your current key (masked by default)
- Revealing / hiding the key
- Copying to clipboard
- Regenerating the key
- Quick-start code samples for Python, TypeScript, Java, and cURL

### Role Summary

| Role | Tabs visible | Kill switch | Policy editor | User management | API Keys |
|------|-------------|-------------|---------------|-----------------|----------|
| admin | All | ✓ | ✓ | ✓ | ✓ (own) |
| operator | Dashboard, Tester, Simulator, Policies, Audit, SURGE, API Keys | ✗ | ✓ | ✗ | ✓ (own) |
| auditor | Dashboard, Audit, API Keys | ✗ | ✗ | ✗ | ✓ (own) |

### Adding operators (after deployment)

1. Login as admin
2. Go to User Management tab
3. Click **+ ADD OPERATOR**
4. Set role to `operator` or `auditor`

---

## Real-Time Monitoring (SSE)

The Governor streams every governance decision via Server-Sent Events at `GET /actions/stream`.

### Verify SSE after deployment

```bash
# Get a token
TOKEN=$(curl -s -X POST https://your-app.fly.dev/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-password"}' | jq -r .access_token)

# Open the stream (events appear as evaluations happen)
curl -N -H "Authorization: Bearer $TOKEN" https://your-app.fly.dev/actions/stream

# Check active subscribers
curl https://your-app.fly.dev/actions/stream/status
```

The dashboard connects to the SSE stream automatically when in Live Mode. A **LIVE** badge appears in the Audit Log tab when streaming is active.
