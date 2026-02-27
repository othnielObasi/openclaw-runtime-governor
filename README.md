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
- **Agent traces are invisible.** You can see the final output, but you cannot reconstruct the agent's decision path — which LLM calls it made, which tools it invoked, how governance decisions fit into the execution timeline. When something goes wrong, post-mortem debugging is guesswork.
- **Multi-agent environments are ungovernable.** When multiple agents share infrastructure, there is no cross-agent view of who is doing what, no way to correlate one agent's governance blocks with another's escalating risk patterns.
- **Compliance is unprovable.** Regulators and auditors increasingly require evidence that AI systems were governed at runtime. Logs alone are insufficient — you need cryptographic attestation and traceable governance decision chains tied to specific agent actions.

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
| Observability platforms | LLM layer | ✅ Passive | N/A — monitors, can't enforce | Post-hoc correlation | ✅ Logs only |
| **OpenClaw Governor** | **Tool call interception** | **✅ Real-time** | **✅ 100%** | **✅ 6 patterns** | **✅ Full trace + attestation** |

The Governor doesn't try to make the AI "behave better." It operates at the **execution boundary** — the moment an agent's decision becomes a real-world action — with deterministic, auditable, policy-driven rules that no prompt injection can bypass.

### Why this isn't "another observability platform"

Existing AI observability platforms are excellent at **passive monitoring** — they trace LLM calls, measure token usage, detect embedding drift, and score hallucinations. They tell you *what happened*.

The OpenClaw Governor is fundamentally different: it **actively prevents** dangerous actions from executing. By the time an observability platform shows you that an agent ran `rm -rf /`, the damage is done. The Governor intercepts that call *before execution* and returns a `block` verdict — the tool never fires.

| Capability | Observability Platforms | OpenClaw Governor |
|---|---|---|
| **Can block a dangerous tool call?** | ❌ No — observe only | ✅ Yes — inline enforcement |
| **Prompt injection defense** | Detect in LLM output (post-hoc) | Block in tool payload (pre-execution, 11 patterns) |
| **Policy engine** | None — manual alert configuration | Full CRUD — YAML + DB policies, toggle, regex, PATCH |
| **Kill switch** | No concept | Global emergency halt, DB-persisted |
| **Multi-step attack detection** | Post-hoc trace correlation | Real-time — 6 chain patterns across 60-min session window |
| **Cryptographic attestation** | No | SHA-256 SURGE receipts per decision |
| **LLM-layer diagnostics** | ✅ Deep (tokens, latency, drift) | Not the focus — complementary |

**In practice, you'd use both**: an observability platform to optimize your agent's LLM quality, and OpenClaw to ensure it can never do anything dangerous regardless of what the LLM outputs. Observe + Govern.

### Key differentiators:

- **Language & framework agnostic.** Three SDKs (Python, TypeScript/JS, Java) — wrap any agent in 3 lines of code.
- **Real-time streaming.** Server-Sent Events push every governance decision to dashboards and monitoring tools within milliseconds. You don't poll for safety — you *watch* it happen.
- **Chain analysis.** Session-aware pattern detection across a 60-minute window catches multi-step attacks (credential theft → exfiltration, read → write → execute, repeated scope probing) that single-call checks miss entirely.
- **Zero-trust architecture.** The agent never touches tools directly. Every action is intercepted, evaluated, logged, and either allowed or blocked before execution.
- **Agent trace observability.** Full agent lifecycle tracing: every LLM call, tool invocation, and retrieval step is captured as spans in an OpenTelemetry-inspired trace tree. Governance decisions are auto-injected as child spans, so you can see *exactly* where in the agent's reasoning chain each policy fired.
- **Post-mortem reconstruction.** When an agent misbehaves, you don't guess — you pull the full trace, expand each span, see the governance pipeline results, and trace root cause from the agent's first thought to its last blocked action.
- **Multi-agent visibility.** Filter traces by `agent_id` to compare governance patterns across agents. Spot which agents are hitting blocks, which are probing scope boundaries, and which are operating cleanly — all from one dashboard.
- **On-chain attestation.** SURGE governance receipts (SHA-256) provide cryptographic proof of every governance decision for regulatory compliance.

---

## Components

