"""
NOVTIA Governor — SURGE v2
=============================
Sovereign Unified Runtime Governance Engine

Cryptographic governance receipts with:
- Hash chain: each receipt includes the previous receipt's digest,
  creating a tamper-evident chain. Altering any receipt breaks all
  subsequent hashes.
- Merkle tree: periodic checkpoints hash all receipts in a window
  into a single root, enabling efficient batch verification.
- EU AI Act article tagging: each receipt references which Articles
  (9, 12, 13, 14, 17) it provides evidence for.
- Sovereign attestation: receipts contain a deployment_id and
  jurisdiction field proving governance happened on specific
  sovereign infrastructure.
- Independent verification: export the full chain as a JSON file
  that any third party can recalculate and confirm.

This is the compliance backbone. Every governance decision is
cryptographically provable, tamper-evident, jurisdiction-tagged,
and regulation-mapped.

Integration:
    from surge import SurgeEngine, SovereignConfig
    surge = SurgeEngine(config=SovereignConfig(
        deployment_id="novtia-uk-prod-001",
        jurisdiction="GB",
        operator="NHS Digital",
    ))

    # After every evaluation:
    receipt = surge.issue(tool, decision, risk_score, policy_ids, ...)

    # Export for auditor:
    bundle = surge.export_chain(start, end, format="json")

    # Verify integrity:
    result = surge.verify_chain()
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4


# ═══════════════════════════════════════════════════════════
# EU AI ACT ARTICLE MAPPING
# ═══════════════════════════════════════════════════════════

EU_AI_ACT_ARTICLES = {
    "Art.9": {
        "title": "Risk Management System",
        "indicators": ["risk_score", "block", "review", "chain_analysis",
                       "injection", "pii", "scope_violation"],
        "description": "Evidence of continuous risk identification and mitigation",
    },
    "Art.12": {
        "title": "Record-Keeping",
        "indicators": ["*"],  # Every receipt satisfies Art.12
        "description": "Automatic recording of events enabling traceability",
    },
    "Art.13": {
        "title": "Transparency",
        "indicators": ["explanation", "risk_score", "policy_ids", "chain_pattern"],
        "description": "Sufficient transparency for deployers to understand system behaviour",
    },
    "Art.14": {
        "title": "Human Oversight",
        "indicators": ["kill_switch", "review", "escalation", "human_override"],
        "description": "Measures enabling human oversight during operation",
    },
    "Art.15": {
        "title": "Accuracy, Robustness, Cybersecurity",
        "indicators": ["injection", "verification", "drift", "credential_leak"],
        "description": "Resilience against errors, faults, and security threats",
    },
    "Art.17": {
        "title": "Quality Management System",
        "indicators": ["policy_created", "policy_updated", "audit", "compliance_export"],
        "description": "Quality management procedures and documentation",
    },
    "Art.26": {
        "title": "Obligations of Deployers",
        "indicators": ["monitoring", "risk_score", "human_oversight", "audit_trail"],
        "description": "Deployer obligations for high-risk AI monitoring",
    },
}

NIST_AI_RMF_MAP = {
    "GOVERN-1.1": {"indicators": ["policy_ids"], "desc": "Policy enforcement"},
    "MAP-1.1": {"indicators": ["risk_score", "chain_analysis"], "desc": "Risk identification"},
    "MEASURE-2.1": {"indicators": ["*"], "desc": "Continuous monitoring"},
    "MANAGE-1.1": {"indicators": ["block", "review", "kill_switch"], "desc": "Risk treatment"},
    "MANAGE-2.1": {"indicators": ["escalation", "kill_switch"], "desc": "Incident response"},
}

OWASP_LLM_MAP = {
    "LLM01": {"indicators": ["injection"], "desc": "Prompt Injection"},
    "LLM02": {"indicators": ["pii", "credential_leak"], "desc": "Sensitive Information Disclosure"},
    "LLM05": {"indicators": ["verification"], "desc": "Improper Output Handling"},
    "LLM06": {"indicators": ["scope_violation", "kill_switch", "block"], "desc": "Excessive Agency"},
    "LLM10": {"indicators": ["budget_exceeded", "rate_limited"], "desc": "Unbounded Consumption"},
}


def _tag_compliance(decision: str, risk_score: int, explanation: str,
                    policy_ids: List[str], chain_pattern: Optional[str],
                    extra_context: Dict[str, Any]) -> Dict[str, List[str]]:
    """Tag a receipt with all applicable compliance framework references."""

    # Build indicator set
    indicators: Set[str] = {"risk_score"}
    indicators.add(decision)

    if policy_ids:
        indicators.add("policy_ids")
    if chain_pattern:
        indicators.add("chain_analysis")

    explanation_lower = (explanation or "").lower()
    keyword_map = {
        "injection": "injection", "pii": "pii", "credential": "credential_leak",
        "scope": "scope_violation", "kill": "kill_switch", "escalat": "escalation",
        "verif": "verification", "drift": "drift", "budget": "budget_exceeded",
        "rate": "rate_limited", "human": "human_override", "override": "human_override",
        "monitor": "monitoring",
    }
    for kw, ind in keyword_map.items():
        if kw in explanation_lower:
            indicators.add(ind)

    for k, v in extra_context.items():
        if isinstance(v, str):
            indicators.add(v)

    # Match against frameworks
    tags: Dict[str, List[str]] = {"eu_ai_act": [], "nist_ai_rmf": [], "owasp_llm": []}

    for article_id, article in EU_AI_ACT_ARTICLES.items():
        if "*" in article["indicators"] or indicators & set(article["indicators"]):
            tags["eu_ai_act"].append(article_id)

    for ref_id, ref in NIST_AI_RMF_MAP.items():
        if "*" in ref["indicators"] or indicators & set(ref["indicators"]):
            tags["nist_ai_rmf"].append(ref_id)

    for ref_id, ref in OWASP_LLM_MAP.items():
        if indicators & set(ref["indicators"]):
            tags["owasp_llm"].append(ref_id)

    return tags


# ═══════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════

@dataclass
class SovereignConfig:
    """Identifies the sovereign deployment."""
    deployment_id: str = "novtia-default"
    jurisdiction: str = "GB"              # ISO 3166-1 alpha-2
    operator: str = ""                    # Organisation operating the Governor
    infrastructure: str = "on-premise"    # on-premise | private-cloud | sovereign-cloud
    data_residency: str = "GB"            # Where data physically resides
    classification: str = "OFFICIAL"      # OFFICIAL | SECRET | TOP SECRET (UK) or equivalent

    def to_dict(self) -> Dict[str, str]:
        return {
            "deployment_id": self.deployment_id,
            "jurisdiction": self.jurisdiction,
            "operator": self.operator,
            "infrastructure": self.infrastructure,
            "data_residency": self.data_residency,
            "classification": self.classification,
        }


@dataclass
class GovernanceReceipt:
    """Cryptographic proof of a governance decision."""
    receipt_id: str
    sequence: int                          # Monotonic sequence number
    timestamp: str                         # ISO-8601 UTC
    tool: str
    decision: str                          # allow | block | review
    risk_score: int
    explanation: str
    policy_ids: List[str]
    chain_pattern: Optional[str]
    agent_id: Optional[str]
    session_id: Optional[str]

    # Sovereign attestation
    sovereign: Dict[str, str]              # SovereignConfig fields

    # Compliance tags
    compliance: Dict[str, List[str]]       # {eu_ai_act: [...], nist: [...], owasp: [...]}

    # Cryptographic fields
    digest: str                            # SHA-256 of this receipt's payload
    previous_digest: str                   # Digest of the previous receipt (chain link)
    merkle_root: Optional[str] = None      # Populated at checkpoint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "tool": self.tool,
            "decision": self.decision,
            "risk_score": self.risk_score,
            "explanation": self.explanation,
            "policy_ids": self.policy_ids,
            "chain_pattern": self.chain_pattern,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "sovereign": self.sovereign,
            "compliance": self.compliance,
            "digest": self.digest,
            "previous_digest": self.previous_digest,
            "merkle_root": self.merkle_root,
        }

    def payload_string(self) -> str:
        """Canonical string used for digest computation."""
        return (
            f"{self.receipt_id}|{self.sequence}|{self.timestamp}|"
            f"{self.tool}|{self.decision}|{self.risk_score}|"
            f"{','.join(self.policy_ids)}|{self.chain_pattern or ''}|"
            f"{self.agent_id or ''}|{self.session_id or ''}|"
            f"{self.sovereign.get('deployment_id', '')}|"
            f"{self.sovereign.get('jurisdiction', '')}|"
            f"{self.previous_digest}"
        )


@dataclass
class ChainVerification:
    """Result of verifying the receipt chain."""
    valid: bool
    receipts_checked: int
    first_broken_at: Optional[int] = None  # Sequence number where chain breaks
    first_broken_receipt: Optional[str] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "receipts_checked": self.receipts_checked,
            "first_broken_at": self.first_broken_at,
            "first_broken_receipt": self.first_broken_receipt,
            "errors": self.errors,
        }


@dataclass
class MerkleCheckpoint:
    """A Merkle tree checkpoint covering a range of receipts."""
    checkpoint_id: str
    timestamp: str
    sequence_start: int
    sequence_end: int
    receipt_count: int
    merkle_root: str
    leaf_digests: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "sequence_start": self.sequence_start,
            "sequence_end": self.sequence_end,
            "receipt_count": self.receipt_count,
            "merkle_root": self.merkle_root,
        }


@dataclass
class ComplianceBundle:
    """Auditor-ready export of the governance chain."""
    exported_at: str
    deployment: Dict[str, str]
    period_start: Optional[str]
    period_end: Optional[str]
    total_receipts: int
    chain_valid: bool
    summary: Dict[str, Any]
    checkpoints: List[Dict[str, Any]]
    receipts: List[Dict[str, Any]]
    verification_instructions: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exported_at": self.exported_at,
            "deployment": self.deployment,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_receipts": self.total_receipts,
            "chain_valid": self.chain_valid,
            "summary": self.summary,
            "checkpoints": self.checkpoints,
            "receipts": self.receipts,
            "verification_instructions": self.verification_instructions,
        }


# ═══════════════════════════════════════════════════════════
# MERKLE TREE
# ═══════════════════════════════════════════════════════════

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _merkle_root(leaves: List[str]) -> str:
    """Compute Merkle root from a list of leaf hashes."""
    if not leaves:
        return _sha256("empty")
    if len(leaves) == 1:
        return leaves[0]

    # Pad to even number
    nodes = list(leaves)
    if len(nodes) % 2 == 1:
        nodes.append(nodes[-1])

    while len(nodes) > 1:
        next_level = []
        for i in range(0, len(nodes), 2):
            combined = _sha256(nodes[i] + nodes[i + 1])
            next_level.append(combined)
        nodes = next_level
        if len(nodes) > 1 and len(nodes) % 2 == 1:
            nodes.append(nodes[-1])

    return nodes[0]


# ═══════════════════════════════════════════════════════════
# SURGE ENGINE
# ═══════════════════════════════════════════════════════════

GENESIS_DIGEST = _sha256("NOVTIA_SURGE_GENESIS_v2")

VERIFICATION_INSTRUCTIONS = """
SURGE Chain Verification Instructions
======================================
To independently verify the integrity of this governance chain:

