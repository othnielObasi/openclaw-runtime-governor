# 🛡️ NOVTIA OpenClaw Governor – Harmonized Build

Track: **Developer Infrastructure & Tools (Track 3)** | Prize: **Compliance-Ready Tokenization**

A **runtime governance, risk, and safety layer** that sits between OpenClaw agents
and real-world tools. Every tool call is intercepted, evaluated through a layered
policy + neuro-risk engine, and returned as an `allow / block / review` decision
with full audit trail and **SURGE token governance integration**.

## Architecture Overview

```
OpenClaw Agent
      │
      ▼
 openclaw-skills/governed-tools   ←── wraps every tool call
      │
      ▼
 governor-service  (FastAPI v0.3.0)
  ├── RBAC Auth (JWT + API Key)     ←── admin / operator / auditor roles
  ├── Rate Limiting                 ←── brute-force protection (slowapi)
  ├── Injection Firewall            ←── prompt-injection detection
  ├── Scope Enforcer                ←── allowed_tools scoping
  ├── Policy Engine                 ←── YAML + DB-backed rules (cached)
  ├── Neuro Risk Estimator          ←── heuristic risk scoring
  ├── Chain Analysis                ←── multi-step attack pattern detection
  ├── Kill Switch (DB-persisted)    ←── global halt control
  ├── SURGE Governance Layer        ←── token-staked policies + receipts
  └── Audit Logger                  ←── SQLite / Postgres via SQLAlchemy
      │
      ▼
 dashboard/  (Next.js)
  ├── Auth (Login / RBAC)           ←── JWT-based session management
  ├── ActionTester                  ←── test any tool call live
  ├── PolicyEditor                  ←── create/delete dynamic policies
  ├── AdminStatus                   ←── kill switch control
  ├── UserManagement                ←── admin user CRUD
  └── RecentActions                 ←── audit log feed
```

## Security Model

All API endpoints (except `/health`) require authentication via:
- **JWT Bearer token** — obtained from `/auth/login`
- **API Key header** — `X-API-Key: ocg_<key>`

Role-based access:
| Role | Evaluate | View Logs | Policies | Kill Switch | Users |
|------|----------|-----------|----------|-------------|-------|
| `admin` | ✅ | ✅ | ✅ CRUD | ✅ | ✅ CRUD |
| `operator` | ✅ | ✅ | ✅ CRUD | ❌ | ❌ |
| `auditor` | ❌ | ✅ | ✅ Read | ❌ | ❌ |

Production safeguards:
- JWT secret **must** be changed from default in non-development environments (startup fails otherwise)
- Admin seed password **refused** in non-development environments unless overridden
- Login endpoint rate-limited (5/minute per IP)
- Kill switch state persisted to database (survives restarts)
- Policy engine cached with configurable TTL (default 10s)

## SURGE Token Governance

The governor integrates with the SURGE token economy:

| Feature | Description |
|---------|-------------|
| **Governance Receipts** | Every evaluation produces a SHA-256 signed receipt for on-chain attestation |
| **Policy Staking** | Operators stake $SURGE on policies to signal confidence |
| **Fee Gating** | Optional micro-fee (0.001 $SURGE) per evaluation for premium governance |
| **Token-Aware Policies** | Built-in rules for surge_launch, surge_trade, surge_transfer operations |

## Components

| Directory | Purpose |
|-----------|---------|
| `governor-service/` | FastAPI backend – policies, risk, auth, SURGE, DB, admin |
| `dashboard/` | Next.js control panel |
| `openclaw-skills/` | OpenClaw skills that wire agents to the governor |
| `docs/` | Architecture & overview notes |

## Quick Start

### Backend

```bash
cd governor-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Default admin: `admin@openclaw.io` / `changeme` (dev mode only).

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GOVERNOR_DATABASE_URL` | `sqlite:///./governor.db` | DB connection string |
| `GOVERNOR_JWT_SECRET` | *(must set in production)* | JWT signing secret |
| `GOVERNOR_ENVIRONMENT` | `development` | `development` or `production` |
| `GOVERNOR_ADMIN_EMAIL` | `admin@openclaw.io` | Seed admin email |
| `GOVERNOR_ADMIN_PASSWORD` | `changeme` | Seed admin password |
| `GOVERNOR_LOG_SQL` | `false` | Echo SQL queries |
| `GOVERNOR_ALLOW_CORS_ORIGINS` | `["*"]` | CORS allowed origins |
| `POLICIES_PATH` | `app/policies/base_policies.yml` | Base policy file |
| `GOVERNOR_SURGE_GOVERNANCE_FEE_ENABLED` | `false` | Enable $SURGE micro-fees |
| `GOVERNOR_SURGE_WALLET_ADDRESS` | *(empty)* | SURGE wallet for fee collection |

### Dashboard

```bash
cd dashboard
npm install
npm run dev
```

Set `NEXT_PUBLIC_GOVERNOR_API` to your governor URL (default: `http://localhost:8000`).

## Deployment

See `DEPLOY.md` for Fly.io (backend) + Vercel (dashboard) instructions.

## API Endpoints

### Auth
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/login` | None | Login (rate-limited: 5/min) |
| `GET` | `/auth/me` | Any | Current user info |
| `GET` | `/auth/users` | Admin | List all users |
| `POST` | `/auth/users` | Admin | Create user |
| `PATCH` | `/auth/users/{id}` | Admin | Update user |
| `DELETE` | `/auth/users/{id}` | Admin | Deactivate user |

### Governance
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/actions/evaluate` | Operator+ | Evaluate a tool call |
| `GET` | `/actions` | Any | List recent action logs |
| `GET` | `/policies` | Any | List all policies |
| `POST` | `/policies` | Operator+ | Create a dynamic policy |
| `DELETE` | `/policies/{id}` | Operator+ | Delete a policy |

### Admin
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/admin/status` | Any | Kill switch status |
| `POST` | `/admin/kill` | Admin | Enable kill switch |
| `POST` | `/admin/resume` | Admin | Disable kill switch |
| `GET` | `/summary/moltbook` | Any | Governance summary |

### SURGE Governance
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
