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
 │  ⑥ Post-Execution Verification        │   │
 │                                       │   │
 │  Verdict: BLOCK (risk 95/100)         │   │
 │  "Destructive filesystem operation"   │   │
 │                                       │   │
 │  ──► Audit log persisted              │   │
 │  ──► SSE event pushed to dashboard    │   │
 │  ──► SURGE receipt generated          │   │
 │  ──► Escalation queue + notifications │   │
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
| **OpenClaw Governor** | **Tool call interception** | **✅ Real-time** | **✅ 100%** | **✅ 11 patterns** | **✅ Full trace + attestation** |

The Governor doesn't try to make the AI "behave better." It operates at the **execution boundary** — the moment an agent's decision becomes a real-world action — with deterministic, auditable, policy-driven rules that no prompt injection can bypass.

### Key capabilities:

- **🛡️ Inline enforcement.** This is not passive monitoring. Every tool call is intercepted, evaluated against layered policies, and either allowed or blocked *before it executes*. The dangerous action never fires.
- **🔥 Prompt injection firewall.** 11 injection patterns scanned on every tool-call payload — catches jailbreaks that survive the LLM layer and reach the tool execution boundary.
- **📜 Full policy engine.** YAML base policies + dynamic DB policies with CRUD, partial updates (PATCH), active/inactive toggle, and regex validation. Not just alerts — enforceable rules.
- **🚨 Kill switch.** One API call halts every agent globally. DB-persisted, survives restarts. When things go wrong at 3 AM, you have an instant off switch.
- **🔗 Multi-step attack detection.** 11 chain patterns evaluated in real-time across a 60-minute session window. Catches credential-then-exfiltration, read-write-execute chains, scope probing, privilege escalation, and data staging that look innocent one step at a time.
- **🔍 Post-execution verification.** 8-check verification engine inspects tool *results* after execution — credential leak scan, destructive output detection, intent-alignment, diff size anomaly, output injection scan, independent re-verification against policies, and cross-session drift detection. Catches agents that execute blocked actions or produce unsafe output.
- **💬 Conversation logging.** Opt-in capture of agent prompts and reasoning with encrypted-at-rest storage, conversation timelines, and correlation to governance decisions. See what the agent was *thinking* when it made each tool call.
- **⚡ Real-time streaming.** Server-Sent Events push every governance decision to dashboards within milliseconds. You don't poll for safety — you *watch* it happen.
- **🔍 Agent trace observability.** Full agent lifecycle tracing: LLM calls, tool invocations, and retrieval steps captured as spans in an OpenTelemetry-inspired trace tree. Governance decisions are auto-injected as child spans — see *exactly* where in the agent's reasoning chain each policy fired.
- **🔬 Post-mortem reconstruction.** When an agent misbehaves, pull the full trace, expand each span, see the governance pipeline results, and trace root cause from the agent's first thought to its last blocked action.
- **👥 Multi-agent visibility.** Filter traces by `agent_id` to compare governance patterns across agents. Spot which agents are hitting blocks, which are probing scope boundaries, and which are operating cleanly — all from one dashboard.
- **🌐 Language & framework agnostic.** Three SDKs (Python, TypeScript/JS, Java) — wrap any agent in 3 lines of code. No agent rewrites required.
- **🔐 Cryptographic attestation.** SURGE governance receipts (SHA-256) provide provable evidence of every governance decision for regulatory compliance.

---

## Components

| Directory | What | Version |
|-----------|------|---------|
| [`governor-service/`](governor-service/) | FastAPI backend — 6-layer pipeline, auth, SSE streaming, SURGE, verification, conversations | 0.4.0 |
| [`dashboard/`](dashboard/) | Next.js control panel — 16 tabs, real-time monitoring, policy editor, verification, traces | 0.3.0 |
| [`openclaw-skills/governed-tools/`](openclaw-skills/governed-tools/) | Python SDK (`openclaw-governor-client` on PyPI) | 0.3.0 |
| [`openclaw-skills/governed-tools/js-client/`](openclaw-skills/governed-tools/js-client/) | TypeScript/JS SDK (`@openclaw/governor-client` on npm) — dual CJS + ESM | 0.3.0 |
| [`openclaw-skills/governed-tools/java-client/`](openclaw-skills/governed-tools/java-client/) | Java SDK (`dev.openclaw:governor-client` on Maven Central) — zero deps, Java 11+ | 0.3.0 |
| [`openclaw-skills/moltbook-reporter/`](openclaw-skills/moltbook-reporter/) | Automated Moltbook status reporter | 0.3.0 |
| [`governor_agent.py`](governor_agent.py) | Autonomous governance agent (observe → reason → act loop) | — |
| [`demo_agent.py`](demo_agent.py) | DeFi Research Agent — live end-to-end governance demo (5 phases, 17 tool calls) | — |
| [`docs/`](docs/) | Architecture docs, SDK comparison | — |

