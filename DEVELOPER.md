# Developer Guide

Complete guide for contributing to the OpenClaw Runtime Governor.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Governor service backend |
| Node.js | 20+ | Dashboard frontend |
| npm | 10+ | Dashboard package management |
| Git | 2.40+ | Version control |
| Docker | 24+ | *(optional)* Containerised deployment |

---

## Repository Layout

```
openclaw-runtime-governor/
│
├── governor-service/        # Python/FastAPI backend (the core)
│   ├── app/
│   │   ├── main.py          # FastAPI app, CORS, router registration
│   │   ├── config.py        # All env vars via pydantic-settings
│   │   ├── database.py      # SQLAlchemy engine, session factory
│   │   ├── models.py        # ORM: ActionLog, PolicyModel, User, GovernorState
│   │   ├── schemas.py       # Pydantic v2 request/response schemas
│   │   ├── state.py         # Kill switch — DB-persisted, thread-safe
│   │   ├── session_store.py # Session history reconstruction for chain analysis
│   │   ├── chain_analysis.py# Multi-step attack pattern detector
│   │   ├── rate_limit.py    # slowapi rate limiter singleton
│   │   │
│   │   ├── api/
│   │   │   ├── routes_actions.py   # POST /actions/evaluate, GET /actions
│   │   │   ├── routes_policies.py  # CRUD /policies
│   │   │   ├── routes_admin.py     # Kill switch control
│   │   │   ├── routes_summary.py   # GET /summary/moltbook
│   │   │   └── routes_surge.py     # SURGE receipts, staking
│   │   │
│   │   ├── auth/
│   │   │   ├── core.py         # bcrypt hashing, JWT encode/decode, API key gen
│   │   │   ├── dependencies.py # FastAPI deps: JWT/API key extraction, role guards
│   │   │   ├── routes_auth.py  # Login, user CRUD, key rotation
│   │   │   └── seed.py         # Default admin seeding on startup
│   │   │
│   │   ├── neuro/
│   │   │   └── risk_estimator.py  # Heuristic risk scoring (0-100)
│   │   │
│   │   ├── policies/
│   │   │   ├── engine.py       # 5-layer evaluation pipeline
│   │   │   ├── loader.py       # Policy dataclass, YAML + DB loading, cache
│   │   │   └── base_policies.yml  # 10 base governance rules
│   │   │
│   │   └── telemetry/
│   │       └── logger.py       # Writes action logs to DB
│   │
│   ├── tests/
│   │   └── test_governor.py    # 22 test cases
│   ├── conftest.py             # Session-scoped DB fixtures
│   ├── requirements.txt
│   ├── Dockerfile
│   └── fly.toml
│
├── dashboard/               # Next.js 14 frontend
│   ├── app/
│   │   ├── layout.tsx       # Root layout, fonts, AuthProvider
│   │   └── page.tsx         # Landing page with Demo/Live selector
│   ├── components/
│   │   ├── ApiClient.ts          # Axios instance
│   │   ├── AuthContext.tsx        # Auth React context
│   │   ├── GovernorLogin.tsx      # Login page (TypeScript)
│   │   ├── GovernorLogin.jsx      # Login page (JSX variant)
│   │   ├── GovernorDashboard.jsx  # Live dashboard (3453 lines)
│   │   ├── Governordashboard-demo.jsx  # Demo dashboard (4061 lines)
│   │   ├── ActionTester.tsx       # Tool evaluation form
│   │   ├── AdminStatus.tsx        # Kill switch toggle
│   │   ├── PolicyEditor.tsx       # Policy CRUD
│   │   ├── RecentActions.tsx      # Audit log feed
│   │   ├── SummaryPanel.tsx       # Stats overview
│   │   └── UserManagement.tsx     # User admin
│   ├── package.json
│   ├── tsconfig.json
│   └── vercel.json
│
├── openclaw-skills/
│   ├── governed-tools/
│   │   ├── governor_client.py             # Python SDK
│   │   ├── skill.toml
│   │   ├── js-client/                     # @openclaw/ocg-client (npm)
│   │   │   ├── src/index.ts
│   │   │   ├── examples/proxy-server.js
│   │   │   └── tests/
│   │   └── python-proxy/                  # FastAPI proxy server
│   │       ├── proxy_server.py
│   │       └── tests/
│   └── moltbook-reporter/
│       ├── reporter.py                    # Main reporter
│       ├── moltbook_lablab_poster.py      # Lablab poster (cron)
│       └── skill.toml
│
├── governor_agent.py        # Autonomous governance agent
├── GovernorComplete.jsx     # Standalone artifact (login + full dashboard)
├── DEPLOY.md
├── PUBLISHING.md
├── DISCLOSURES.md
└── docs/ARCHITECTURE.md
```

