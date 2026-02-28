# Governance Coverage Audit

**Date:** 2026-02-28  
**Trigger:** External feedback on agent governance verification gaps  
**Auditor:** Copilot / Engineering

---

## Feedback Summary

> Governance for autonomous agents is tricky — you're trying to create safety constraints that don't break the agent's ability to be actually useful. The challenge I see most often isn't the policy framework, it's verification.
>
> You can write perfect governance rules. But how do you know the agent is actually following them at runtime?

The feedback identified three safety patterns:

1. **Clear governance rules** (policy-as-code)
2. **Diff verification on every change** (independent post-execution review)
3. **Conversation history analysis** (catch deviation and hallucination)

And three agent failure modes:

- Implement workarounds that technically pass the policy
- Drift from intended behavior over time
- Find edge cases that bypass constraints

---

## What We Have Today

### Layer Architecture

```
Agent → POST /actions/evaluate
         │
         ├─ Layer 1: Kill Switch        (DB-persisted, blocks everything if on)
         ├─ Layer 2: Injection Firewall  (20 regex patterns, Unicode NFKC normalization)
         ├─ Layer 3: Scope Enforcer      (allowed_tools whitelist)
         ├─ Layer 4: Policy Engine       (11 YAML + dynamic DB policies, regex matching)
         ├─ Layer 5: Neuro Estimator     (keyword/tool/cardinality heuristics)
         │           + Chain Analysis    (6 multi-step attack patterns from session history)
         │
         ├─ Trace Span auto-created (correlated by trace_id)
         ├─ SURGE Receipt generated (on-chain attestation)
         ├─ SSE broadcast to dashboard
         └─ Escalation Engine:
              ├─ Review queue entry (pending → approve/reject/expire)
              ├─ Auto-kill-switch check (block count / avg risk threshold)
              └─ Notifications: Email, Slack, WhatsApp, Jira, Webhook
```

### 1. Governance Rules — STRONG ✅

| Component | Detail |
|-----------|--------|
| **5-layer pipeline** | Kill switch → injection firewall → scope enforcer → policy engine → neuro+chain. Short-circuits on first block. |
| **11 base policies** | Destructive commands, privilege escalation, credential exfiltration, bulk messaging, SURGE operations (YAML-based, always loaded) |
| **Dynamic policies** | CRUD via API, regex matching on tool names, URLs, and flattened args |
| **Policy versioning** | Every edit creates an immutable `PolicyVersion` snapshot + `PolicyAuditLog` with before/after JSON diffs |
| **Kill switch** | Global emergency stop — manual via admin API or auto-triggered by escalation engine |
| **SURGE fee gating** | Agents must hold token balance to use governance (economic disincentive) |
| **RBAC** | 4 roles: superadmin, admin, operator, auditor — JWT + API key auth |

### 2. Conversation History / Chain Analysis — SOLID ✅

| Component | Detail |
|-----------|--------|
| **Session store** | Reconstructs last 60 min / 50 actions per agent+session from the `action_logs` table |
| **6 chain patterns** | See table below |
| **Risk escalation** | Chain match + risk ≥ 80 auto-promotes `allow` → `review` |
| **Auto-kill-switch** | 3 blocks OR avg risk ≥ 82 in last 10 actions → global shutdown |

**Chain patterns detected:**

| Pattern | Risk Boost | Min Actions | What It Catches |
|---------|-----------|-------------|-----------------|
| `repeated-scope-probing` | +60 | 2 | Agent repeatedly tries tools outside its scope |
| `credential-then-http` | +55 | 2 | Credential access followed by external HTTP call (exfiltration) |
| `read-write-exec` | +45 | 3 | file_read → file_write → shell execution (lateral movement) |
| `block-bypass-retry` | +40 | 2 | Agent retries previously blocked tools (defiance) |
| `browse-then-exfil` | +35 | 2 | HTTP browse → messaging send (data theft) |
| `rapid-tool-switching` | +30 | 3 | ≥3 high-risk tool types in last 5 calls (confusion attack) |

### 3. Anti-Evasion / Injection Defense — SOLID ✅

| Component | Detail |
|-----------|--------|
| **20 regex patterns** | Covers prompt injection, jailbreak phrases, destructive shell commands, code injection (`eval(`, `os.system(`, etc.) |
| **Unicode NFKC normalization** | Defeats homoglyph attacks (e.g., Cyrillic "а" for Latin "a") |
| **Zero-width character stripping** | Prevents invisible character obfuscation |
| **Flattened payload matching** | Args are recursively flattened to a string before regex matching — can't hide dangerous strings in nested JSON |

### 4. Observability / Audit Trail — STRONG ✅

| Component | Detail |
|-----------|--------|
| **Action logs** | Every evaluated action stored with tool, args, context, decision, risk, matched policies |
| **Trace correlation** | Governance decisions auto-injected as `governance` spans in agent trace trees |
| **Unified timeline** | `GET /traces/{trace_id}` merges agent spans + governance decisions into one view |
| **Policy audit log** | Who changed what policy, when, with before/after diffs |
| **Login history** | Every auth event with IP and user-agent |
| **SSE streaming** | Real-time dashboard feed of all governance decisions |

### 5. Escalation & Alerting — STRONG ✅

| Component | Detail |
|-----------|--------|
| **Review queue** | Block/review decisions create pending events (approve/reject/expire) |
| **Auto-kill-switch** | Threshold-based automatic global shutdown |
| **5 notification channels** | Email (SMTP), Slack (webhook + Bot API), WhatsApp (Meta Cloud API), Jira (issue creation), generic webhook |
| **Per-agent config** | Escalation thresholds can be set globally or per-agent |
| **Severity derivation** | Auto-computed from risk score + decision + chain pattern |

---

## What We're Missing

