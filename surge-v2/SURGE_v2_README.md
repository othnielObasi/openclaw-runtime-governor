# SURGE v2 — Sovereign Unified Runtime Governance Engine

> Cryptographic proof that every AI agent action was governed — on your infrastructure, under your jurisdiction, mapped to your regulations.

**47 tests passing** · Zero external dependencies · Python 3.9+ · EU AI Act ready

---

## What SURGE Does

Every time the NOVTIA Governor evaluates a tool call, SURGE issues a **governance receipt** — a cryptographically signed record proving that a specific agent action was evaluated at a specific time, on specific infrastructure, and received a specific governance decision.

Receipts are **hash-chained**: each receipt includes the SHA-256 digest of the previous receipt. Alter any single record and the entire chain breaks. This isn't an audit log that can be edited. It's a tamper-evident chain that any third party can independently verify.

**For regulated enterprises:** SURGE generates the compliance evidence your auditors need — not after the fact, but automatically, for every governance decision, tagged to the exact regulation it satisfies.

**For sovereign AI deployments:** Every receipt attests that governance happened on your infrastructure, in your jurisdiction, with zero external API calls. No US hyperscaler touched the decision. The receipt proves it.

---

## Architecture

```
Agent requests tool call
        │
        ▼
┌──────────────────┐
│ Governor Pipeline │  Layers 0-6: Budget, PII, Injection,
│ (evaluate)       │  Scope, Trust, Policy, Chain Analysis
└────────┬─────────┘
         │ decision
         ▼
┌──────────────────────────────────────────────────┐
│                   SURGE v2                        │
│                                                   │
│  ┌─────────┐   ┌──────────┐   ┌──────────────┐  │
│  │ Receipt  │──▶│  Hash    │──▶│  Compliance  │  │
│  │ Builder  │   │  Chain   │   │  Tagger      │  │
│  └─────────┘   └──────────┘   └──────────────┘  │
│       │              │               │            │
│       ▼              ▼               ▼            │
│  ┌─────────┐   ┌──────────┐   ┌──────────────┐  │
│  │Sovereign│   │  Merkle  │   │  EU AI Act   │  │
│  │Attestor │   │  Tree    │   │  NIST · OWASP│  │
│  └─────────┘   └──────────┘   └──────────────┘  │
│                      │                            │
│                      ▼                            │
│              ┌──────────────┐                     │
│              │   Export     │                     │
│              │   Bundle     │──▶ Auditor JSON     │
│              └──────────────┘                     │
└──────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Initialise the Engine

```python
from surge import SurgeEngine, SovereignConfig

surge = SurgeEngine(
    config=SovereignConfig(
        deployment_id="novtia-uk-prod-001",
        jurisdiction="GB",                  # ISO 3166-1
        operator="Acme Financial Services",
        infrastructure="on-premise",        # on-premise | private-cloud | sovereign-cloud
        data_residency="GB",
        classification="OFFICIAL",          # UK govt classification
    ),
    checkpoint_interval=100,  # Merkle checkpoint every 100 receipts
)
```

### 2. Issue Receipts (in your evaluation pipeline)

```python
receipt = surge.issue(
    tool="patient_lookup",
    decision="allow",
    risk_score=15,
    explanation="Low risk, within scope, no PII in args",
    policy_ids=["pol_nhs_data_access"],
    chain_pattern=None,
    agent_id="agent_triage_001",
    session_id="sess_abc123",
)

# receipt.digest       → SHA-256 of this receipt
# receipt.previous_digest → SHA-256 of previous receipt (chain link)
# receipt.sovereign    → {deployment_id, jurisdiction, operator, ...}
# receipt.compliance   → {eu_ai_act: ["Art.9", "Art.12", ...], ...}
```

### 3. Verify Chain Integrity

```python
result = surge.verify_chain()
# result.valid            → True if entire chain is intact
# result.receipts_checked → Number verified
# result.first_broken_at  → Sequence number where tampering detected (if any)
```

### 4. Export for Auditors

```python
bundle = surge.export(
    period_start="2026-01-01",
    period_end="2026-03-31",
)