---

## Local Development Setup

### Backend

```bash
cd governor-service

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --reload --port 8000
```

On first startup, the server:
1. Creates all database tables (`SQLite` by default at `./governor.db`)
2. Seeds a default admin account: `admin` / `changeme`
3. Loads base policies from `app/policies/base_policies.yml`

Verify it's running:
```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### Dashboard

```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:3000`. The landing page shows two options:
- **Demo Mode** — fully self-contained, no backend needed
- **Live Mode** — connects to the governor service

To point Live Mode at your local backend:
```bash
NEXT_PUBLIC_GOVERNOR_API=http://localhost:8000 npm run dev
```

### Running Both Together

Open two terminals:

```bash
# Terminal 1 — Backend
cd governor-service
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Dashboard
cd dashboard
NEXT_PUBLIC_GOVERNOR_API=http://localhost:8000 npm run dev
```

---

## Core Concepts

### Evaluation Pipeline

The heart of the system is `governor-service/app/policies/engine.py`. When a tool call arrives at `POST /actions/evaluate`, it passes through 5 layers in order:

```
Kill Switch → Injection Firewall → Scope Enforcer → Policy Engine → Neuro + Chain
```

Each layer can:
- **Block** — stop evaluation, return block immediately
- **Review** — flag for human review (continues evaluation)
- **Pass** — no opinion, continue to next layer

Every layer emits a `TraceStep` with timing, risk contribution, and detail text. The full trace is returned in the response.

**Key file**: `governor-service/app/policies/engine.py` — the `evaluate_action()` function.

### Policy System

Policies come from two sources:

1. **Base policies** (`app/policies/base_policies.yml`) — version-controlled, loaded on startup
2. **Dynamic policies** — created via API, stored in `policy_models` DB table

Both share the same `Policy` dataclass (defined in `loader.py`):

```python
@dataclass
class Policy:
    policy_id: str
    description: str
    tool: str           # Tool name to match (supports *)
    severity: str       # low | medium | high | critical
    action: str         # allow | block | review
    url_regex: str      # Optional regex for http_request URLs
    args_regex: str     # Optional regex matched against all arg values
```

The `matches()` method checks tool name, URL regex, and args regex against the incoming request.

**Cache**: Policies are cached with a configurable TTL (default 10s). Call `invalidate_policy_cache()` to force reload.

### Authentication

Dual auth via FastAPI dependency injection (`auth/dependencies.py`):

1. **JWT Bearer** — `Authorization: Bearer <token>` from `/auth/login`
2. **API Key** — `X-API-Key: ocg_<32-byte-key>`

Role guards are composable FastAPI dependencies:
```python
@router.post("/admin/kill")
async def kill_switch(user: User = Depends(require_admin)):
    ...
```

### Kill Switch

The kill switch is a boolean persisted as a key-value pair in the `governor_state` table:

- **Engaged**: Every evaluation immediately returns `block` with risk 100
- **Released**: Normal pipeline evaluation
- Thread-safe via `threading.Lock`
- Cached in-memory, falls back to DB on error
- Survives server restarts

### Chain Analysis

Session-based multi-step attack detection (`chain_analysis.py`):

- Reconstructs session history from `action_logs` table (60-minute window, max 50 entries)
- Scoped by `agent_id` and optional `session_id`
- Evaluates 6 known attack patterns in descending risk-boost order
- Returns first matching pattern with risk boost

### SURGE Integration

SURGE governance features are in `api/routes_surge.py`:

- **Receipts**: SHA-256 digest of `(action_log_id, tool, decision, timestamp)` — immutable attestation
- **Staking**: Operators attach $SURGE amounts to policy IDs
- **Fee gating**: When enabled, evaluations cost 0.001 $SURGE

---

## Database

### Models (4 tables)

| Table | Model | Purpose |
|-------|-------|---------|
| `action_logs` | `ActionLog` | Audit trail of every evaluation |
| `policy_models` | `PolicyModel` | Dynamic policies created via API |
| `users` | `User` | RBAC accounts (admin/operator/auditor) |
| `governor_state` | `GovernorState` | Key-value store (kill switch state) |

### Connections

- **Development**: SQLite at `./governor.db` (default)
- **Production**: PostgreSQL via `GOVERNOR_DATABASE_URL`
- **Engine**: SQLAlchemy 2.0 with `Mapped[]` / `mapped_column()` style
- **Sessions**: Context manager `db_session()` with auto-commit/rollback

### Migrations

There is currently no migration tool (Alembic etc.). Tables are created via `Base.metadata.create_all()` on startup. For schema changes in development, delete `governor.db` and restart. For production, manual SQL or Alembic integration is recommended.

---

## Testing

### Backend Tests

```bash
cd governor-service
pytest tests/ -v
```

The test suite (`tests/test_governor.py`) covers:

| Category | Tests |
|----------|-------|
| Basic decisions | Valid decision types, risk scoring |
| Injection firewall | Jailbreak, override, disable-safety detection |
| Scope enforcement | Out-of-scope block, in-scope allow, no-constraint pass |
| Kill switch | Global block behavior |
| Neuro estimator | Credential keywords, bulk recipients, tool type risk |
| Execution trace | Trace presence, short-circuit on kill |
| Chain analysis | No-history baseline, browse-then-exfil, read-write-exec, scope probing |
| Policy cache | Invalidation behavior |
| SURGE | Token launch review, ownership transfer block, receipt SHA-256 |

**Fixtures** (`conftest.py`): Session-scoped autouse fixture creates all tables before the suite and drops them after.

### Client Tests

```bash
# JavaScript client
cd openclaw-skills/governed-tools/js-client
node tests/test_client.js
node tests/test_client_headers.js

