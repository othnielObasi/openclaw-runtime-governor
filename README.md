# OpenClaw Runtime Governor

> Runtime governance, risk, and safety layer for autonomous AI agents.

**Track 3 – Developer Infrastructure & Tools** · **SURGE × OpenClaw Hackathon** · **Sovereign AI Lab**

[![CI - Dashboard](https://github.com/othnielObasi/openclaw-runtime-governor/actions/workflows/ci.yml/badge.svg)](https://github.com/othnielObasi/openclaw-runtime-governor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## What It Does

Every tool call made by an OpenClaw agent is intercepted, evaluated through a **5-layer governance pipeline**, and returned as an **allow / block / review** decision — with full audit trail and SURGE token governance receipts.

```
Agent calls tool
       │
       ▼
 ┌─────────────────────────────────────────────────────┐
 │              Governor Service (FastAPI)              │
 │                                                     │
 │  1. Kill Switch ───► instant halt if engaged        │
 │  2. Injection Firewall ───► prompt-injection scan   │
 │  3. Scope Enforcer ───► allowed_tools check         │
 │  4. Policy Engine ───► YAML + dynamic DB rules      │
 │  5. Neuro Risk Estimator + Chain Analysis           │
 │                                                     │
 │  ───► ActionDecision { allow | block | review }     │
 │  ───► Execution Trace (per-layer timing & detail)   │
 │  ───► SURGE Governance Receipt (SHA-256)            │
 └─────────────────────────────────────────────────────┘
       │
       ▼
 Dashboard (Next.js) ─── live monitoring & control
```

The pipeline **short-circuits** on the first block — kill switch fires before anything else, injection firewall before policy evaluation, and so on. Every evaluation produces a detailed execution trace showing exactly which layers fired and why.

---

## Components

| Directory | What | Version |
|-----------|------|---------|
| [`governor-service/`](governor-service/) | FastAPI backend — evaluation pipeline, auth, SURGE, audit logging | 0.3.0 |
| [`dashboard/`](dashboard/) | Next.js control panel — live monitoring, policy editor, admin controls | 0.2.0 |
| [`openclaw-skills/governed-tools/`](openclaw-skills/governed-tools/) | Python + JS clients that wire agents to the governor | 0.2.0 / 0.1.0 |
| [`openclaw-skills/moltbook-reporter/`](openclaw-skills/moltbook-reporter/) | Automated Moltbook status reporter | 0.3.0 |
| [`governor_agent.py`](governor_agent.py) | Autonomous governance agent (observe → reason → act loop) | — |
| [`docs/`](docs/) | Architecture docs & diagrams | — |

---

## Quick Start

### 1. Backend

```bash
cd governor-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Default dev credentials: `admin@openclaw.io` / `changeme`

The API is now live at `http://localhost:8000`. Check health:

```bash
curl http://localhost:8000/health
```

### 2. Dashboard

```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:3000`. The landing page offers **Demo Mode** (self-contained, no backend) or **Live Mode** (connects to governor-service).

Set `NEXT_PUBLIC_GOVERNOR_API` to point at your backend (default: `http://localhost:8000`).

### 3. Test an Evaluation

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@openclaw.io","password":"changeme"}' | jq -r .access_token)

# Evaluate a tool call
curl -X POST http://localhost:8000/actions/evaluate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "shell",
    "args": {"command": "ls -la"},
    "context": {"agent_id": "test-agent"}
  }'
```

Response includes the decision, risk score, explanation, matched policy IDs, and full execution trace.

---

## Governance Pipeline

### Layer 1 — Kill Switch
Global emergency halt. When engaged, **every** evaluation returns `block` immediately. Persisted to database (survives restarts). Toggled via API or dashboard by admins only.

### Layer 2 — Injection Firewall
Scans the entire payload (tool name, args, context) against 11 known prompt-injection patterns: jailbreak, override, ignore previous, disable safety, etc. Triggers block with risk score 95.

### Layer 3 — Scope Enforcer
If the calling context includes `allowed_tools`, the requested tool must be in that list. Blocks out-of-scope tools with risk score 90.

### Layer 4 — Policy Engine
Matches against two policy sources:

- **Base policies** — 10 YAML rules shipped with the service ([`base_policies.yml`](governor-service/app/policies/base_policies.yml))
- **Dynamic policies** — created at runtime via API, stored in the database

Policies match on tool name, URL regex, and args regex. Each carries a severity (`low` / `medium` / `high` / `critical`) and action (`allow` / `block` / `review`).

### Layer 5 — Neuro Risk Estimator + Chain Analysis
Heuristic risk scorer (0–100) based on tool type, sensitive keywords, and bulk-recipient detection. **Chain analysis** examines session history across a 60-minute window to detect 6 multi-step attack patterns:

| Pattern | Risk Boost | Description |
|---------|------------|-------------|
| `browse-then-exfil` | +35 | Browse/read followed by HTTP send |
| `read-write-exec` | +45 | File read → write → shell execution |
| `repeated-scope-probing` | +60 | Multiple out-of-scope attempts |
| `credential-then-http` | +55 | Credential access then HTTP request |
| `rapid-tool-switching` | +30 | 5+ distinct tools in quick succession |
| `block-bypass-retry` | +40 | Retrying after being blocked |

If combined risk score reaches 80+, the decision is promoted to `review`.

---

## SURGE Token Governance

Integration with the SURGE token economy:

| Feature | Description |
|---------|-------------|
| **Governance Receipts** | Every evaluation produces a SHA-256 signed receipt suitable for on-chain attestation |
| **Policy Staking** | Operators stake $SURGE on policies to signal confidence |
| **Fee Gating** | Optional micro-fee (0.001 $SURGE) per evaluation for premium governance tiers |
| **Token-Aware Policies** | Built-in rules for `surge_launch`, `surge_trade`, `surge_transfer`, `surge_ownership_transfer` |

---

## Security Model

### Authentication
All endpoints (except `/health` and `/`) require authentication via:
- **JWT Bearer token** — obtained from `POST /auth/login`
- **API Key** — `X-API-Key: ocg_<key>` header

Both methods are supported simultaneously on every protected endpoint.

### Role-Based Access Control

| Role | Evaluate | View Logs | Policies | Kill Switch | Users |
|------|----------|-----------|----------|-------------|-------|
| `admin` | ✅ | ✅ | ✅ CRUD | ✅ | ✅ CRUD |
| `operator` | ✅ | ✅ | ✅ CRUD | ❌ | ❌ |
| `auditor` | ❌ | ✅ | Read only | ❌ | ❌ |

### Production Safeguards
- JWT secret **must** be changed from default — startup fails otherwise in non-dev environments
- Admin seed password refused in production unless explicitly overridden
- Login rate-limited: 5 requests/min per IP
- Evaluate rate-limited: 120 requests/min per IP
- Kill switch state persisted to database
- Policy engine cached with configurable TTL (default 10s)

---

## API Reference

### Auth
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/login` | None | Login (rate-limited 5/min) |
| `GET` | `/auth/me` | Any | Current user info |
| `GET` | `/auth/users` | Admin | List all users |
| `POST` | `/auth/users` | Admin | Create user |
| `PATCH` | `/auth/users/{id}` | Admin | Update user |
| `DELETE` | `/auth/users/{id}` | Admin | Deactivate user (soft delete) |
| `POST` | `/auth/users/{id}/rotate-key` | Admin | Rotate API key |

### Governance
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/actions/evaluate` | Operator+ | Evaluate a tool call |
| `GET` | `/actions` | Any | List action logs (filterable) |
| `GET` | `/policies` | Any | List all policies |
| `POST` | `/policies` | Operator+ | Create dynamic policy |
| `DELETE` | `/policies/{id}` | Operator+ | Delete a policy |

### Admin
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/admin/status` | Any | Kill switch status |
| `POST` | `/admin/kill` | Admin | Engage kill switch |
| `POST` | `/admin/resume` | Admin | Release kill switch |
| `GET` | `/summary/moltbook` | Any | Governance summary with narrative |

### SURGE
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/surge/status` | Any | SURGE integration status |
| `GET` | `/surge/receipts` | Any | List governance receipts |
| `GET` | `/surge/receipts/{id}` | Any | Get specific receipt |
| `POST` | `/surge/policies/stake` | Operator+ | Stake $SURGE on a policy |
| `GET` | `/surge/policies/staked` | Any | List staked policies |
| `DELETE` | `/surge/policies/stake/{id}` | Operator+ | Unstake a policy |

### Meta
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | None | Service info |
| `GET` | `/health` | None | Health check |

---

## Client SDKs

### Python

```python
from governor_client import evaluate_action, governed_call

# Direct evaluation
decision = evaluate_action("shell", {"command": "rm -rf /"})
# decision.decision == "block"

# Convenience wrapper — raises GovernorBlockedError on block
result = governed_call("file_read", {"path": "/etc/passwd"}, your_tool_fn)
```

### JavaScript / TypeScript

```typescript
import { GovernorClient } from "@openclaw/ocg-client";

const client = new GovernorClient({
  url: "https://your-governor.fly.dev",
  apiKey: "ocg_your_key_here",
});

const result = await client.request("/actions/evaluate", {
  method: "POST",
  body: { tool: "shell", args: { command: "ls" } },
});
```

### Proxy Servers
Both Python (FastAPI) and JavaScript (Express) proxy servers are included for environments where agents can't reach the governor directly:
- **Python proxy**: [`openclaw-skills/governed-tools/python-proxy/`](openclaw-skills/governed-tools/python-proxy/)
- **JS proxy**: [`openclaw-skills/governed-tools/js-client/examples/`](openclaw-skills/governed-tools/js-client/examples/)

---

## Autonomous Governance Agent

[`governor_agent.py`](governor_agent.py) runs an autonomous **observe → reason → act → update memory** loop:

- Monitors governor health and action statistics on a configurable heartbeat
- Maintains persistent in-process memory of threat trends
- Auto-engages kill switch after 5+ high-risk actions in one window
- Auto-releases kill switch when threat levels subside
- Alerts on anomalies: >40% block rate, average risk >75
- Posts status updates to Moltbook

```bash
# Full autonomous mode
python governor_agent.py

# Single observation cycle (dry run)
python governor_agent.py --demo

# Without Moltbook posting
python governor_agent.py --no-moltbook
```

---

## Deployment

| Component | Platform | Config |
|-----------|----------|--------|
| Governor Service | Fly.io | [`fly.toml`](governor-service/fly.toml), [`Dockerfile`](governor-service/Dockerfile) |
| Dashboard | Vercel | [`vercel.json`](dashboard/vercel.json) |

See [`DEPLOY.md`](DEPLOY.md) for full deployment instructions and [`PUBLISHING.md`](PUBLISHING.md) for PyPI/npm package publishing workflows.

---

## Testing

```bash
# Backend — 22 test cases
cd governor-service
pytest tests/ -v

# JS client
cd openclaw-skills/governed-tools/js-client
node tests/test_client.js
node tests/test_client_headers.js

# Python proxy
cd openclaw-skills/governed-tools/python-proxy
pytest tests/ -v
```

Tests cover all 5 pipeline layers, chain analysis patterns, SURGE governance receipts, policy cache invalidation, and client SDK behavior.

---

## Environment Variables

<details>
<summary><strong>Governor Service</strong> (14 variables)</summary>

| Variable | Default | Description |
|----------|---------|-------------|
| `GOVERNOR_DATABASE_URL` | `sqlite:///./governor.db` | Database connection string |
| `GOVERNOR_JWT_SECRET` | *(must set in prod)* | JWT signing secret |
| `GOVERNOR_ENVIRONMENT` | `development` | `development` or `production` |
| `GOVERNOR_LOG_LEVEL` | `info` | Logging level |
| `GOVERNOR_LOG_SQL` | `false` | Echo SQL queries to stdout |
| `GOVERNOR_ALLOW_CORS_ORIGINS` | `["*"]` | CORS allowed origins (JSON) |
| `GOVERNOR_POLICIES_PATH` | `app/policies/base_policies.yml` | Base policy YAML path |
| `GOVERNOR_POLICY_CACHE_TTL_SECONDS` | `10` | Policy cache TTL |
| `GOVERNOR_JWT_EXPIRE_MINUTES` | `480` | JWT token expiry (8 hours) |
| `GOVERNOR_LOGIN_RATE_LIMIT` | `5/minute` | Login rate limit |
| `GOVERNOR_EVALUATE_RATE_LIMIT` | `120/minute` | Evaluate rate limit |
| `GOVERNOR_ADMIN_EMAIL` | `admin@openclaw.io` | Seed admin email |
| `GOVERNOR_ADMIN_PASSWORD` | `changeme` | Seed admin password |
| `GOVERNOR_SURGE_GOVERNANCE_FEE_ENABLED` | `false` | Enable $SURGE micro-fees |
| `GOVERNOR_SURGE_WALLET_ADDRESS` | *(empty)* | SURGE wallet address |

</details>

<details>
<summary><strong>Dashboard</strong> (1 variable)</summary>

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_GOVERNOR_API` | Governor service URL (default: `http://localhost:8000`) |

</details>

<details>
<summary><strong>Autonomous Agent</strong> (5 variables)</summary>

| Variable | Description |
|----------|-------------|
| `GOVERNOR_URL` | Governor service URL |
| `GOVERNOR_AGENT_ID` | Agent identifier |
| `GOVERNOR_HEARTBEAT_SEC` | Check interval in seconds (default: 30) |
| `MOLTBOOK_API_KEY` | Moltbook API key |
| `MOLTBOOK_SUBMOLT` | Target submolt (default: `lablab`) |

</details>

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Pydantic 2.8 |
| Auth | bcrypt, python-jose (JWT HS256), slowapi |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Dashboard | Next.js 14.2, React 18.3, TypeScript, Axios |
| Deployment | Fly.io (backend), Vercel (dashboard) |
| CI/CD | GitHub Actions |

---

## Project Structure

```
openclaw-runtime-governor/
├── governor-service/           # FastAPI backend
│   ├── app/
│   │   ├── main.py             # App init, CORS, route registration
│   │   ├── config.py           # Pydantic settings (all env vars)
│   │   ├── database.py         # SQLAlchemy engine & session
│   │   ├── models.py           # ActionLog, PolicyModel, User, GovernorState
│   │   ├── schemas.py          # Pydantic request/response models
│   │   ├── state.py            # Kill switch (DB-persisted, thread-safe)
│   │   ├── session_store.py    # Session history for chain analysis
│   │   ├── chain_analysis.py   # Multi-step attack pattern detection
│   │   ├── rate_limit.py       # slowapi rate limiter
│   │   ├── api/                # Route handlers
│   │   ├── auth/               # JWT + API key auth, RBAC, user seed
│   │   ├── neuro/              # Heuristic risk estimator
│   │   ├── policies/           # Engine, YAML loader, base rules
│   │   └── telemetry/          # Audit logger
│   └── tests/                  # pytest test suite
├── dashboard/                  # Next.js control panel
│   ├── app/                    # Pages (landing, layout)
│   └── components/             # Dashboard, login, editors, panels
├── openclaw-skills/
│   ├── governed-tools/         # Python + JS client SDKs, proxy servers
│   └── moltbook-reporter/      # Automated Moltbook status poster
├── governor_agent.py           # Autonomous governance agent
├── GovernorComplete.jsx        # Standalone preview artifact
├── DEPLOY.md                   # Deployment guide
├── PUBLISHING.md               # Package publishing guide
├── DEVELOPER.md                # Developer guide
├── DISCLOSURES.md              # Hackathon compliance
└── docs/ARCHITECTURE.md        # Architecture deep-dive
```

---

## License

[MIT](LICENSE) — Copyright © 2026 Sovereign AI Lab

---

**Sovereign AI Lab** · SURGE × OpenClaw Hackathon · Track 3: Developer Infrastructure & Tools