---

## Quick Start

> **Full guide**: See [Getting Started](docs/GETTING_STARTED.md) for the comprehensive setup, architecture, integration, and deployment walkthrough.

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
Heuristic risk scorer (0–100) based on tool type, sensitive keywords, and bulk-recipient detection. **Chain analysis** examines session history across a 60-minute window to detect 11 multi-step attack patterns:

| Pattern | Risk Boost | What it catches |
|---------|------------|-----------------|
| `browse-then-exfil` | +35 | Data reconnaissance followed by HTTP send |
| `read-write-exec` | +45 | File read → write → shell execution chain |
| `repeated-scope-probing` | +60 | Multiple out-of-scope tool attempts |
| `credential-then-http` | +55 | Credential access then network request |
| `rapid-tool-switching` | +30 | 5+ distinct tools in quick succession |
| `block-bypass-retry` | +40 | Retrying a blocked action with variations |
| `privilege-escalation` | +50 | Sudo/admin access followed by system changes |
| `data-staging` | +40 | Multiple file reads before a network send |
| `env-recon` | +35 | Environment/config probing before writes |
| `multi-cred-harvest` | +60 | Multiple credential-related tool calls |
| `delayed-exfil` | +45 | Long gap between data access and exfiltration |

---

## Post-Execution Verification

The Governor doesn't just gate *intent* — it verifies *results*. After a tool executes, submit the output for an 8-check verification scan:

```
Agent executes tool → POST /actions/verify { action_id, result, diff }
                                    │
                    ┌───────────────┼───────────────────┐
                    │  8 verification checks:            │
                    │  ① Credential leak scan            │
                    │  ② Destructive output detection    │
                    │  ③ Scope compliance                │
                    │  ④ Diff size anomaly               │
                    │  ⑤ Intent-alignment (block bypass) │
                    │  ⑥ Output injection scan           │
                    │  ⑦ Independent re-verification     │
                    │  ⑧ Cross-session drift detection   │
                    └────────────────────────────────────┘
                                    │
                    Verdict: compliant | suspicious | violation
                    + escalation if violation detected
```

Each check runs independently and contributes to a risk delta. The intent-alignment check catches agents that **execute actions that were blocked** — a critical policy bypass detection. The drift detector compares per-agent behavior baselines across sessions.

---

## Conversation Logging

Opt-in capture of the agent's reasoning and prompts — encrypted at rest with Fernet symmetric encryption.

```python
# Agents include conversation_id + prompt in evaluate calls:
decision = evaluate_action("shell", {"command": "ls"}, context={
    "agent_id": "my-agent",
    "conversation_id": "conv-abc-123",
    "prompt": "User asked me to list directory contents"
})

# Batch ingest conversation turns:
POST /conversations/turns/batch
[{ "conversation_id": "conv-abc-123", "role": "user", "content": "List the files", ... }]
```

The **Conversations** tab in the dashboard shows:
- All conversations with turn counts and timeline
- Each turn linked to its corresponding governance action
- Full unified timeline: turns + actions interleaved chronologically
- Encrypted storage — prompts are only visible to authenticated admin/operator users

---

## Escalation & Alerting

Automated escalation engine with configurable thresholds and 5 notification channels:

| Channel | Integration |
|---------|-------------|
| Email | SMTP (any provider) |
| Slack | Webhook URL or Bot API token |
| WhatsApp | Meta Cloud API |
| Jira | Issue creation via REST API |
| Webhook | Generic HTTP POST to any URL |

**Auto-kill-switch**: 3+ blocks OR average risk ≥ 82 in last 10 actions → automatic global shutdown. Per-agent thresholds supported.

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

| Role | Evaluate | Logs | Policies | Kill Switch | Users | Stream | Verify |
|------|----------|------|----------|-------------|-------|--------|--------|
| `superadmin` | ✅ | ✅ | ✅ CRUD | ✅ | ✅ CRUD | ✅ | ✅ |
| `admin` | ✅ | ✅ | ✅ CRUD | ✅ | ✅ CRUD | ✅ | ✅ |
| `operator` | ✅ | ✅ | ✅ CRUD | ❌ | ❌ | ✅ | ✅ |
| `auditor` | ❌ | ✅ | Read | ❌ | ❌ | ✅ | ❌ |