# Python proxy
cd openclaw-skills/governed-tools/python-proxy
pytest tests/ -v
```

### Writing New Tests

Tests use `evaluate_action()` directly from `policies.engine` — no HTTP layer. To add a test:

```python
# governor-service/tests/test_governor.py

def test_my_new_scenario():
    inp = ActionInput(
        tool="shell",
        args={"command": "my-command"},
        context={"agent_id": "test"}
    )
    result = evaluate_action(inp)
    assert result.decision == "allow"
    assert result.risk_score < 50
```

---

## Adding a New Policy

### Via YAML (base policy)

Edit `governor-service/app/policies/base_policies.yml`:

```yaml
- policy_id: my-custom-rule
  description: "Block dangerous custom tool"
  tool: "my_dangerous_tool"
  severity: critical
  action: block
```

Restart the server to load changes.

### Via API (dynamic policy)

```bash
curl -X POST http://localhost:8000/policies \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "block-external-uploads",
    "description": "Block HTTP uploads to external domains",
    "tool": "http_request",
    "severity": "high",
    "action": "block",
    "url_regex": "^https?://(?!internal\\.company\\.com)"
  }'
```

Dynamic policies are stored in the DB and take effect immediately (after cache TTL expires, default 10s).

---

## Adding a New Pipeline Layer

To add a new evaluation layer:

1. Create or modify the layer logic (e.g., a new file in `app/`)
2. Edit `app/policies/engine.py` — add your layer to the `evaluate_action()` function
3. Emit a `TraceStep` for observability:

```python
trace.append(TraceStep(
    layer=6,
    name="my_new_layer",
    key="my-check",
    outcome="pass",            # pass | block | review
    risk_contribution=0,
    matched_ids=[],
    detail="No issues found",
    duration_ms=round(elapsed * 1000, 2),
))
```

4. Add tests in `tests/test_governor.py`

---

## Adding a Dashboard Component

Dashboard components use **inline styles** (no CSS framework). The design system is defined in the dashboard JSX files:

### Design Tokens

```javascript
// Colors (navy depth palette)
const C = {
  bg0: "#080e1a",     // deepest background
  bg1: "#0f1b2d",     // card background
  bg2: "#1d3452",     // hover / active
  line: "#1d3452",    // borders
  p1: "#e2e8f0",      // primary text
  p2: "#8fa3bf",      // secondary text
  p3: "#4a6785",      // muted text
  accent: "#e8412a",  // OpenClaw red
  green: "#22c55e",   // allow
  amber: "#f59e0b",   // review
  red: "#ef4444",     // block
};