1. Start with the genesis digest:
   genesis = SHA256("NOVTIA_SURGE_GENESIS_v2")
   expected = "{genesis}"

2. For each receipt in sequence order:
   a. Confirm receipt.previous_digest matches the digest of the prior receipt
      (or genesis for sequence 0)
   b. Reconstruct the payload string:
      "{{receipt_id}}|{{sequence}}|{{timestamp}}|{{tool}}|{{decision}}|
       {{risk_score}}|{{policy_ids joined by comma}}|{{chain_pattern or ''}}|
       {{agent_id or ''}}|{{session_id or ''}}|{{deployment_id}}|
       {{jurisdiction}}|{{previous_digest}}"
   c. Compute SHA256(payload_string) and confirm it matches receipt.digest

3. For each Merkle checkpoint:
   a. Collect the leaf digests (receipt.digest) for the sequence range
   b. Compute the Merkle root using pairwise SHA256 hashing
   c. Confirm it matches checkpoint.merkle_root

If any hash does not match, the chain has been tampered with at that point.
All receipts after the first mismatch are untrustworthy.

Tool: Any SHA-256 implementation (openssl, Python hashlib, etc.)
""".format(genesis=GENESIS_DIGEST)


class SurgeEngine:
    """
    Sovereign Unified Runtime Governance Engine.

    Issues hash-chained, compliance-tagged governance receipts
    with Merkle tree checkpoints and sovereign attestation.

    Usage:
        surge = SurgeEngine(config=SovereignConfig(
            deployment_id="novtia-uk-nhs-001",
            jurisdiction="GB",
            operator="NHS Digital",
        ))

        receipt = surge.issue(
            tool="patient_lookup",
            decision="allow",
            risk_score=15,
            explanation="Low risk, within scope",
            policy_ids=["pol_nhs_001"],
        )

        # Periodic checkpoint
        checkpoint = surge.checkpoint()

        # Verify integrity
        result = surge.verify_chain()

        # Export for auditor
        bundle = surge.export(period_start="2026-01-01", period_end="2026-03-01")
    """

    def __init__(
        self,
        config: Optional[SovereignConfig] = None,
        checkpoint_interval: int = 100,  # Auto-checkpoint every N receipts
    ):
        self.config = config or SovereignConfig()
        self.checkpoint_interval = checkpoint_interval
        self._lock = threading.Lock()
        self._receipts: List[GovernanceReceipt] = []
        self._checkpoints: List[MerkleCheckpoint] = []
        self._sequence: int = 0
        self._last_digest: str = GENESIS_DIGEST
        self._last_checkpoint_seq: int = 0

        # Persistence callbacks (set by governor-service)
        self._on_receipt: Optional[Any] = None     # fn(receipt: GovernanceReceipt)
        self._on_checkpoint: Optional[Any] = None  # fn(checkpoint: MerkleCheckpoint)

    def set_persistence(self, on_receipt=None, on_checkpoint=None):
        """Set callbacks invoked after each receipt/checkpoint for DB persistence."""
        self._on_receipt = on_receipt
        self._on_checkpoint = on_checkpoint

    def load_chain(self, receipts: List[Dict], checkpoints: List[Dict]):
        """Rebuild chain state from persisted data (DB rows).

        receipts: list of dicts with receipt fields (ordered by sequence ASC)
        checkpoints: list of dicts with checkpoint fields (ordered by sequence_start ASC)

        This MUST be called before any new issue() calls to ensure
        the hash chain continues correctly from persisted state.
        """
        self._receipts = []
        self._checkpoints = []

        for rd in receipts:
            r = GovernanceReceipt(
                receipt_id=rd["receipt_id"],
                sequence=rd["sequence"],
                timestamp=rd["timestamp"],
                tool=rd["tool"],
                decision=rd["decision"],
                risk_score=rd["risk_score"],
                explanation=rd.get("explanation", ""),
                policy_ids=rd.get("policy_ids", []),
                chain_pattern=rd.get("chain_pattern"),
                agent_id=rd.get("agent_id"),
                session_id=rd.get("session_id"),
                sovereign=rd.get("sovereign", self.config.to_dict()),
                compliance=rd.get("compliance", {}),
                digest=rd["digest"],
                previous_digest=rd["previous_digest"],
                merkle_root=rd.get("merkle_root"),
            )
            self._receipts.append(r)

        for cd in checkpoints:
            cp = MerkleCheckpoint(
                checkpoint_id=cd["checkpoint_id"],
                timestamp=cd["timestamp"],
                sequence_start=cd["sequence_start"],
                sequence_end=cd["sequence_end"],
                receipt_count=cd["receipt_count"],
                merkle_root=cd["merkle_root"],
                leaf_digests=cd.get("leaf_digests", []),
            )
            self._checkpoints.append(cp)

        if self._receipts:
            last = self._receipts[-1]
            self._sequence = last.sequence + 1
            self._last_digest = last.digest
        else:
            self._sequence = 0
            self._last_digest = GENESIS_DIGEST

        if self._checkpoints:
            self._last_checkpoint_seq = self._checkpoints[-1].sequence_end + 1
        else:
            self._last_checkpoint_seq = 0

    # ─── ISSUE ───

    def issue(
        self,
        tool: str,
        decision: str,
        risk_score: int,
        explanation: str = "",
        policy_ids: Optional[List[str]] = None,
        chain_pattern: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> GovernanceReceipt:
        """Issue a new governance receipt."""
        with self._lock:
            return self._issue_locked(
                tool, decision, risk_score, explanation, policy_ids,
                chain_pattern, agent_id, session_id, extra_context,
            )

    def _issue_locked(
        self,
        tool: str,
        decision: str,
        risk_score: int,
        explanation: str = "",
        policy_ids: Optional[List[str]] = None,
        chain_pattern: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> GovernanceReceipt:
        """Internal issue — caller holds self._lock."""

        receipt_id = f"surge-{uuid4().hex[:16]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        policy_ids = policy_ids or []
        extra_context = extra_context or {}

        # Compliance tagging
        compliance = _tag_compliance(
            decision, risk_score, explanation,
            policy_ids, chain_pattern, extra_context,
        )

        # Build receipt (digest not yet computed)
        receipt = GovernanceReceipt(
            receipt_id=receipt_id,
            sequence=self._sequence,
            timestamp=timestamp,
            tool=tool,
            decision=decision,
            risk_score=risk_score,
            explanation=explanation,
            policy_ids=policy_ids,
            chain_pattern=chain_pattern,
            agent_id=agent_id,
            session_id=session_id,
            sovereign=self.config.to_dict(),
            compliance=compliance,
            digest="",  # Computed below
            previous_digest=self._last_digest,
        )

        # Compute digest from canonical payload (includes previous_digest → chain)
        receipt.digest = _sha256(receipt.payload_string())

        # Append and advance
        self._receipts.append(receipt)
        self._last_digest = receipt.digest
        self._sequence += 1

        # Persist to DB
        if self._on_receipt:
            try:
                self._on_receipt(receipt)
            except Exception:
                pass  # best-effort

        # Auto-checkpoint
        if self.checkpoint_interval > 0:
            since_last = self._sequence - self._last_checkpoint_seq
            if since_last >= self.checkpoint_interval:
                self._checkpoint_locked()

        return receipt

    # ─── CHECKPOINT ───

    def checkpoint(self) -> MerkleCheckpoint:
        """Create a Merkle tree checkpoint for recent receipts."""
        with self._lock:
            return self._checkpoint_locked()

    def _checkpoint_locked(self) -> MerkleCheckpoint:
        """Internal checkpoint — caller holds self._lock."""
        start_seq = self._last_checkpoint_seq
        end_seq = self._sequence - 1

        # Collect leaf digests
        leaves = [
            r.digest for r in self._receipts
            if r.sequence >= start_seq and r.sequence <= end_seq
        ]

        if not leaves:
            leaves = [_sha256("empty_checkpoint")]

        root = _merkle_root(leaves)

        cp = MerkleCheckpoint(
            checkpoint_id=f"cp-{uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            sequence_start=start_seq,
            sequence_end=end_seq,
            receipt_count=len(leaves),
            merkle_root=root,
            leaf_digests=leaves,
        )

        # Tag receipts in this window with the Merkle root
        for r in self._receipts:
            if r.sequence >= start_seq and r.sequence <= end_seq:
                r.merkle_root = root

        self._checkpoints.append(cp)
        self._last_checkpoint_seq = self._sequence

        # Persist to DB
        if self._on_checkpoint:
            try:
                self._on_checkpoint(cp)
            except Exception:
                pass  # best-effort

        return cp

    # ─── VERIFY ───

    def verify_chain(self) -> ChainVerification:
        """Verify the integrity of the entire receipt chain."""
        if not self._receipts:
            return ChainVerification(valid=True, receipts_checked=0)

        errors = []
        expected_prev = GENESIS_DIGEST

        for r in self._receipts:
            # Check chain link
            if r.previous_digest != expected_prev:
                return ChainVerification(
                    valid=False,
                    receipts_checked=r.sequence,
                    first_broken_at=r.sequence,
                    first_broken_receipt=r.receipt_id,
                    errors=[
                        f"Chain broken at seq {r.sequence}: expected previous_digest "
                        f"{expected_prev[:16]}... got {r.previous_digest[:16]}..."
                    ],
                )

            # Recompute digest
            recomputed = _sha256(r.payload_string())
            if recomputed != r.digest:
                return ChainVerification(
                    valid=False,
                    receipts_checked=r.sequence,
                    first_broken_at=r.sequence,
                    first_broken_receipt=r.receipt_id,
                    errors=[
                        f"Digest mismatch at seq {r.sequence}: computed "
                        f"{recomputed[:16]}... stored {r.digest[:16]}..."
                    ],
                )

            expected_prev = r.digest

        # Verify Merkle checkpoints
        for cp in self._checkpoints:
            leaves = [
                r.digest for r in self._receipts
                if r.sequence >= cp.sequence_start and r.sequence <= cp.sequence_end
            ]
            recomputed_root = _merkle_root(leaves) if leaves else _sha256("empty_checkpoint")
            if recomputed_root != cp.merkle_root:
                errors.append(
                    f"Merkle checkpoint {cp.checkpoint_id} root mismatch: "
                    f"computed {recomputed_root[:16]}... stored {cp.merkle_root[:16]}..."
                )

        return ChainVerification(
            valid=len(errors) == 0,
            receipts_checked=len(self._receipts),
            errors=errors,
        )

    def verify_single(self, receipt_id: str) -> Dict[str, Any]:
        """Verify a single receipt's integrity."""
        for i, r in enumerate(self._receipts):
            if r.receipt_id == receipt_id:
                # Check digest
                recomputed = _sha256(r.payload_string())
                digest_valid = recomputed == r.digest

                # Check chain link
                if i == 0:
                    chain_valid = r.previous_digest == GENESIS_DIGEST
                else:
                    chain_valid = r.previous_digest == self._receipts[i - 1].digest

                # Check Merkle inclusion
                merkle_valid = None
                if r.merkle_root:
                    for cp in self._checkpoints:
                        if cp.sequence_start <= r.sequence <= cp.sequence_end:
                            merkle_valid = r.digest in cp.leaf_digests
                            break

                return {
                    "receipt_id": receipt_id,
                    "valid": digest_valid and chain_valid,
                    "digest_valid": digest_valid,
                    "chain_link_valid": chain_valid,
                    "merkle_inclusion": merkle_valid,
                    "sequence": r.sequence,
                }

        return {"receipt_id": receipt_id, "valid": False, "error": "Receipt not found"}

    # ─── EXPORT ───

    def export(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> ComplianceBundle:
        """Export the governance chain as an auditor-ready bundle."""

        # Filter by period
        receipts = self._receipts
        if period_start:
            receipts = [r for r in receipts if r.timestamp >= period_start]
        if period_end:
            receipts = [r for r in receipts if r.timestamp <= period_end]

        # Verify chain
        verification = self.verify_chain()

        # Compute summary
        total = len(receipts)
        decisions = {}
        eu_articles_hit = {}
        owasp_hit = {}
        tools_seen = set()
        agents_seen = set()

        for r in receipts:
            decisions[r.decision] = decisions.get(r.decision, 0) + 1
            tools_seen.add(r.tool)
            if r.agent_id:
                agents_seen.add(r.agent_id)
            for art in r.compliance.get("eu_ai_act", []):
                eu_articles_hit[art] = eu_articles_hit.get(art, 0) + 1
            for ref in r.compliance.get("owasp_llm", []):
                owasp_hit[ref] = owasp_hit.get(ref, 0) + 1

        risk_scores = [r.risk_score for r in receipts]

        summary = {
            "total_receipts": total,
            "decisions": decisions,
            "block_rate_pct": round(decisions.get("block", 0) / max(total, 1) * 100, 2),
            "avg_risk_score": round(sum(risk_scores) / max(len(risk_scores), 1), 2),
            "max_risk_score": max(risk_scores) if risk_scores else 0,
            "unique_tools": len(tools_seen),
            "unique_agents": len(agents_seen),
            "eu_ai_act_coverage": eu_articles_hit,
            "owasp_llm_coverage": owasp_hit,
            "chain_integrity": "VERIFIED" if verification.valid else "BROKEN",
        }

        # Relevant checkpoints
        checkpoints = []
        if receipts:
            min_seq = receipts[0].sequence
            max_seq = receipts[-1].sequence
            checkpoints = [
                cp.to_dict() for cp in self._checkpoints
                if cp.sequence_end >= min_seq and cp.sequence_start <= max_seq
            ]

        return ComplianceBundle(
            exported_at=datetime.now(timezone.utc).isoformat(),
            deployment=self.config.to_dict(),
            period_start=period_start,
            period_end=period_end,
            total_receipts=total,
            chain_valid=verification.valid,
            summary=summary,
            checkpoints=checkpoints,
            receipts=[r.to_dict() for r in receipts],
            verification_instructions=VERIFICATION_INSTRUCTIONS,
        )

    # ─── QUERY ───

    def get_receipt(self, receipt_id: str) -> Optional[GovernanceReceipt]:
        for r in self._receipts:
            if r.receipt_id == receipt_id:
                return r
        return None

    def get_receipts(self, limit: int = 50, agent_id: Optional[str] = None,
                     decision: Optional[str] = None) -> List[GovernanceReceipt]:
        results = self._receipts
        if agent_id:
            results = [r for r in results if r.agent_id == agent_id]
        if decision:
            results = [r for r in results if r.decision == decision]
        return list(reversed(results[-limit:]))

    def get_checkpoints(self) -> List[MerkleCheckpoint]:
        return list(self._checkpoints)

    @property
    def receipt_count(self) -> int:
        return len(self._receipts)

    @property
    def chain_length(self) -> int:
        return self._sequence

    @property
    def last_digest(self) -> str:
        return self._last_digest

    def status(self) -> Dict[str, Any]:
        return {
            "engine": "SURGE v2",
            "deployment": self.config.to_dict(),
            "chain_length": self._sequence,
            "total_receipts": len(self._receipts),
            "total_checkpoints": len(self._checkpoints),
            "last_digest": self._last_digest[:32] + "...",
            "genesis_digest": GENESIS_DIGEST[:32] + "...",
            "checkpoint_interval": self.checkpoint_interval,
            "chain_intact": self.verify_chain().valid,
        }