### Production Safeguards
- JWT secret **must** be changed from default — startup fails otherwise
- Login rate-limited (5/min), evaluate rate-limited (120/min)
- Kill switch state persisted to database
- Policy engine cached with configurable TTL

---

## SURGE Token Governance

The Governor integrates with the SURGE token economy to create an **economically-backed governance layer**. All data is DB-persisted (survives Fly.io restarts).

| Feature | Description |
|---------|-------------|
| **Governance Receipts** | SHA-256 signed receipt for every evaluation — DB-persisted, on-chain attestation ready |
| **Tiered Fee Pricing** | Fees scale with risk: 0.001 (standard) → 0.005 (elevated) → 0.010 (high) → 0.025 (critical) $SURGE per evaluation |
| **Virtual Wallets** | Each agent/org has a $SURGE wallet with balance enforcement. Auto-provisioned on first call (100 SURGE). Returns 402 Payment Required when empty |
| **Fee Enforcement** | When enabled, `/evaluate` checks wallet balance *before* running the pipeline. Zero balance = zero access |
| **Policy Staking** | Operators stake $SURGE on policies to signal confidence — DB-persisted with unstake support |
| **Token-Aware Policies** | Built-in rules for `surge_launch`, `surge_trade`, `surge_transfer`, `surge_transfer_ownership` |

### Fee tiers

| Risk Score | Fee per Evaluation |
|-----------|-------------------|
| 0–39 (standard) | 0.001 $SURGE |
| 40–69 (elevated) | 0.005 $SURGE |
| 70–89 (high) | 0.010 $SURGE |
| 90–100 (critical) | 0.025 $SURGE |

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

## DeFi Research Agent Demo

[`demo_agent.py`](demo_agent.py) is an end-to-end live governance demo — an autonomous DeFi research agent that makes real tool calls through the Governor, progressing from safe research to dangerous operations, with full verification and conversation logging.

| Phase | Tools | Expected Outcome |
|-------|-------|------------------|
| 1. Safe Research | `fetch_price`, `read_contract` | ✅ ALLOW |
| 2. DeFi Analysis | `analyze_liquidity`, `query_pool`, `calculate_impermanent_loss` | ✅ ALLOW |
| 3. Trade Execution | `execute_swap`, `http_request`, `messaging_send` | ⚠️ REVIEW |
| 4. Dangerous Ops | `shell rm -rf`, `surge_transfer_ownership`, credential exfil | 🚫 BLOCK |
| 5. Attack Chain | scope violation, injection attempt, `base64_decode` | 🚫 BLOCK + chain detection |
| 6. Verification | 8 scenarios (compliant + violation) | ✅ 8/8 verified |

Every evaluation includes `trace_id`/`span_id` and `conversation_id`, so the full session appears in the **Trace Viewer** and **Conversations** tab with governance decisions inline.

```bash
# Run against local server
python demo_agent.py

# Run against production
python demo_agent.py --url https://openclaw-governor.fly.dev

# Show full execution trace per evaluation
python demo_agent.py --verbose

# Enable SURGE fee gating (shows wallet depletion)
python demo_agent.py --fee-gating
```

Sample output: **17 evaluations** → 9 allowed, 2 reviewed, 6 blocked, avg risk 45.9. **8/8 verification scenarios** pass. Chain analysis detects `browse-then-exfil` and `credential-then-http` patterns. 5 conversation turns and 22+ trace spans persisted.

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
| `GET` | `/surge/status` | Any | SURGE integration status (tiered fees, totals) |
| `GET` | `/surge/receipts` | Any | List governance receipts (DB-persisted) |
| `GET` | `/surge/receipts/{id}` | Any | Get specific receipt by ID |
| `POST` | `/surge/policies/stake` | Operator+ | Stake $SURGE on a policy |
| `GET` | `/surge/policies/staked` | Any | List all staked policies |
| `DELETE` | `/surge/policies/stake/{id}` | Operator+ | Unstake a policy |
| `POST` | `/surge/wallets` | Operator+ | Create virtual $SURGE wallet |
| `GET` | `/surge/wallets` | Any | List all wallets |
| `GET` | `/surge/wallets/{id}` | Any | Get wallet balance |
| `POST` | `/surge/wallets/{id}/topup` | Operator+ | Deposit $SURGE into wallet |