// Fonts
const mono = "'IBM Plex Mono', monospace";   // data, labels, code
const sans = "'DM Sans', sans-serif";        // body text, descriptions
```

### Component Pattern

1. Create a new `.tsx` file in `dashboard/components/`
2. Use the `ApiClient` for backend calls:
```typescript
import api from "./ApiClient";
const { data } = await api.get("/your-endpoint");
```
3. Access auth context:
```typescript
import { useAuth } from "./AuthContext";
const { token, role } = useAuth();
```

---

## CI/CD

### GitHub Actions Workflows

| Workflow | File | Trigger | What It Does |
|----------|------|---------|--------------|
| Dashboard Build | `.github/workflows/ci.yml` | Push/PR touching `dashboard/**` | Node.js 20, `npm ci`, `npm run build` |
| Moltbook Poster | `.github/workflows/moltbook-poster.yml` | Cron (every 30 min) + manual | Runs `moltbook_lablab_poster.py` |

### Deployment

| Component | Platform | How |
|-----------|----------|-----|
| Backend | Fly.io | `fly deploy` from `governor-service/` |
| Dashboard | Vercel | Auto-deploys on push to `main` |

See [`DEPLOY.md`](DEPLOY.md) for detailed deployment steps.

### Publishing Packages

| Package | Registry | Workflow |
|---------|----------|----------|
| `governed-tools` | PyPI | `.github/workflows/publish-python.yml` |
| `@openclaw/ocg-client` | npm | `.github/workflows/publish-js.yml` |

See [`PUBLISHING.md`](PUBLISHING.md) for secrets setup and manual publish instructions.

---

## Environment Variables Reference

### Governor Service

| Variable | Default | Notes |
|----------|---------|-------|
| `GOVERNOR_DATABASE_URL` | `sqlite:///./governor.db` | Use `postgresql://` in production |
| `GOVERNOR_JWT_SECRET` | `change-me-in-...` | **Must change in production** — startup refuses default |
| `GOVERNOR_ENVIRONMENT` | `development` | Set to `production` for prod safeguards |
| `GOVERNOR_LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `GOVERNOR_LOG_SQL` | `false` | Set `true` to see SQL in stdout |
| `GOVERNOR_ALLOW_CORS_ORIGINS` | `["*"]` | JSON array of allowed origins |
| `GOVERNOR_POLICIES_PATH` | `app/policies/base_policies.yml` | Path to base policy YAML |
| `GOVERNOR_POLICY_CACHE_TTL_SECONDS` | `10` | Set to `0` to disable caching |
| `GOVERNOR_JWT_EXPIRE_MINUTES` | `480` | 8 hours default |
| `GOVERNOR_LOGIN_RATE_LIMIT` | `5/minute` | slowapi format |
| `GOVERNOR_EVALUATE_RATE_LIMIT` | `120/minute` | slowapi format |
| `GOVERNOR_ADMIN_USERNAME` | `admin` | First admin account username |
| `GOVERNOR_ADMIN_PASSWORD` | `changeme` | First admin account password |
| `GOVERNOR_SURGE_GOVERNANCE_FEE_ENABLED` | `false` | Enable $SURGE fee per eval |
| `GOVERNOR_SURGE_WALLET_ADDRESS` | *(empty)* | SURGE wallet for fee collection |

### Dashboard

| Variable | Default | Notes |
|----------|---------|-------|
| `NEXT_PUBLIC_GOVERNOR_API` | `http://localhost:8000` | Points dashboard at backend |

---

## Troubleshooting

### "JWT secret must be changed from default"
Set `GOVERNOR_JWT_SECRET` to a long random string. This error only occurs when `GOVERNOR_ENVIRONMENT=production`.

### Dashboard shows "NEXT_PUBLIC_GOVERNOR_API is not set"
This is a build-time warning. Set the env var before building:
```bash
NEXT_PUBLIC_GOVERNOR_API=https://your-api.fly.dev npm run build
```

### "ModuleNotFoundError: No module named 'requests'"
Install dependencies: `pip install -r requirements.txt`. The moltbook-reporter has its own `requirements.txt`.

### Policy changes not taking effect
The policy engine caches policies with a 10-second TTL. Wait 10 seconds or restart the server. You can also set `GOVERNOR_POLICY_CACHE_TTL_SECONDS=0` for instant updates during development.

### Kill switch won't release
The kill switch is persisted in the database. Use the API:
```bash
curl -X POST http://localhost:8000/admin/resume \
  -H "Authorization: Bearer $TOKEN"
```

### SQLite "database is locked"
This happens under concurrent load. Switch to PostgreSQL for production:
```bash
GOVERNOR_DATABASE_URL=postgresql://user:pass@host:5432/governor
```

---

## Code Style

- **Python**: Standard library conventions, type hints throughout, Pydantic v2 models
- **TypeScript/React**: Inline styles (no CSS framework), functional components, hooks
- **Naming**: `snake_case` for Python, `camelCase` for JS/TS, `UPPER_CASE` for constants
- **Formatting**: No strict formatter enforced — keep consistent with surrounding code

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make changes with tests
4. Run the test suite: `cd governor-service && pytest tests/ -v`
5. Build the dashboard: `cd dashboard && npm run build`
6. Commit with conventional commits: `feat:`, `fix:`, `docs:`, etc.
7. Open a pull request against `main`

---

## License

[MIT](LICENSE) — Copyright © 2026 Sovereign AI Lab