# bundle.chain_valid          → True/False
# bundle.summary              → {decisions, block_rate, eu_ai_act_coverage, ...}
# bundle.receipts             → Full receipt chain for the period
# bundle.checkpoints          → Merkle checkpoints covering the period
# bundle.verification_instructions → How to independently verify the chain
```

### 5. Mount API Routes

```python
from surge.router import router as surge_router
app.include_router(surge_router, prefix="/surge")
```

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/surge/status` | Engine status and chain integrity |
| `POST` | `/surge/issue` | Issue a governance receipt |
| `GET` | `/surge/receipts` | List receipts (filterable by agent, decision) |
| `GET` | `/surge/receipts/{id}` | Get specific receipt |
| `GET` | `/surge/receipts/{id}/verify` | Verify single receipt integrity |
| `POST` | `/surge/checkpoint` | Create Merkle checkpoint |
| `GET` | `/surge/checkpoints` | List all checkpoints |
| `GET` | `/surge/verify` | Verify entire chain |
| `GET` | `/surge/export` | Download auditor-ready compliance bundle |

---

## Cryptographic Chain

### How It Works

```
Genesis: SHA256("NOVTIA_SURGE_GENESIS_v2")
   │
   ▼
Receipt 0:
   payload = "surge-abc...|0|2026-03-01T...|shell|block|95|pol_1|...|{genesis_hash}"
   digest  = SHA256(payload)
   previous_digest = genesis_hash
   │
   ▼
Receipt 1:
   payload = "surge-def...|1|2026-03-01T...|http_get|allow|10|...|{receipt_0_digest}"
   digest  = SHA256(payload)
   previous_digest = receipt_0.digest
   │
   ▼
Receipt 2:
   payload = "surge-ghi...|2|...|{receipt_1_digest}"
   ...
```

Each receipt's digest includes the previous receipt's digest in its payload. Changing any field in any receipt produces a different SHA-256, which breaks the chain link for every subsequent receipt.

### Merkle Checkpoints

Every N receipts (default: 100), the engine computes a Merkle tree root:

```
         Merkle Root
        /           \
    H(0+1)        H(2+3)
    /    \        /    \
  R0.digest  R1.digest  R2.digest  R3.digest
```

One hash represents the integrity of an entire batch. An auditor can verify 10,000 receipts by checking 100 Merkle roots.

### Independent Verification

The export bundle includes plain-English instructions for verifying the chain using any SHA-256 implementation:

1. Start from genesis hash
2. For each receipt: reconstruct payload string, compute SHA-256, confirm it matches
3. Confirm each `previous_digest` links to the prior receipt
4. For each checkpoint: recompute Merkle root from leaf digests

No NOVTIA software required. Any SHA-256 tool works (`openssl`, Python `hashlib`, browser crypto API).

---

## Compliance Framework Mapping

### EU AI Act

Every receipt is automatically tagged with the Articles it provides evidence for:

| Article | Title | When Tagged |
|---------|-------|-------------|
| **Art.9** | Risk Management System | Block/review decisions, risk scores, chain analysis |
| **Art.12** | Record-Keeping | **Every receipt** — automatic event logging |
| **Art.13** | Transparency | Explanations, risk scores, policy references |
| **Art.14** | Human Oversight | Kill switch, review decisions, escalations |
| **Art.15** | Accuracy, Robustness, Cybersecurity | Injection detection, verification, drift |
| **Art.17** | Quality Management System | Policy creation/updates, audit exports |
| **Art.26** | Obligations of Deployers | Monitoring, risk scoring, audit trails |

### NIST AI RMF

| Reference | Function | When Tagged |
|-----------|----------|-------------|
| GOVERN-1.1 | Policy enforcement | Any evaluation with policy_ids |
| MAP-1.1 | Risk identification | Risk scores, chain analysis |
| MEASURE-2.1 | Continuous monitoring | Every receipt |
| MANAGE-1.1 | Risk treatment | Block/review decisions |
| MANAGE-2.1 | Incident response | Kill switch, escalations |

