# Getting Started — OpenClaw Runtime Governor

> Complete guide to running, integrating, deploying, and contributing to the OpenClaw Runtime Governor.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start (5 minutes)](#quick-start-5-minutes)
3. [Repository Layout](#repository-layout)
4. [Core Concepts](#core-concepts)
5. [Authentication & Access Control](#authentication--access-control)
6. [Integrating Your Agent](#integrating-your-agent)
7. [Dashboard Guide](#dashboard-guide)
8. [Post-Execution Verification](#post-execution-verification)
9. [Conversation Logging](#conversation-logging)
10. [Agent Trace Observability](#agent-trace-observability)
11. [Real-Time Streaming (SSE)](#real-time-streaming-sse)
12. [Policy Management](#policy-management)
13. [SURGE Token Governance](#surge-token-governance)
14. [Escalation & Alerting](#escalation--alerting)
15. [Environment Variables](#environment-variables)
16. [Deployment](#deployment)
17. [Testing](#testing)
18. [Extending the Governor](#extending-the-governor)
19. [Troubleshooting](#troubleshooting)
20. [Contributing](#contributing)

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Governor service backend |
| Node.js | 20+ | Dashboard frontend |
| npm | 10+ | Dashboard packages |
| Git | 2.40+ | Version control |
| Docker | 24+ | *(optional)* Containerised deployment |
| jq | any | *(optional)* JSON parsing in terminal examples |

---

## Quick Start (5 minutes)

### 1. Start the backend

```bash
cd governor-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

On first startup, the server automatically:
- Creates all 17 database tables (SQLite at `./governor.db`)
- Seeds a default admin account: `admin` / `changeme`
- Loads 10 base governance policies from `app/policies/base_policies.yml`

Verify:
```bash
curl http://localhost:8000/healthz
# → {"status":"ok"}
```

### 2. Start the dashboard

```bash
cd dashboard
npm install
NEXT_PUBLIC_GOVERNOR_API=http://localhost:8000 npm run dev
```

Open `http://localhost:3000`. Choose **Live Mode** to connect to the backend or **Demo Mode** for a self-contained preview.

### 3. Evaluate your first tool call

```bash
# Get a JWT token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}' | jq -r .access_token)

# Ask the Governor: "Can this agent run rm -rf /?"
curl -s -X POST http://localhost:8000/actions/evaluate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "shell",
    "args": {"command": "rm -rf /"},
    "context": {"agent_id": "my-agent"}
  }' | jq .
```

Response:
```json
{
  "decision": "block",
  "risk_score": 95,
  "explanation": "Destructive filesystem operation",
  "policy_ids": ["shell-dangerous"],
  "execution_trace": [...]
}
```

### 4. Run the demo agent

```bash
python demo_agent.py                    # against local server
python demo_agent.py --verbose          # with detailed trace per evaluation
python demo_agent.py --fee-gating       # enable SURGE fee depletion
```

The demo agent runs 17 tool calls across 5 phases (safe → dangerous), plus 8 verification scenarios — producing traces, SURGE receipts, conversation turns, and audit logs you can explore in the dashboard.

---

## Repository Layout

```
openclaw-runtime-governor/
│
├── governor-service/              # FastAPI backend (the core)
│   ├── app/
│   │   ├── main.py                # App init, CORS, router registration, migrations
│   │   ├── config.py              # All env vars via pydantic-settings (GOVERNOR_ prefix)
│   │   ├── database.py            # SQLAlchemy engine, SessionLocal, db_session()
│   │   ├── models.py              # 17 ORM models (ActionLog, ConversationTurn, VerificationLog, etc.)
│   │   ├── schemas.py             # Pydantic v2 request/response schemas
│   │   ├── state.py               # Kill switch — DB-persisted, thread-safe
│   │   ├── session_store.py       # Session history reconstruction for chain analysis
│   │   ├── chain_analysis.py      # 11 multi-step attack pattern detector
│   │   ├── event_bus.py           # In-memory pub/sub for SSE streaming
│   │   ├── encryption.py          # Fernet symmetric encryption (conversation at rest)
│   │   ├── rate_limit.py          # slowapi rate limiter singleton
│   │   │
│   │   ├── api/                   # All API routes (80 routes across 64 paths)
│   │   │   ├── routes_actions.py         # POST /actions/evaluate, GET /actions
│   │   │   ├── routes_stream.py          # GET /actions/stream (SSE)
│   │   │   ├── routes_policies.py        # CRUD /policies + toggle + versioning
│   │   │   ├── routes_traces.py          # Agent trace lifecycle endpoints
│   │   │   ├── routes_verify.py          # POST /actions/verify, GET /verifications
│   │   │   ├── routes_conversations.py   # 6 conversation endpoints
│   │   │   ├── routes_admin.py           # Kill switch control
│   │   │   ├── routes_surge.py           # SURGE receipts, wallets, staking
│   │   │   ├── routes_escalation.py      # Escalation events + config
│   │   │   ├── routes_notifications.py   # 5-channel notification CRUD
│   │   │   └── routes_summary.py         # Moltbook summary export
│   │   │
│   │   ├── auth/                  # Authentication & authorization
│   │   │   ├── core.py            # bcrypt, JWT HS256, API key generation
│   │   │   ├── dependencies.py    # FastAPI deps: role guards, JWT/API-key extraction
│   │   │   ├── routes_auth.py     # Login, signup, user CRUD, key rotation
│   │   │   └── seed.py            # Default admin seeding on startup
│   │   │
│   │   ├── policies/              # Governance policy engine
│   │   │   ├── engine.py          # 6-layer evaluation pipeline
│   │   │   ├── loader.py          # Policy dataclass, YAML + DB loading, TTL cache
│   │   │   └── base_policies.yml  # 10 base governance rules
│   │   │
│   │   ├── neuro/
│   │   │   └── risk_estimator.py  # Heuristic risk scoring (0–100)
│   │   │
│   │   ├── verification/
│   │   │   └── engine.py          # 8-check post-execution verification engine
│   │   │
│   │   ├── escalation/
│   │   │   ├── engine.py          # Review queue, auto-kill-switch
│   │   │   └── notifier.py        # Email / Slack / WhatsApp / Jira / webhook dispatch
│   │   │
│   │   └── telemetry/
│   │       └── logger.py          # Writes action logs to DB
│   │
│   ├── tests/                     # 246 tests across 8 files
│   ├── conftest.py                # Session-scoped DB fixtures
│   ├── requirements.txt
│   ├── Dockerfile
│   └── fly.toml
│
├── dashboard/                     # Next.js 14 frontend (16 tabs)
│   ├── app/
│   │   ├── layout.tsx             # Root layout, fonts, AuthProvider
│   │   └── page.tsx               # Landing page: Demo / Live selector
│   ├── components/
│   │   ├── GovernorDashboard.jsx  # Live dashboard (~7000 lines, 16 tabs)
│   │   ├── Governordashboard-demo.jsx  # Demo dashboard (self-contained)
│   │   ├── ApiClient.ts           # Axios instance → NEXT_PUBLIC_GOVERNOR_API
│   │   ├── AuthContext.tsx         # Auth React context (JWT, role, login/logout)
│   │   ├── GovernorLogin.tsx       # Login + signup page
│   │   ├── ActionTester.tsx        # Tool evaluation form
│   │   ├── AdminStatus.tsx         # Kill switch toggle
│   │   ├── PolicyEditor.tsx        # Policy CRUD editor
│   │   ├── TraceViewer.tsx         # Agent trace explorer (span tree + detail panel)
│   │   ├── useActionStream.ts      # React hook for SSE auto-connect/reconnect
│   │   ├── RecentActions.tsx       # Audit log feed + live SSE merge (LIVE badge)
│   │   ├── SummaryPanel.tsx        # Stats overview (auto-refresh on SSE)
│   │   └── UserManagement.tsx      # User admin CRUD
│   ├── package.json
│   └── vercel.json
│
├── openclaw-skills/               # SDKs & tools
│   ├── governed-tools/
│   │   ├── governor_client.py     # Python SDK (PyPI: openclaw-governor-client)
│   │   ├── js-client/             # TypeScript/JS SDK (npm: @openclaw/governor-client)
│   │   ├── java-client/           # Java SDK (Maven: dev.openclaw:governor-client)
│   │   └── python-proxy/          # FastAPI proxy for network-isolated agents
│   └── moltbook-reporter/         # Automated Moltbook status reporter
│
├── demo_agent.py                  # DeFi Research Agent — live end-to-end governance demo
├── governor_agent.py              # Autonomous observe → reason → act governance agent
├── GovernorComplete.jsx           # Standalone dashboard artifact
├── docs/
│   ├── GETTING_STARTED.md         # ← This file
│   ├── ARCHITECTURE.md            # System architecture & request lifecycle
│   ├── GOVERNANCE_AUDIT.md        # Audit report — all gaps closed
│   ├── SDK_OVERVIEW.md            # Multi-language SDK comparison
│   └── AGENT.md                   # Demo agent documentation
├── DEPLOY.md                      # Deployment instructions (Fly.io, Vultr, Vercel)
├── PUBLISHING.md                  # SDK publishing (PyPI, npm, Maven Central)
├── DEVELOPER.md                   # Legacy developer guide → see this file
└── README.md                      # Project overview
```

---

## Core Concepts

### The Governance Pipeline

Every tool call passes through a **6-layer evaluation pipeline** that short-circuits on the first block:

```
Agent SDK → POST /actions/evaluate
                │
                ├─ Layer 1: Kill Switch         ← global emergency halt (DB-persisted)
                ├─ Layer 2: Injection Firewall   ← 20 regex patterns + Unicode normalization
                ├─ Layer 3: Scope Enforcer       ← allowed_tools whitelist from context
                ├─ Layer 4: Policy Engine        ← 10 YAML base + dynamic DB policies
                ├─ Layer 5: Neuro Risk + Chain   ← heuristic scoring + 11 attack patterns
                └─ Layer 6: Verification         ← 8 post-execution checks (on verify call)
                        │
                        ▼
              ActionDecision {
                decision:    "allow" | "review" | "block",
                risk_score:  0–100,
                explanation: "...",
                policy_ids:  ["shell-dangerous"],
                chain_pattern: "credential-then-http" | null,
                execution_trace: [layer-by-layer detail]
              }
                        │
                        ├─► action_logs table (audit trail)
                        ├─► SSE broadcast (real-time dashboard)
                        ├─► SURGE receipt (SHA-256 attestation)
                        └─► Escalation engine (review queue + notifications)
```

Each layer emits a `TraceStep` with timing, risk contribution, and detail text — making every governance decision fully explainable.

### Decisions

| Decision | Meaning | Agent Should |
|----------|---------|-------------|
| `allow` | Tool call is safe | Proceed with execution |
| `review` | Needs human review | Queue for approval or skip |
| `block` | Dangerous — rejected | Do NOT execute the tool |

### Chain Analysis (11 Patterns)

The Governor detects multi-step attack patterns by examining session history (60-minute window, max 50 actions):

| Pattern | Risk Boost | What it catches |
|---------|------------|-----------------|
| `repeated-scope-probing` | +60 | Agent tries tools outside its scope repeatedly |
| `multi-cred-harvest` | +60 | Multiple credential-related tool calls |
| `credential-then-http` | +55 | Credential access → network request (exfiltration) |
| `privilege-escalation` | +50 | Sudo/admin access → system changes |
| `read-write-exec` | +45 | File read → write → shell (lateral movement) |
| `delayed-exfil` | +45 | Long gap between data access and exfiltration |
| `block-bypass-retry` | +40 | Retrying blocked actions with variations |
| `data-staging` | +40 | Multiple file reads → network send |
| `browse-then-exfil` | +35 | HTTP browse → messaging send |
| `env-recon` | +35 | Environment probing → writes |
| `rapid-tool-switching` | +30 | 5+ distinct tools in quick succession |

### Database (17 Tables)

| Table | Purpose |
|-------|---------|
| `action_logs` | Every evaluation (tool, args, decision, risk, conversation_id, chain_pattern) |
| `policy_models` | Dynamic policies created via API |
| `users` | RBAC accounts (superadmin / admin / operator / auditor) |
| `governor_state` | Key-value store (kill switch state) |
| `conversation_turns` | Agent conversation turns (encrypted at rest) |
| `verification_logs` | Post-execution verification results (8 checks per entry) |
| `trace_spans` | Agent lifecycle trace spans |
| `surge_receipts` | SHA-256 governance attestation receipts |
| `surge_wallets` | Virtual $SURGE agent wallets |
| `surge_staked_policies` | $SURGE staked on policies |
| `escalation_events` | Review queue (pending → approve / reject / expire) |
| `escalation_config` | Per-agent escalation thresholds |
| `escalation_webhooks` | Webhook URLs for escalation |
| `notification_channels` | Multi-channel notification config |
| `policy_versions` | Immutable policy version snapshots |
| `policy_audit_log` | Before/after diffs for policy changes |
| `login_history` | Auth events with IP + user-agent |

Dev uses SQLite; production uses PostgreSQL 16. Tables are created automatically on startup via `Base.metadata.create_all()`, and `_run_migrations()` handles adding new columns to existing production databases.

---

## Authentication & Access Control

### Auth Methods

All protected endpoints accept three authentication methods simultaneously:

| Method | Header / Param | How to Obtain |
|--------|----------------|---------------|
| **JWT Bearer** | `Authorization: Bearer <token>` | `POST /auth/login` |
| **API Key** | `X-API-Key: ocg_<key>` | Dashboard API Keys tab, or `POST /auth/me/rotate-key` |
| **Query Param** | `?token=<jwt>` | For SSE/EventSource (browser can't set headers) |

### Getting a Token

```bash
# Login → JWT token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}' | jq -r .access_token)

echo $TOKEN
```

### Getting an API Key

```bash
# Rotate your own API key (self-service)
curl -s -X POST http://localhost:8000/auth/me/rotate-key \
  -H "Authorization: Bearer $TOKEN" | jq .

# Returns: {"api_key": "ocg_abc123..."}
```

Or use the **API Keys** tab in the dashboard — it shows your key (masked by default), lets you copy or regenerate it, and provides quick-start code samples.

### Role-Based Access Control (RBAC)

| Role | Evaluate | View Logs | Policies | Kill Switch | Verify | Users | Stream |
|------|----------|-----------|----------|-------------|--------|-------|--------|
| `superadmin` | ✅ | ✅ | ✅ CRUD | ✅ | ✅ | ✅ CRUD | ✅ |
| `admin` | ✅ | ✅ | ✅ CRUD | ✅ | ✅ | ✅ CRUD | ✅ |
| `operator` | ✅ | ✅ | ✅ CRUD | ❌ | ✅ | ❌ | ✅ |
| `auditor` | ❌ | ✅ | Read | ❌ | ❌ | ❌ | ✅ |

### Creating Users

```bash
# As admin, create an operator account
curl -s -X POST http://localhost:8000/auth/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"agent-ops","password":"secure-password","role":"operator"}' | jq .
```

Or use the **User Management** tab in the dashboard.

### Default Credentials

- **Local dev**: `admin` / `changeme`
- **Production**: Set `GOVERNOR_ADMIN_USERNAME` and `GOVERNOR_ADMIN_PASSWORD` in environment

> **Change the defaults before any deployment.** The server refuses to start in `production` mode with the default JWT secret.

---

## Integrating Your Agent

### Option A: SDK (Recommended)

Three official SDKs — authenticate with `X-API-Key`, throw on `block` decisions.

#### Python · `pip install openclaw-governor-client`

```python
import governor_client
from governor_client import evaluate_action, GovernorBlockedError

governor_client.GOVERNOR_URL = "https://openclaw-governor.fly.dev"
governor_client.GOVERNOR_API_KEY = "ocg_your_key_here"

try:
    decision = evaluate_action("shell", {"command": "ls -la"}, context={
        "agent_id": "my-agent",
        "session_id": "session-123",
        "allowed_tools": ["shell", "http_request", "file_read"],
    })
    print(f"{decision['decision']} — risk {decision['risk_score']}")
except GovernorBlockedError as e:
    print(f"Blocked: {e}")
    # Do NOT execute the tool
```

#### TypeScript / JavaScript · `npm install @openclaw/governor-client`

```typescript
import { GovernorClient, GovernorBlockedError } from "@openclaw/governor-client";

const gov = new GovernorClient({
  baseUrl: "https://openclaw-governor.fly.dev",
  apiKey: "ocg_your_key_here",
});

try {
  const d = await gov.evaluate("shell", { command: "ls -la" }, {
    agent_id: "my-agent",
    allowed_tools: ["shell", "http_request"],
  });
  console.log(`${d.decision} — risk ${d.risk_score}`);
} catch (err) {
  if (err instanceof GovernorBlockedError) {
    console.error("Blocked:", err.message);
  }
}
```

#### Java · `dev.openclaw:governor-client:0.3.0`

```java
GovernorClient gov = new GovernorClient.Builder()
    .baseUrl("https://openclaw-governor.fly.dev")
    .apiKey("ocg_your_key_here")
    .build();

try {
    GovernorDecision d = gov.evaluate("shell", Map.of("command", "ls -la"));
    System.out.println(d.getDecision() + " — risk " + d.getRiskScore());
} catch (GovernorBlockedError e) {
    System.err.println("Blocked: " + e.getMessage());
}
```

#### Environment Variables (all SDKs)

```bash
export GOVERNOR_URL=https://openclaw-governor.fly.dev
export GOVERNOR_API_KEY=ocg_your_key_here
```

All SDKs read these automatically when explicit configuration is not provided.

### Option B: Direct HTTP

No SDK needed — just `POST /actions/evaluate` with JSON:

```bash
curl -s -X POST https://openclaw-governor.fly.dev/actions/evaluate \
  -H "X-API-Key: ocg_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "http_request",
    "args": {
      "method": "POST",
      "url": "https://api.example.com/data",
      "body": {"query": "SELECT * FROM users"}
    },
    "context": {
      "agent_id": "data-pipeline-agent",
      "session_id": "run-456",
      "allowed_tools": ["http_request", "file_read"]
    }
  }' | jq .
```

### Integration Pattern

The standard integration pattern:

```
┌──────────────┐      ┌──────────────────┐      ┌──────────────┐
│  Your Agent  │─────►│  Governor API    │─────►│  Real World  │
│              │      │  /evaluate       │      │              │
│  1. Decide   │      │  → allow/block   │      │  Tool runs   │
│  2. Ask Gov  │◄─────│                  │      │  only if     │
│  3. Execute  │      │  /verify         │      │  allowed     │
│     if allow │─────►│  → compliant/    │      │              │
│  4. Verify   │      │    violation     │      │              │
└──────────────┘      └──────────────────┘      └──────────────┘
```

```python
# Full lifecycle example (Python)
import governor_client as gc

gc.GOVERNOR_URL = "http://localhost:8000"
gc.GOVERNOR_API_KEY = "ocg_..."

# Step 1: Pre-execution governance
decision = gc.evaluate_action("file_write", {
    "path": "/app/config.py",
    "content": "DEBUG = True"
}, context={"agent_id": "my-agent"})

if decision["decision"] == "block":
    print("Blocked — skipping execution")
elif decision["decision"] == "allow":
    # Step 2: Execute the tool
    result = actually_write_file("/app/config.py", "DEBUG = True")

    # Step 3: Post-execution verification (optional but recommended)
    import httpx
    verify_resp = httpx.post(f"{gc.GOVERNOR_URL}/actions/verify", json={
        "action_id": decision["action_id"],
        "tool": "file_write",
        "result": {"status": "success", "output": "Wrote 1 line"},
        "context": {"agent_id": "my-agent"}
    }, headers={"X-API-Key": gc.GOVERNOR_API_KEY})
    print(verify_resp.json()["verdict"])  # "compliant" or "violation"
```

### Context Fields

The `context` object controls scope enforcement and tracing:

| Field | Type | Purpose |
|-------|------|---------|
| `agent_id` | string | **Recommended** — identifies the agent for chain analysis and filtering |
| `session_id` | string | Groups related tool calls into a session (60-min chain window) |
| `allowed_tools` | string[] | If set, Layer 3 blocks any tool not in this list |
| `user_id` | string | Associate evaluations with a human user |
| `channel` | string | Communication channel (slack, web, etc.) |
| `trace_id` | string | Links evaluation to an agent trace tree |
| `span_id` | string | Parent span for governance span injection |
| `conversation_id` | string | Links to a conversation for conversation logging |
| `turn_id` | integer | Turn number within a conversation |
| `prompt` | string | *(opt-in)* The agent's reasoning / prompt — encrypted at rest |

---

## Dashboard Guide

The dashboard has **16 tabs**, each accessible based on your role:

| Tab | Icon | What It Shows |
|-----|------|---------------|
| **Dashboard** | 📊 | Summary: total actions, allow/review/block counts, risk distribution, live feed |
| **Agent Demo** | 🤖 | Run the 17-step demo agent directly from the browser |
| **Action Tester** | ⚡ | Manual tool evaluation form — test any tool /args / context |
| **Policies** | 📜 | CRUD editor for dynamic policies with active/inactive toggle |
| **Review Queue** | 👁 | Pending escalation events — approve / reject actions |
| **SURGE** | 💎 | SURGE receipts, fee tiers, wallet balances, policy staking |
| **Audit Log** | 🔍 | Full action history with search/filter, SSE live merge (LIVE badge) |
| **Conversations** | 💬 | Agent conversation turns + unified timeline |
| **Verification** | ✅ | Post-execution verification logs — 8 checks per entry |
| **Drift** | 📈 | Per-agent drift detection scores and trends |
| **Chain Analysis** | 🔗 | Detected multi-step attack patterns (dynamic bar chart) |
| **Traces** | 🌲 | Agent trace explorer — span trees, governance correlation |
| **Topology** | 🗺 | Agent-to-tool interaction graph |
| **API Keys** | 🔑 | View / copy / regenerate your API key + code samples |
| **Settings** | ⚙️ | Kill switch toggle, system configuration |
| **Users** | 👥 | User management — create operators and auditors |

### Demo Mode vs Live Mode

- **Demo Mode**: Fully self-contained — no backend needed. Uses simulated data to showcase all 16 tabs.
- **Live Mode**: Connects to your backend via `NEXT_PUBLIC_GOVERNOR_API`. All data is real.

---

## Post-Execution Verification

The verification engine inspects tool *results* after execution — closing the gap between allowing an intent and validating the outcome.

### Submit a verification

```bash
curl -s -X POST http://localhost:8000/actions/verify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action_id": 42,
    "tool": "file_write",
    "result": {
      "status": "success",
      "output": "Wrote 150 lines to /etc/passwd",
      "diff": "- root:x:0:0\n+ root:x:0:0:hacked"
    },
    "context": {
      "agent_id": "my-agent",
      "trace_id": "trace-abc"
    }
  }' | jq .
```

### 8 Verification Checks

| Check | What It Does |
|-------|--------------|
| `credential-scan` | Scans output/diff for API keys, tokens, passwords, secrets |
| `destructive-output` | Detects SQL drops, file deletions, dangerous patterns in output |
| `scope-compliance` | Verifies result is consistent with the agent's allowed scope |
| `diff-size` | Flags unexpectedly large changes (anomaly detection) |
| `intent-alignment` | **Critical**: Catches agents executing BLOCKED actions (policy bypass) |
| `output-injection` | Scans output for prompt injection patterns targeting downstream agents |
| `independent-reverify` | Re-runs the full policy engine against the output text |
| `drift-detection` | Compares agent behavior against historical baselines |

### Verdict

| Verdict | Meaning |
|---------|---------|
| `compliant` | All 8 checks passed |
| `suspicious` | Some checks flagged concerns but below violation threshold |
| `violation` | One or more critical failures — auto-escalated |

### List verifications

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/actions/verifications?verdict=violation" | jq .
```

---

## Conversation Logging

Opt-in capture of agent reasoning and prompts. All content is encrypted at rest with Fernet symmetric encryption.

### Include conversation context in evaluations

```python
decision = evaluate_action("shell", {"command": "ls"}, context={
    "agent_id": "my-agent",
    "conversation_id": "conv-abc-123",
    "turn_id": 1,
    "prompt": "User asked me to list directory contents"
})
```

### Batch ingest conversation turns

```bash
curl -s -X POST http://localhost:8000/conversations/turns/batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "conversation_id": "conv-abc-123",
      "turn_number": 1,
      "role": "user",
      "content": "List the files in /tmp"
    },
    {
      "conversation_id": "conv-abc-123",
      "turn_number": 2,
      "role": "assistant",
      "content": "I will use the shell tool to list the files."
    }
  ]' | jq .
```

### View conversations

```bash
# List all conversations
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/conversations" | jq .

# Get unified timeline (turns + governance actions interleaved)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/conversations/conv-abc-123/timeline" | jq .
```

---

## Agent Trace Observability

Capture the full lifecycle of every agent task — LLM reasoning, tool invocations, retrieval steps, and governance decisions as an OpenTelemetry-inspired span tree.

### Ingest trace spans

```bash
curl -s -X POST http://localhost:8000/traces/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "spans": [
      {
        "trace_id": "trace-task-001",
        "span_id": "root-span",
        "name": "Research Market Data",
        "kind": "agent",
        "start_time": "2026-02-28T12:00:00Z",
        "end_time": "2026-02-28T12:00:05Z"
      },
      {
        "trace_id": "trace-task-001",
        "span_id": "llm-call-1",
        "parent_span_id": "root-span",
        "name": "GPT-4 reasoning",
        "kind": "llm",
        "start_time": "2026-02-28T12:00:01Z",
        "end_time": "2026-02-28T12:00:03Z"
      }
    ]
  }' | jq .
```

### Zero-config governance correlation

Pass `trace_id` and `span_id` in the evaluation context — the Governor auto-creates a `governance` span as a child:

```python
decision = evaluate_action("shell", {"command": "ls"}, context={
    "agent_id": "my-agent",
    "trace_id": "trace-task-001",
    "span_id": "llm-call-1",
})
# → A governance span is auto-created as a child of llm-call-1
```

### View traces

```bash
# List all traces
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/traces" | jq .

# Full trace with span tree
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/traces/trace-task-001" | jq .
```

### Span Kinds

| Kind | Dashboard Color | What It Represents |
|------|----------------|--------------------|
| `agent` | Red | Root agent task / orchestration |
| `llm` | Violet | LLM inference call |
| `tool` | Amber | Tool invocation |
| `governance` | Red | Governor evaluation *(auto-created)* |
| `retrieval` | Cyan | RAG / vector search |
| `chain` | Green | Multi-step chain execution |
| `custom` | Gray | Anything else |

---

## Real-Time Streaming (SSE)

The Governor pushes every governance decision to connected clients via Server-Sent Events.

### Connect to the stream

```bash
# Terminal
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/actions/stream

# Or with API key
curl -N -H "X-API-Key: ocg_your_key" \
  http://localhost:8000/actions/stream
```

### From JavaScript

```javascript
const es = new EventSource(
  "https://openclaw-governor.fly.dev/actions/stream?token=" + jwt
);
es.addEventListener("action_evaluated", (e) => {
  const { tool, decision, risk_score } = JSON.parse(e.data);
  console.log(`${tool}: ${decision} (risk ${risk_score})`);
});
```

### Events

| Event | When |
|-------|------|
| `connected` | On initial connection |
| `action_evaluated` | After every `POST /actions/evaluate` |
| `:heartbeat` | Every 15 seconds (keep-alive) |

### Check status

```bash
curl http://localhost:8000/actions/stream/status
# → {"active_subscribers": 2, "heartbeat_interval_seconds": 15}
```

The dashboard auto-connects to SSE in Live Mode. A **LIVE** badge appears in the Audit Log + Dashboard tabs when streaming is active.

---

## Policy Management

### Base Policies (YAML)

10 policies ship with the Governor in `app/policies/base_policies.yml` — version-controlled and loaded on startup:

```yaml
- policy_id: shell-dangerous
  description: "Block destructive shell commands"
  tool: "shell"
  severity: critical
  action: block
  args_regex: "(rm\\s+-rf|mkfs|dd\\s+if=|shutdown|reboot)"
```

### Dynamic Policies (API)

Create, update, toggle, and delete policies at runtime:

```bash
# Create a policy
curl -s -X POST http://localhost:8000/policies \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "block-external-uploads",
    "description": "Block HTTP uploads to external domains",
    "tool": "http_request",
    "severity": "high",
    "action": "block",
    "url_regex": "^https?://(?!internal\\.company\\.com)"
  }' | jq .

# Toggle a policy on/off
curl -s -X PATCH http://localhost:8000/policies/block-external-uploads/toggle \
  -H "Authorization: Bearer $TOKEN" | jq .

# Partial update (only change description and severity)
curl -s -X PATCH http://localhost:8000/policies/block-external-uploads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"description": "Updated description", "severity": "critical"}' | jq .
```

### Policy Versioning

Every edit creates an immutable `PolicyVersion` snapshot + `PolicyAuditLog` with before/after JSON diffs. You can restore any previous version:

```bash
# List versions
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/policies/block-external-uploads/versions" | jq .

# Restore a version
curl -s -X POST \
  "http://localhost:8000/policies/block-external-uploads/versions/2/restore" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### Policy Cache

Policies are cached with a configurable TTL (default 10s). For instant updates during development:

```bash
GOVERNOR_POLICY_CACHE_TTL_SECONDS=0  # disable caching
```

---

## SURGE Token Governance

Economically-backed governance layer — all data DB-persisted.

| Feature | Description |
|---------|-------------|
| **Governance Receipts** | SHA-256 signed receipt for every evaluation |
| **Tiered Fees** | 0.001 (standard) → 0.005 (elevated) → 0.010 (high) → 0.025 (critical) $SURGE |
| **Virtual Wallets** | Auto-provisioned on first call (100 SURGE), returns 402 when empty |
| **Policy Staking** | Operators stake $SURGE on policies to signal confidence |

### Fee Tiers

| Risk Score | Fee |
|-----------|-----|
| 0–39 | 0.001 $SURGE |
| 40–69 | 0.005 $SURGE |
| 70–89 | 0.010 $SURGE |
| 90–100 | 0.025 $SURGE |

```bash
# Check SURGE status
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/surge/status" | jq .

# List receipts
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/surge/receipts" | jq .
```

---

## Escalation & Alerting

Automated escalation engine with 5 notification channels:

| Channel | Integration |
|---------|-------------|
| Email | SMTP (any provider) |
| Slack | Webhook URL or Bot API token |
| WhatsApp | Meta Cloud API |
| Jira | Issue creation via REST API |
| Webhook | Generic HTTP POST |

### Auto-Kill-Switch

The escalation engine monitors for:
- 3+ blocks in recent evaluations → auto-engage kill switch
- Average risk ≥ 82 in last 10 actions → auto-engage kill switch

### Configure notification channels

```bash
# Create a Slack channel
curl -s -X POST http://localhost:8000/notifications/channels \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "security-alerts",
    "channel_type": "slack",
    "config_json": {
      "webhook_url": "https://hooks.slack.com/services/T.../B.../..."
    },
    "is_active": true
  }' | jq .
```

### View escalation events

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/escalation/events?status=pending" | jq .

# Approve an event
curl -s -X PUT http://localhost:8000/escalation/events/42/approve \
  -H "Authorization: Bearer $TOKEN" | jq .
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
| `GOVERNOR_ENCRYPTION_KEY` | *(auto-generated)* | Fernet key for conversation encryption |
| `GOVERNOR_POLICIES_PATH` | `app/policies/base_policies.yml` | Base policy YAML path |
| `GOVERNOR_POLICY_CACHE_TTL_SECONDS` | `10` | Policy cache TTL (0 to disable) |
| `GOVERNOR_JWT_EXPIRE_MINUTES` | `480` | JWT token expiry (8 hours) |
| `GOVERNOR_LOGIN_RATE_LIMIT` | `5/minute` | Login rate limit |
| `GOVERNOR_EVALUATE_RATE_LIMIT` | `120/minute` | Evaluate rate limit |
| `GOVERNOR_ADMIN_USERNAME` | `admin` | Seed admin username |
| `GOVERNOR_ADMIN_PASSWORD` | `changeme` | Seed admin password |
| `GOVERNOR_SURGE_GOVERNANCE_FEE_ENABLED` | `false` | Enable $SURGE micro-fees |
| `GOVERNOR_SURGE_WALLET_ADDRESS` | *(empty)* | SURGE wallet for fee collection |

### Dashboard

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_GOVERNOR_API` | `http://localhost:8000` | Governor service URL (build-time) |

### SDKs / Agents

| Variable | Default | Description |
|----------|---------|-------------|
| `GOVERNOR_URL` | `http://localhost:8000` | Governor service URL |
| `GOVERNOR_API_KEY` | *(empty)* | API key (`ocg_…`) for `X-API-Key` header |

---

## Deployment

### Live Deployments

| Component | Platform | URL |
|-----------|----------|-----|
| Backend (primary) | Fly.io | `https://openclaw-governor.fly.dev` |
| Backend (standby) | Vultr VPS | `http://45.76.141.204:8000` |
| Dashboard (primary) | Vercel | `https://openclaw-runtime-governor.vercel.app` |
| Dashboard (mirror) | Vercel | `https://openclaw-runtime-governor-j9py.vercel.app` |
| Dashboard (standby) | Vultr VPS | `http://45.76.141.204:3000` |

### Deploy to Fly.io

```bash
cd governor-service
fly launch        # first time only
fly deploy

# Set secrets
fly secrets set GOVERNOR_JWT_SECRET="your-long-random-secret"
fly secrets set GOVERNOR_ADMIN_PASSWORD="your-secure-password"
fly secrets set GOVERNOR_DATABASE_URL="postgresql://..."
fly secrets set GOVERNOR_ENVIRONMENT="production"
```

### Deploy to Vultr (Docker Compose)

```bash
git clone https://github.com/othnielObasi/openclaw-runtime-governor.git
cd openclaw-runtime-governor/governor-service/vultr
cp .env.vultr.example .env
nano .env                    # fill in real secrets
docker compose up -d

# Verify
curl http://localhost:8000/healthz
```

The Vultr stack includes: Governor + PostgreSQL 16 + Dashboard (Next.js standalone) + Caddy (reverse proxy / HTTPS).

### Deploy Dashboard to Vercel

1. Import the repo into Vercel
2. Set root directory to `dashboard`
3. Set env var: `NEXT_PUBLIC_GOVERNOR_API=https://openclaw-governor.fly.dev`
4. Deploy

### Failover

The Vultr deployment acts as a hot standby. To switch traffic during a Fly.io outage:
1. Update `NEXT_PUBLIC_GOVERNOR_API` to point to the Vultr IP
2. Redeploy the dashboard on Vercel

See [`DEPLOY.md`](../DEPLOY.md) for detailed deployment instructions.

---

## Testing

### Backend (246 tests)

```bash
cd governor-service
pytest tests/ -v
```

| File | Coverage |
|------|----------|
| `test_governor.py` | Governance pipeline: decisions, firewall, scope, kill switch, neuro, chain, SURGE |
| `test_conversations.py` | Conversation logging: turns, batch ingest, timeline, encryption |
| `test_escalation.py` | Escalation engine: review queue, auto-kill-switch, thresholds |
| `test_policies.py` | Policy CRUD: create, update, toggle, regex validation |
| `test_stream.py` | SSE streaming: event bus, subscribers, auth, heartbeat |
| `test_traces.py` | Trace observability: ingest, tree reconstruction, governance correlation |
| `test_verification.py` | Post-execution: 8 checks, intent-alignment, drift detection |
| `test_versioning.py` | Policy versioning + notification channels (5 types) |

### SDK Tests

```bash
# TypeScript/JS (10 tests)
cd openclaw-skills/governed-tools/js-client && npm test

# Java (11 tests)
cd openclaw-skills/governed-tools/java-client && mvn test
```

### Writing New Tests

Tests call `evaluate_action()` directly from `policies.engine` — no HTTP layer involved:

```python
# governor-service/tests/test_governor.py
from app.schemas import ActionInput
from app.policies.engine import evaluate_action

def test_my_scenario():
    inp = ActionInput(
        tool="shell",
        args={"command": "echo hello"},
        context={"agent_id": "test-agent"}
    )
    result = evaluate_action(inp)
    assert result.decision == "allow"
    assert result.risk_score < 50
```

Fixtures (`conftest.py`): Session-scoped autouse fixture creates all tables before the suite and drops them after.

---

## Extending the Governor

### Adding a New Policy (YAML)

Edit `governor-service/app/policies/base_policies.yml`:

```yaml
- policy_id: my-custom-rule
  description: "Block dangerous custom tool"
  tool: "my_dangerous_tool"
  severity: critical
  action: block
  args_regex: "(dangerous_pattern|exploit_attempt)"
```

Restart the server to load changes.

### Adding a New Pipeline Layer

1. Add your layer logic in `app/` (new file or existing)
2. Edit `app/policies/engine.py` — add to the `evaluate_action()` pipeline
3. Emit a `TraceStep` for observability:

```python
trace.append(TraceStep(
    layer=7,
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

### Adding a Dashboard Tab

Dashboard components use **inline styles** (navy depth palette). Design tokens:

```javascript
const C = {
  bg0: "#080e1a",  bg1: "#0f1b2d",  bg2: "#1d3452",
  line: "#1d3452", p1: "#e2e8f0",   p2: "#8fa3bf",  p3: "#4a6785",
  accent: "#e8412a", green: "#22c55e", amber: "#f59e0b", red: "#ef4444",
};
const mono = "'IBM Plex Mono', monospace";
const sans = "'DM Sans', sans-serif";
```

Pattern:
1. Create a new component in `dashboard/components/`
2. Use `ApiClient` for backend calls: `import api from "./ApiClient";`
3. Access auth: `import { useAuth } from "./AuthContext";`

### Adding a Notification Channel Type

1. Add the channel type to the `NotificationChannel` model in `models.py`
2. Implement the dispatch logic in `escalation/notifier.py`
3. Add tests in `test_versioning.py`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **"JWT secret must be changed from default"** | Set `GOVERNOR_JWT_SECRET` to a long random string (only in `production` mode) |
| **Dashboard shows "API is not set"** | Set `NEXT_PUBLIC_GOVERNOR_API` **before** building: `NEXT_PUBLIC_GOVERNOR_API=https://... npm run build` |
| **Policy changes not taking effect** | Policy cache TTL is 10s — wait or set `GOVERNOR_POLICY_CACHE_TTL_SECONDS=0` |
| **Kill switch won't release** | Use the API: `curl -X POST .../admin/resume -H "Authorization: Bearer $TOKEN"` |
| **SQLite "database is locked"** | Switch to PostgreSQL: `GOVERNOR_DATABASE_URL=postgresql://user:pass@host/db` |
| **CORS errors on dashboard** | Set `GOVERNOR_ALLOW_CORS_ORIGINS='["https://your-dashboard.vercel.app"]'` |
| **SSE stream disconnects** | The 15s heartbeat keeps connections alive. Check for proxy timeouts. Reconnection is automatic in the dashboard. |
| **Vultr data not persisting** | Ensure `GOVERNOR_DATABASE_URL` points to PostgreSQL. If using Docker, ensure `docker compose` reads `.env` (not raw `docker run`). |
| **Demo agent all blocks** | Check if kill switch is engaged: `curl .../admin/status`. Resume if needed. |
| **Verification engine crash on dict** | Upgrade to latest code — fixed in commit `ba91ce7` (dict-to-string coercion in `check_diff_size`). |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make changes with tests
4. Run the test suite: `cd governor-service && pytest tests/ -v`
5. Build the dashboard: `cd dashboard && npm run build`
6. Commit with conventional commits: `feat:`, `fix:`, `docs:`, etc.
7. Open a pull request against `main`

### CI/CD

| Workflow | Trigger | What It Does |
|----------|---------|--------------|
| Dashboard Build | Push/PR touching `dashboard/**` | `npm ci && npm run build` |
| Moltbook Poster | Cron (every 30 min) | Runs `moltbook_lablab_poster.py` |
| SDK Publish | GitHub Release | Publishes to PyPI, npm, Maven Central |

See [`PUBLISHING.md`](../PUBLISHING.md) for SDK publishing secrets and instructions.

---

## Further Reading

| Document | Description |
|----------|-------------|
| [README.md](../README.md) | Project overview, comparison, full API reference |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, request lifecycle, file map |
| [GOVERNANCE_AUDIT.md](GOVERNANCE_AUDIT.md) | Governance coverage audit — all gaps closed |
| [SDK_OVERVIEW.md](SDK_OVERVIEW.md) | Multi-language SDK comparison and API methods |
| [AGENT.md](AGENT.md) | Demo agent documentation (5 phases + verification) |
| [DEPLOY.md](../DEPLOY.md) | Detailed deployment instructions |
| [PUBLISHING.md](../PUBLISHING.md) | SDK publishing (PyPI, npm, Maven Central) |

---

**License**: [MIT](../LICENSE) — Copyright © 2026 Sovereign AI Lab
