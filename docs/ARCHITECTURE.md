# Architecture – OpenClaw Governor (Harmonized)

## Request Lifecycle

```
OpenClaw Agent / SDK
     │
     ▼ POST /actions/evaluate
     │   Authorization: Bearer <jwt>   OR   X-API-Key: ocg_<key>
     │
 governor-service (FastAPI)
     │
     ├─1─ Kill Switch          ← instant block if globally halted
     │
     ├─2─ Injection Firewall   ← scans payload for 11 prompt-injection patterns
     │
     ├─3─ Scope Enforcer       ← enforces allowed_tools from context
     │
     ├─4─ Policy Engine        ← YAML base policies + DB dynamic policies
     │        ├─ base_policies.yml  (loaded at startup, cached with TTL)
     │        └─ PolicyModel (DB)   (created at runtime via API)
     │
     ├─5─ Neuro Risk Estimator ← heuristic scoring (tool type, keywords,
     │        │                   bulk-recipients) → elevates risk_score
     │        └─ Chain Analysis ← detects 6 multi-step attack patterns
     │                            across 60-min session window
     │
     └─► ActionDecision { decision, risk_score, explanation, policy_ids, trace }
              │
              ├─► Audit Logger  →  action_logs table (SQLite / Postgres)
              └─► SURGE Receipt →  SHA-256 governance attestation
```

## Authentication

Dual auth via FastAPI dependency injection (`auth/dependencies.py`):

| Method | Header | Generation |
|--------|--------|-----------|
| JWT Bearer | `Authorization: Bearer <token>` | `POST /auth/login` |
| API Key | `X-API-Key: ocg_<key>` | `POST /auth/me/rotate-key` (self-service) |

Both methods are supported simultaneously on every protected endpoint. API keys use the `ocg_` prefix + `secrets.token_urlsafe(32)` (~43 chars).

### RBAC

| Role | Evaluate | View Logs | Policies | Kill Switch | Users | API Keys |
|------|----------|-----------|----------|-------------|-------|----------|
| `admin` | ✅ | ✅ | ✅ CRUD | ✅ | ✅ CRUD | ✅ own + any |
| `operator` | ✅ | ✅ | ✅ CRUD | ❌ | ❌ | ✅ own |
| `auditor` | ❌ | ✅ | Read only | ❌ | ❌ | ✅ own |

## File Map

```
governor-service/
├── app/
│   ├── main.py               ← FastAPI app init, CORS, route registration
│   ├── config.py             ← Settings (pydantic-settings, env vars)
│   ├── database.py           ← SQLAlchemy engine, SessionLocal, db_session()
│   ├── models.py             ← ActionLog, PolicyModel, User, GovernorState
│   ├── schemas.py            ← Pydantic schemas (ActionInput, ActionDecision, etc.)
│   ├── state.py              ← Kill switch — DB-persisted, thread-safe
│   ├── session_store.py      ← Session history reconstruction for chain analysis
│   ├── chain_analysis.py     ← 6 multi-step attack pattern detector
│   ├── rate_limit.py         ← slowapi rate limiter singleton
│   ├── api/
│   │   ├── routes_actions.py ← POST /actions/evaluate, GET /actions
│   │   ├── routes_policies.py← GET/POST/DELETE /policies
│   │   ├── routes_summary.py ← GET /summary/moltbook
│   │   ├── routes_admin.py   ← GET /admin/status, POST /admin/kill|resume
│   │   └── routes_surge.py   ← SURGE receipts, staking, fee gating
│   ├── auth/
│   │   ├── core.py           ← bcrypt hashing, JWT encode/decode, API key generation
│   │   ├── dependencies.py   ← FastAPI deps: JWT/API key extraction, role guards
│   │   ├── routes_auth.py    ← Login, signup, user CRUD, key rotation (self-service + admin)
│   │   └── seed.py           ← Default admin seeding on startup
│   ├── policies/
│   │   ├── engine.py         ← evaluate_action() – full 5-layer pipeline
│   │   ├── loader.py         ← Policy dataclass, load_base_policies(), load_db_policies(), cache
│   │   └── base_policies.yml ← 10 YAML-defined static policies
│   ├── neuro/
│   │   └── risk_estimator.py ← estimate_neural_risk() heuristic (0–100)
│   └── telemetry/
│       └── logger.py         ← log_action() – writes to action_logs table
│
dashboard/
├── app/
│   ├── layout.tsx            ← Root layout (dark theme, fonts, AuthProvider)
│   └── page.tsx              ← Landing page with Demo/Live selector
└── components/
    ├── ApiClient.ts          ← Axios instance pointing to NEXT_PUBLIC_GOVERNOR_API
    ├── AuthContext.tsx        ← Auth React context (JWT, role, login/logout)
    ├── GovernorLogin.tsx      ← Login + signup page
    ├── GovernorDashboard.jsx  ← Live dashboard (all tabs including API Keys)
    ├── Governordashboard-demo.jsx ← Demo dashboard (self-contained)
    ├── ActionTester.tsx       ← POST /actions/evaluate UI
    ├── AdminStatus.tsx        ← Kill switch toggle
    ├── PolicyEditor.tsx       ← Create/delete dynamic policies
    ├── RecentActions.tsx      ← GET /actions audit feed
    ├── SummaryPanel.tsx       ← Stats overview
    └── UserManagement.tsx     ← User admin CRUD
│
openclaw-skills/
├── governed-tools/
│   ├── governor_client.py    ← Python SDK (PyPI: openclaw-governor-client)
│   ├── js-client/            ← TypeScript/JS SDK (npm: @openclaw/governor-client)
│   │   └── src/index.ts      ← GovernorClient class, dual CJS+ESM build
│   ├── java-client/          ← Java SDK (Maven: dev.openclaw:governor-client)
│   │   └── src/main/java/dev/openclaw/governor/
│   │       ├── GovernorClient.java       ← Builder pattern, java.net.http.HttpClient
│   │       ├── GovernorDecision.java
│   │       ├── GovernorBlockedError.java
│   │       └── SimpleJson.java           ← Zero-dep JSON parser
│   ├── python-proxy/         ← FastAPI proxy for agents
│   └── skill.toml
└── moltbook-reporter/
    ├── reporter.py           ← fetch_summary(), build_status_text()
    └── skill.toml
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Layered evaluation (kill → firewall → scope → policy → neuro+chain) | Short-circuit on most critical checks first |
| YAML + DB policies | Static policies version-controlled; dynamic policies editable at runtime |
| `Policy.matches()` method | Encapsulates matching logic cleanly; easy to extend |
| Neuro estimator raises risk, not decision | Risk scoring is advisory; only explicit policies change allow→block |
| Chain analysis with 60-min session window | Detects multi-step attack patterns across related tool calls |
| Dual auth (JWT + API key) | JWT for dashboard sessions; API keys for programmatic SDK access |
| Self-service key rotation (`/auth/me/rotate-key`) | OpenAI/Anthropic-style developer experience |
| `ocg_` key prefix | Easy identification, plaintext prefix enables revocation scanning |
| Three official SDKs (Python, TypeScript/JS, Java) | Cover the most common agent runtimes |
| TypeScript SDK dual CJS + ESM | Maximum compatibility across Node.js module systems |
| Java SDK zero external deps | Minimal JAR size, no dependency conflicts in agent runtimes |
| Context metadata indexed in DB | Enables efficient filtering by agent_id, user_id, channel |
| CORS middleware on FastAPI | Allows dashboard on different origin (Vercel) to talk to backend (Fly.io) |
| SURGE governance receipts (SHA-256) | Immutable attestation for on-chain governance proofs |