### OWASP Top 10 for LLM 2025

| Reference | Risk | When Tagged |
|-----------|------|-------------|
| LLM01 | Prompt Injection | Injection detected in explanation |
| LLM02 | Sensitive Info Disclosure | PII/credential findings |
| LLM05 | Improper Output Handling | Verification failures |
| LLM06 | Excessive Agency | Scope violations, blocks, kill switch |
| LLM10 | Unbounded Consumption | Budget exceeded, rate limited |

---

## Sovereign Attestation

Every receipt embeds:

```json
{
  "sovereign": {
    "deployment_id": "novtia-uk-nhs-001",
    "jurisdiction": "GB",
    "operator": "NHS Digital",
    "infrastructure": "on-premise",
    "data_residency": "GB",
    "classification": "OFFICIAL"
  }
}
```

This proves:
- **Where** governance happened (jurisdiction + data residency)
- **Who** operated it (operator)
- **How** it was deployed (infrastructure type)
- **What** classification level applies

For EU/UK sovereign AI procurement, this is the evidence that no foreign dependency was involved in governance decisions.

---

## Export Bundle Structure

The `/surge/export` endpoint produces a self-contained JSON file:

```json
{
  "exported_at": "2026-03-01T12:00:00+00:00",
  "deployment": { "deployment_id": "...", "jurisdiction": "GB", ... },
  "period_start": "2026-01-01",
  "period_end": "2026-03-31",
  "total_receipts": 8472,
  "chain_valid": true,
  "summary": {
    "total_receipts": 8472,
    "decisions": { "allow": 7891, "block": 412, "review": 169 },
    "block_rate_pct": 4.87,
    "avg_risk_score": 14.2,
    "unique_tools": 12,
    "unique_agents": 6,
    "eu_ai_act_coverage": {
      "Art.12": 8472, "Art.9": 581, "Art.13": 8472,
      "Art.14": 169, "Art.15": 87
    },
    "chain_integrity": "VERIFIED"
  },
  "checkpoints": [ ... ],
  "receipts": [ ... ],
  "verification_instructions": "..."
}
```

Hand this file to your auditor. They can independently verify every hash.

---

## Running Tests

```bash
cd surge_v2
pip install pytest fastapi
PYTHONPATH=. pytest tests/ -v
```

**Expected: 47 passed**

Test coverage:
- Receipt issuance and sequencing (4 tests)
- Hash chain integrity (4 tests)
- Tamper detection — digest, chain link, payload modification (5 tests)
- Merkle checkpoints — creation, determinism, auto-checkpoint (8 tests)
- Compliance tagging — EU AI Act, NIST, OWASP (9 tests)
- Export bundle — serialisation, filtering, coverage (6 tests)
- Query and status (4 tests)
- Edge cases — unicode, large chains, empty inputs (5 tests)

---

## Migration from SURGE v1

SURGE v1 (hackathon version) used token staking and wallet addresses. v2 strips all token economy and replaces it with:

| v1 (Hackathon) | v2 (Production) |
|---|---|
| `governance_fee_surge` | Removed |
| `staker_wallet` | Removed |
| `PolicyStake` model | Removed |
| Single SHA-256 per receipt | Hash-chained receipts |
| No checkpoints | Merkle tree checkpoints |
| No compliance tags | EU AI Act + NIST + OWASP tags |
| No sovereign attestation | Full deployment/jurisdiction attestation |
| No export | Auditor-ready JSON bundle |

To migrate: replace `from routes_surge import create_governance_receipt` with `from surge import SurgeEngine` and update the call signature (see Quick Start above).

---

## Requirements

```
fastapi>=0.100.0    # For API router only
pydantic>=2.0.0     # For API router only
```

The core engine (`surge/__init__.py`) uses Python stdlib only — `hashlib`, `uuid`, `datetime`, `json`. Zero external dependencies for the cryptographic layer.

---

**Built by Othniel Obasi · NOVTIA · March 2026**