### Traces — Agent Lifecycle Observability
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/traces/ingest` | Operator+ | Batch ingest agent trace spans (up to 500, idempotent) |
| `GET` | `/traces` | Any | List traces with summary (`?agent_id=`, `?has_blocks=true`) |
| `GET` | `/traces/{trace_id}` | Any | Full trace: all spans + correlated governance decisions |
| `DELETE` | `/traces/{trace_id}` | Operator+ | Delete all spans for a trace |

### Verification — Post-Execution Checks
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/actions/verify` | Operator+ | Run 8-check verification on tool execution result |
| `GET` | `/actions/verifications` | Any | List verification logs (`?verdict=`, `?agent_id=`) |

### Conversations — Agent Reasoning Capture
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/conversations` | Any | List all conversations with turn counts |
| `GET` | `/conversations/{id}/turns` | Any | Get turns for a conversation |
| `GET` | `/conversations/{id}/timeline` | Any | Unified timeline: turns + actions interleaved |
| `POST` | `/conversations/turns/batch` | Operator+ | Batch ingest conversation turns (encrypted at rest) |
| `POST` | `/conversations/turns` | Operator+ | Ingest single conversation turn |
| `GET` | `/conversations/stats` | Any | Conversation statistics |

### Escalation
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/escalation/events` | Any | List escalation events (`?status=`, `?severity=`) |
| `PUT` | `/escalation/events/{id}/approve` | Admin | Approve a pending escalation |
| `PUT` | `/escalation/events/{id}/reject` | Admin | Reject a pending escalation |
| `GET` | `/escalation/config` | Admin | Get escalation thresholds |
| `PUT` | `/escalation/config` | Admin | Update escalation thresholds |

### Notifications
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/notifications/channels` | Any | List notification channels |
| `POST` | `/notifications/channels` | Admin | Create notification channel (email/slack/whatsapp/jira/webhook) |
| `PUT` | `/notifications/channels/{id}` | Admin | Update channel config |
| `DELETE` | `/notifications/channels/{id}` | Admin | Delete a channel |

---

## Testing

```bash
# Backend — 246 tests across 8 test files
cd governor-service && pytest tests/ -v
# Includes: governance pipeline, conversations, verification, escalation,
#           policies+versioning, SSE streaming, traces, and notification channels

# TypeScript/JS SDK — 10 tests
cd openclaw-skills/governed-tools/js-client && npm test

# Java SDK — 11 tests
cd openclaw-skills/governed-tools/java-client && mvn test
```

---

## Deployment

| Component | Platform | URL | Config |
|-----------|----------|-----|--------|
| Governor Service (primary) | Fly.io | `https://openclaw-governor.fly.dev` | [`fly.toml`](governor-service/fly.toml), [`Dockerfile`](governor-service/Dockerfile) |
| Governor Service (standby) | Vultr VPS | `http://45.76.141.204:8000` | [`vultr/docker-compose.yml`](governor-service/vultr/docker-compose.yml) |
| Dashboard (primary) | Vercel | `https://openclaw-runtime-governor.vercel.app` | [`vercel.json`](dashboard/vercel.json) |
| Dashboard (mirror) | Vercel | `https://openclaw-runtime-governor-j9py.vercel.app` | Same source |
| Dashboard (standby) | Vultr VPS | `http://45.76.141.204:3000` | Docker (Next.js standalone) |

Both backends run PostgreSQL 16 with 17 tables. Data persists across container restarts and redeployments.

See [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) for the comprehensive guide, [`DEPLOY.md`](DEPLOY.md) for deployment details, [`PUBLISHING.md`](PUBLISHING.md) for SDK publishing, [`DEVELOPER.md`](DEVELOPER.md) for contributor quick-reference.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Pydantic 2.8 |
| Real-time | Server-Sent Events (SSE), asyncio event bus |
| Auth | bcrypt, python-jose (JWT HS256), slowapi rate limiting, RBAC (4 roles) |
| Database | SQLite (dev) / PostgreSQL 16 (prod) — 17 tables |
| Encryption | Fernet symmetric (conversation prompts at rest) |
| Dashboard | Next.js 14.2, React 18.3, TypeScript — 16 tabs |
| SDKs | Python (httpx), TypeScript/JS (fetch), Java (HttpClient) |
| Deployment | Fly.io + Vultr VPS (backend), Vercel × 2 + Vultr (dashboard) |
| CI/CD | GitHub Actions (dashboard), Docker Compose (Vultr) |

---

## License

[MIT](LICENSE) — Copyright © 2026 Sovereign AI Lab