| Directory | What | Version |
|-----------|------|---------|
| [`governor-service/`](governor-service/) | FastAPI backend — 5-layer pipeline, auth, SSE streaming, SURGE, audit | 0.3.0 |
| [`dashboard/`](dashboard/) | Next.js control panel — real-time monitoring, policy editor, admin | 0.2.0 |
| [`openclaw-skills/governed-tools/`](openclaw-skills/governed-tools/) | Python SDK (`openclaw-governor-client` on PyPI) | 0.3.0 |
| [`openclaw-skills/governed-tools/js-client/`](openclaw-skills/governed-tools/js-client/) | TypeScript/JS SDK (`@openclaw/governor-client` on npm) — dual CJS + ESM | 0.3.0 |
| [`openclaw-skills/governed-tools/java-client/`](openclaw-skills/governed-tools/java-client/) | Java SDK (`dev.openclaw:governor-client` on Maven Central) — zero deps, Java 11+ | 0.3.0 |
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

## Agent Trace Observability

The Governor captures the full lifecycle of every agent task — not just tool calls, but the LLM reasoning, retrieval steps, and governance decisions that connect them.

### The challenge solved

Traditional logging records *what happened*. Traces record *why it happened*. When an agent runs a 15-step task and gets blocked on step 12, you need to see:
- What the agent was trying to accomplish (the root span)
- Which LLM calls led to the blocked tool invocation (parent chain)
- Exactly where in the execution tree the governance pipeline fired
- Which policies matched and why the risk score was what it was

### How it works

```
Agent Framework                     Governor Service
     │                                    │
     │  SDK: ingestSpans([...])           │
     ├──────POST /traces/ingest──────────►│  Stores spans as trace tree
     │                                    │
     │  SDK: evaluate("shell", args,      │
     │       context={trace_id, span_id}) │
     ├──────POST /actions/evaluate───────►│  Evaluates + auto-creates
     │                                    │  governance span as child
     │                                    │  of the calling span
     │                                    │
     │  SDK: getTrace(trace_id)           │
     ├──────GET /traces/{id}─────────────►│  Returns full tree:
     │                                    │  agent → llm → governance
     │                                    │  with decision, risk, policies
```

### Span kinds

| Kind | Color (dashboard) | What it represents |
|------|-------------------|--------------------|
| `agent` | Red | Root agent task / orchestration step |
| `llm` | Violet | LLM inference call (GPT-4, Claude, etc.) |
| `tool` | Amber | Tool invocation (shell, HTTP, file, etc.) |
| `governance` | Red | Governor evaluation *(auto-created)* |
| `retrieval` | Cyan | RAG / vector search / document fetch |
| `chain` | Green | LangChain / multi-step chain execution |
| `custom` | Gray | Anything else |

### Zero-config governance correlation

Just pass `trace_id` and `span_id` in the context when calling evaluate:

```python
# The Governor auto-creates a governance span as a child of span_id
decision = evaluate_action("shell", {"command": "ls"}, context={
    "trace_id": "task-abc-123",
    "span_id": "llm-call-7",
    "agent_id": "my-agent",
})
```

The governance span contains the full 5-layer pipeline result (which layers fired, timing, matched policies, risk breakdown) — nested inside the agent's trace tree exactly where it belongs.

### Dashboard

The **Traces** tab (available to all roles) shows:
- Trace list with span count, governance count, duration, and block status
- Drill into any trace to see the full span tree with parent-child hierarchy
- Click any span for detailed metadata, timing, and governance pipeline visualization
- Filter by `agent_id` or `has_blocks` to focus on specific agents or problems

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

### Java  ·  `dev.openclaw:governor-client:0.3.0`

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
| `POST` | `/actions/evaluate` | Operator+ | Evaluate a tool call (auto-creates governance span if `trace_id` in context) |
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

### Traces — Agent Lifecycle Observability
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/traces/ingest` | Operator+ | Batch ingest agent trace spans (up to 500, idempotent) |
| `GET` | `/traces` | Any | List traces with summary (`?agent_id=`, `?has_blocks=true`) |
| `GET` | `/traces/{trace_id}` | Any | Full trace: all spans + correlated governance decisions |
| `DELETE` | `/traces/{trace_id}` | Operator+ | Delete all spans for a trace |

---

## Testing

```bash
# Backend — 68 tests (24 governance + 18 policy + 16 traces + 10 SSE streaming)
cd governor-service && pytest tests/ -v

# TypeScript/JS SDK — 10 tests
cd openclaw-skills/governed-tools/js-client && npm test

# Java SDK — 11 tests
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