### GAP 1: Post-Execution Verification — NOT IMPLEMENTED ❌

**The core issue:** We gate the agent's *intent* (tool name + args) before execution. We never see the *result*. An agent could:

- Call an allowed tool but use it in an unintended way
- Produce output that technically "passed" the policy but violates governance intent
- Modify files/state in ways the pre-execution check couldn't predict

**What the feedback recommends:**
> Every agent modification should pass through a verification layer that asks: "Did this change comply with our safety model? Does it align with our governance intent?"

**Current flow (pre-execution only):**
```
Agent → "I want to call file_write" → Governor evaluates intent → allow/block
                                                                      ↓
Agent executes file_write ← no verification of what was actually written
```

**Desired flow (pre + post):**
```
Agent → "I want to call file_write" → Governor evaluates intent → allow
                                                                      ↓
Agent executes file_write → "Here's what I wrote" → Governor verifies result
                                                                      ↓
                                                          compliance/violation
```

**Impact:** This is the single highest-value addition. Without it, we're trusting that allowing the intent means the execution will be safe.

### GAP 2: Independent Verifier Agent — NOT IMPLEMENTED ❌

**What the feedback describes:** For safety-critical changes, spawn a second agent with read-only access to independently audit the diff. A "second pair of eyes" that specifically watches for governance violations.

**Our equivalent:** None. We have automated policy checks but no independent AI reviewer. This is a more advanced version of Gap 1 — instead of a rule-based post-execution check, use an LLM to reason about whether the change is safe.

**Priority:** Lower than Gap 1. Rule-based verification covers most cases; LLM-based review is for edge cases. Can be added later as an optional layer.

### GAP 3: Semantic Output Analysis — NOT IMPLEMENTED ❌

**What it is:** Inspect the agent's *text responses* (not just tool calls) for hallucination, contradiction with stated goals, or prompt injection embedded in outputs.

**Current state:** Our chain analysis only looks at tool call sequences. We don't analyze the conversational content between tool calls.

**Priority:** Low. Most governance risk lives in tool execution, not text output. The ROI of inspecting responses is lower than inspecting tool results.

### GAP 4: Cross-Session Drift Detection — PARTIAL ⚠️

**What we have:** Intra-session chain analysis (last 60 min / 50 actions within one session).

**What we're missing:**
- Cross-session behavioral profiling (is this agent acting differently than it did yesterday?)
- Baseline behavior models per agent
- Goal alignment tracking (is the agent still pursuing its original objective?)

**Priority:** Medium. Useful for long-running agents but not critical for most use cases.

---

## Recommendation

### Implement Now: Post-Execution Verification (`POST /actions/verify`)

**Scope:** ~300-400 lines across:
- New route: `routes_verify.py`
- Verification engine: `verification/engine.py`
- New model: `VerificationLog`
- Schema additions to `schemas.py`
- Trace correlation for verification spans

**Design concept:**

```python
# Agent calls after tool execution:
POST /actions/verify
{
    "action_id": "uuid-from-evaluate-response",
    "tool": "file_write",
    "result": {
        "status": "success",
        "output": "Wrote 42 lines to /app/config.py",
        "diff": "- old_setting = false\n+ old_setting = true"
    },
    "context": {
        "agent_id": "agent-1",
        "session_id": "session-abc",
        "trace_id": "trace-xyz"
    }
}

# Governor responds:
{
    "verification": "compliant" | "violation" | "suspicious",
    "risk_delta": 15,
    "findings": [
        {
            "check": "output-credential-scan",
            "result": "pass",
            "detail": "No credentials detected in output"
        },
        {
            "check": "scope-compliance",
            "result": "pass",
            "detail": "Modified file matches allowed scope"
        }
    ],
    "escalated": false
}
```

**Verification checks to implement:**
1. **Credential leak scan** — check result/output/diff for secrets, API keys, tokens
2. **Scope compliance** — if the tool wrote to a file or URL, is it within the agent's declared scope?
3. **Destructive output detection** — scan for dangerous patterns in the output (SQL drops, file deletions, etc.)
4. **Diff size anomaly** — flag unexpectedly large changes
5. **Result-intent alignment** — compare the original `evaluate` request against the reported result
6. **Chain context update** — feed the verified result back into chain analysis for richer pattern detection

### Defer: Gaps 2, 3, 4

- **Independent verifier agent** — add later as an optional "deep review" mode for critical actions
- **Semantic output analysis** — requires LLM integration, introduces latency and complexity
- **Cross-session drift** — useful but lower priority than closing the pre/post gap

---

## Summary Matrix

| Feedback Point | Our Coverage | Rating | Action |
|---|---|---|---|
| Clear governance rules | 5-layer pipeline, 11+ policies, versioning, kill switch, SURGE gating | **Strong** ✅ | None needed |
| Diff verification on every change | Pre-execution gating only; no post-execution inspection | **Gap** ❌ | **Implement `POST /actions/verify`** |
| Conversation history analysis | 6-pattern chain analysis on tool sequences; no LLM output analysis | **Partial** ⚠️ | Defer semantic analysis |
| Agent workaround detection | Injection firewall + Unicode normalization + chain retries; no semantic intent | **Partial** ⚠️ | Partially addressed by verify |
| Behavioral drift over time | Intra-session chain analysis; no cross-session baselining | **Partial** ⚠️ | Defer |
| Independent verifier agent | Not implemented | **Gap** ❌ | Defer |

### Strengths not mentioned in feedback:
- SURGE economic gating (agents pay to use governance)
- Multi-channel escalation (5 notification integrations)
- Immutable audit trail with policy versioning
- Trace correlation (governance decisions in agent observability)
- Auto-kill-switch (automatic emergency shutdown)
- Real-time SSE dashboard streaming
