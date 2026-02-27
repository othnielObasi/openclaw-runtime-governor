# OpenClaw Runtime Governor

> **The missing safety layer between AI agents and the real world.**

[![CI - Dashboard](https://github.com/othnielObasi/openclaw-runtime-governor/actions/workflows/ci.yml/badge.svg)](https://github.com/othnielObasi/openclaw-runtime-governor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Sovereign AI Lab** · SURGE × OpenClaw Hackathon · Track 3: Developer Infrastructure & Tools

---

## The Problem

Autonomous AI agents can now browse the web, execute shell commands, read and write files, manage databases, and call APIs — **unsupervised**. The capabilities are extraordinary. The guardrails are not.

Today, when you deploy an AI agent in production:

- **There is no runtime check** on what tools the agent invokes. A coding assistant can `rm -rf /`. A data pipeline agent can exfiltrate credentials via HTTP. A customer support bot can be jailbroken into ignoring its instructions.
- **There is no audit trail.** You find out what your agent did *after* the damage — if you find out at all.
- **There is no real-time visibility.** You deploy an agent and hope for the best. If it starts behaving dangerously at 3 AM, nobody knows until morning.
- **There is no multi-step attack detection.** An agent that reads a credential file, then sends an HTTP request a minute later, looks innocent at each step — but the *sequence* is a textbook exfiltration pattern.
- **There is no standard governance API.** Every team builds ad-hoc safety checks buried inside agent code. Nothing is reusable, testable, or auditable.

Existing solutions either require rewriting agent internals, rely on brittle prompt engineering ("please don't do bad things"), or operate only at the LLM layer — completely blind to what tools the agent actually calls at runtime.

**The OpenClaw Runtime Governor intercepts tool calls *between* the agent and the real world — the exact point where intent becomes action — and applies layered, deterministic governance before anything executes.**

---

## How It Works

Every tool call your AI agent wants to make passes through the Governor first. The agent doesn't call tools directly — it asks permission, receives a verdict, and only proceeds if allowed.

```
Your AI Agent                          The Real World
     │                                       ▲
     │  "I want to run: shell rm -rf /"      │
     ▼                                       │
 ┌───────────────────────────────────────┐   │
 │     OpenClaw Runtime Governor         │   │
 │                                       │   │
 │  ① Kill Switch ── emergency halt?     │   │
 │  ② Injection Firewall ── jailbreak?   │   │
 │  ③ Scope Enforcer ── tool allowed?    │   │
 │  ④ Policy Engine ── rule match?       │   │
 │  ⑤ Neuro Risk + Chain Analysis        │   │
 │                                       │   │
 │  Verdict: BLOCK (risk 95/100)         │   │
 │  "Destructive filesystem operation"   │   │
 │                                       │   │
 │  ──► Audit log persisted              │   │
 │  ──► SSE event pushed to dashboard    │   │
 │  ──► SURGE receipt generated          │   │
 └───────────────────────────────────────┘   │
     │                                       │
     ✗  Agent receives block — tool          │
        never executes                       │
```

The pipeline **short-circuits**: a kill switch fires before the injection scan even starts, the firewall fires before policy evaluation, and so on. Every evaluation produces a detailed trace showing exactly which layers fired, their timing, and the rationale — making every governance decision fully explainable.

---

## What Makes This Different

| Approach | Where it operates | Runtime? | Deterministic? | Multi-step detection? | Auditable? |
|----------|-------------------|----------|----------------|-----------------------|------------|
| Prompt engineering | Inside the LLM | ❌ Static | ❌ Probabilistic | ❌ | ❌ |
| Output filtering | After LLM response | ❌ Post-hoc | Partially | ❌ | ❌ |
| Fine-tuning / RLHF | Model weights | ❌ Static | ❌ Probabilistic | ❌ | ❌ |
| API rate limiting | HTTP layer | ✅ | ✅ | ❌ | Partially |
| **OpenClaw Governor** | **Tool call interception** | **✅ Real-time** | **✅ 100%** | **✅ 6 patterns** | **✅ Full trace** |

The Governor doesn't try to make the AI "behave better." It operates at the **execution boundary** — the moment an agent's decision becomes a real-world action — with deterministic, auditable, policy-driven rules that no prompt injection can bypass.

### Key differentiators:

- **Language & framework agnostic.** Three SDKs (Python, TypeScript/JS, Java) — wrap any agent in 3 lines of code.
- **Real-time streaming.** Server-Sent Events push every governance decision to dashboards and monitoring tools within milliseconds. You don't poll for safety — you *watch* it happen.
- **Chain analysis.** Session-aware pattern detection across a 60-minute window catches multi-step attacks (credential theft → exfiltration, read → write → execute, repeated scope probing) that single-call checks miss entirely.
- **Zero-trust architecture.** The agent never touches tools directly. Every action is intercepted, evaluated, logged, and either allowed or blocked before execution.
- **On-chain attestation.** SURGE governance receipts (SHA-256) provide cryptographic proof of every governance decision for regulatory compliance.

---

## Components

| Directory | What | Version |
|-----------|------|---------|
| [`governor-service/`](governor-service/) | FastAPI backend — 5-layer pipeline, auth, SSE streaming, SURGE, audit | 0.3.0 |
| [`dashboard/`](dashboard/) | Next.js control panel — real-time monitoring, policy editor, admin | 0.2.0 |
| [`openclaw-skills/governed-tools/`](openclaw-skills/governed-tools/) | Python SDK (`openclaw-governor-client` on PyPI) | 0.2.0 |
| [`openclaw-skills/governed-tools/js-client/`](openclaw-skills/governed-tools/js-client/) | TypeScript/JS SDK (`@openclaw/governor-client` on npm) — dual CJS + ESM | 0.2.0 |
| [`openclaw-skills/governed-tools/java-client/`](openclaw-skills/governed-tools/java-client/) | Java SDK (`dev.openclaw:governor-client` on Maven Central) — zero deps, Java 11+ | 0.2.0 |
| [`openclaw-skills/moltbook-reporter/`](openclaw-skills/moltbook-reporter/) | Automated Moltbook status reporter | 0.3.0 |
| [`governor_agent.py`](governor_agent.py) | Autonomous governance agent (observe → reason → act loop) | — |
| [`docs/`](docs/) | Architecture docs, SDK comparison | — |

---

## Quick Start

### 1. Backend

```bash
cd governor-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Default dev credentials: `admin` / `changeme`

### 2. Dashboard

```bash
cd dashboard
npm install
NEXT_PUBLIC_GOVERNOR_API=http://localhost:8000 npm run dev
```

Open `http://localhost:3000` — **Demo Mode** (self-contained) or **Live Mode** (connects to backend).

### 3. Evaluate a tool call

```bash
# Get a token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}' | jq -r .access_token)

# Ask the Governor: "Can this agent run rm -rf /?"
curl -X POST http://localhost:8000/actions/evaluate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "shell",
    "args": {"command": "rm -rf /"},
    "context": {"agent_id": "my-agent"}
  }'
```

Response: `{ "decision": "block", "risk_score": 95, "explanation": "Destructive filesystem operation", ... }`

### 4. Watch it happen in real time

```bash
# Open an SSE stream — events arrive within milliseconds of each evaluation
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/actions/stream
```

Every time any agent calls `/actions/evaluate`, you'll see the decision appear instantly.

---

## Real-Time Monitoring

The Governor pushes every governance decision to connected clients via **Server-Sent Events (SSE)** — no polling delay, no missed events.

| Endpoint | What |
|----------|------|
| `GET /actions/stream` | SSE stream of all governance events (requires auth) |
| `GET /actions/stream/status` | Active subscriber count + heartbeat info |

### Dashboard integration
The dashboard connects automatically. Real-time events appear with a **LIVE** badge. The summary panel refreshes within 2 seconds of any new decision. When streaming is connected, polling backs off to 60s (from 30s) to reduce load.

### Connect from code

```javascript
// Browser / Node.js
const es = new EventSource("https://your-governor.fly.dev/actions/stream?token=<jwt>");
es.addEventListener("action_evaluated", (e) => {
  const { tool, decision, risk_score } = JSON.parse(e.data);
  console.log(`${tool}: ${decision} (risk ${risk_score})`);
});
```

```bash
# Terminal monitoring
curl -N -H "X-API-Key: ocg_..." https://your-governor.fly.dev/actions/stream
```

---

## Governance Pipeline

### Layer 1 — Kill Switch
Global emergency halt. When engaged, **every** evaluation returns `block` immediately. Persisted to database (survives restarts). Admin-only toggle via API or dashboard.

### Layer 2 — Injection Firewall
Scans the entire payload (tool name, args, context) against 11 known prompt-injection patterns: jailbreak, override, ignore previous, disable safety, etc. Triggers block with risk score 95.

### Layer 3 — Scope Enforcer
If the calling context includes `allowed_tools`, the requested tool must be in that list. Blocks out-of-scope tools with risk score 90.

### Layer 4 — Policy Engine
Matches against two policy sources:
- **Base policies** — 10 YAML rules shipped with the service ([`base_policies.yml`](governor-service/app/policies/base_policies.yml))
- **Dynamic policies** — created at runtime via API, stored in the database. Each policy has an `is_active` toggle — disable policies without deleting them. Regex patterns (`url_regex`, `args_regex`) are validated at creation and update time. Partial updates via PATCH.

### Layer 5 — Neuro Risk Estimator + Chain Analysis
Heuristic risk scorer (0–100) based on tool type, sensitive keywords, and bulk-recipient detection. **Chain analysis** examines session history across a 60-minute window to detect 6 multi-step attack patterns:

| Pattern | Risk Boost | What it catches |
|---------|------------|-----------------|
| `browse-then-exfil` | +35 | Data reconnaissance followed by HTTP send |
| `read-write-exec` | +45 | File read → write → shell execution chain |
| `repeated-scope-probing` | +60 | Multiple out-of-scope tool attempts |
| `credential-then-http` | +55 | Credential access then network request |
| `rapid-tool-switching` | +30 | 5+ distinct tools in quick succession |
| `block-bypass-retry` | +40 | Retrying a blocked action with variations |

---

## Client SDKs

Three official SDKs — authenticate with `X-API-Key`, throw on `block` decisions.

### Python  ·  `pip install openclaw-governor-client`

```python
from governor_client import evaluate_action, GovernorBlockedError

try:
    decision = evaluate_action("shell", {"command": "rm -rf /"})
except GovernorBlockedError:
    print("Blocked!")
```

### TypeScript / JavaScript  ·  `npm install @openclaw/governor-client`

```typescript
import { GovernorClient, GovernorBlockedError } from "@openclaw/governor-client";

const gov = new GovernorClient({
  baseUrl: "https://openclaw-governor.fly.dev",
  apiKey: "ocg_your_key_here",
});

try {
  const d = await gov.evaluate("shell", { command: "ls" });
} catch (err) {
  if (err instanceof GovernorBlockedError) console.error("Blocked!");
}
```

### Java  ·  `dev.openclaw:governor-client:0.2.0`

```java
GovernorClient gov = new GovernorClient.Builder()
    .baseUrl("https://openclaw-governor.fly.dev")
    .apiKey("ocg_your_key_here")
    .build();

try {
    GovernorDecision d = gov.evaluate("shell", Map.of("command", "ls"));
} catch (GovernorBlockedError e) {
    System.err.println("Blocked!");
}
```

See [`docs/SDK_OVERVIEW.md`](docs/SDK_OVERVIEW.md) for a full multi-language comparison.

---

## Security Model

### Authentication
All protected endpoints accept:
- **JWT Bearer** — `Authorization: Bearer <token>` from `POST /auth/login`
- **API Key** — `X-API-Key: ocg_<key>` (self-service rotation via dashboard or API)
- **Query param** — `?token=<jwt>` (for SSE/EventSource which can't set headers)

### Role-Based Access Control

| Role | Evaluate | Logs | Policies | Kill Switch | Users | Stream |
|------|----------|------|----------|-------------|-------|--------|
| `admin` | ✅ | ✅ | ✅ CRUD | ✅ | ✅ CRUD | ✅ |
| `operator` | ✅ | ✅ | ✅ CRUD | ❌ | ❌ | ✅ |
| `auditor` | ❌ | ✅ | Read | ❌ | ❌ | ✅ |

### Production Safeguards
- JWT secret **must** be changed from default — startup fails otherwise
- Login rate-limited (5/min), evaluate rate-limited (120/min)
- Kill switch state persisted to database
- Policy engine cached with configurable TTL

---

## SURGE Token Governance

| Feature | Description |
|---------|-------------|
| **Governance Receipts** | SHA-256 signed receipt for every evaluation — on-chain attestation ready |
| **Policy Staking** | Operators stake $SURGE on policies to signal confidence |
| **Fee Gating** | Optional micro-fee (0.001 $SURGE) per evaluation |
| **Token-Aware Policies** | Built-in rules for `surge_launch`, `surge_trade`, `surge_transfer` |

---

## Autonomous Governance Agent

[`governor_agent.py`](governor_agent.py) runs an autonomous observe → reason → act loop:

- Monitors governor health and action statistics on a configurable heartbeat
- Auto-engages kill switch after 5+ high-risk actions
- Auto-releases when threat levels subside
- Alerts on anomalies: >40% block rate, average risk >75
- Posts status updates to Moltbook

```bash
python governor_agent.py          # Full autonomous mode
python governor_agent.py --demo   # Single observation cycle
```

---

## API Reference

### Auth
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/login` | None | Login (rate-limited 5/min) |
| `POST` | `/auth/signup` | None | Public registration |
| `GET` | `/auth/me` | Any | Current user info |
| `POST` | `/auth/me/rotate-key` | Any | Rotate own API key (self-service) |
| `GET` | `/auth/users` | Admin | List all users |
| `POST` | `/auth/users` | Admin | Create user |
| `PATCH` | `/auth/users/{id}` | Admin | Update user |
| `DELETE` | `/auth/users/{id}` | Admin | Deactivate user |
| `POST` | `/auth/users/{id}/rotate-key` | Admin | Rotate any user's key |

### Governance
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/actions/evaluate` | Operator+ | Evaluate a tool call |
| `GET` | `/actions` | Any | List action logs (filterable) |
| `GET` | `/actions/stream` | Any | **Real-time SSE event stream** |
| `GET` | `/actions/stream/status` | Any | Active stream subscribers |
| `GET` | `/policies` | Any | List all policies (`?active_only=true` to filter) |
| `GET` | `/policies/{id}` | Any | Get single policy detail |
| `POST` | `/policies` | Operator+ | Create dynamic policy (validates regex) |
| `PATCH` | `/policies/{id}` | Operator+ | Partial update (description, severity, action, match, status) |
| `PATCH` | `/policies/{id}/toggle` | Operator+ | Toggle policy active/inactive |
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
| `POST` | `/surge/policies/stake` | Operator+ | Stake $SURGE on a policy |

---

## Testing

```bash
# Backend — 52 tests (24 governance + 18 policy management + 10 SSE streaming)
cd governor-service && pytest tests/ -v

# TypeScript/JS SDK — 6 tests
cd openclaw-skills/governed-tools/js-client && npm test

# Java SDK — 6 tests
cd openclaw-skills/governed-tools/java-client && mvn test
```

---

## Deployment

| Component | Platform | Config |
|-----------|----------|--------|
| Governor Service | Fly.io | [`fly.toml`](governor-service/fly.toml), [`Dockerfile`](governor-service/Dockerfile) |
| Dashboard | Vercel | [`vercel.json`](dashboard/vercel.json) |

See [`DEPLOY.md`](DEPLOY.md) for full instructions, [`PUBLISHING.md`](PUBLISHING.md) for SDK publishing, [`DEVELOPER.md`](DEVELOPER.md) for contributor guide.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Pydantic 2.8 |
| Real-time | Server-Sent Events (SSE), asyncio event bus |
| Auth | bcrypt, python-jose (JWT HS256), slowapi rate limiting |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Dashboard | Next.js 14.2, React 18.3, TypeScript |
| SDKs | Python (httpx), TypeScript/JS (fetch), Java (HttpClient) |
| Deployment | Fly.io (backend), Vercel (dashboard) |

---

## License

[MIT](LICENSE) — Copyright © 2026 Sovereign AI Lab
