"""
SURGE v2 — Test Suite
======================
Run: pytest tests/test_surge.py -v
"""
import json
import hashlib
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from surge import (
    SurgeEngine, SovereignConfig, GovernanceReceipt,
    ChainVerification, MerkleCheckpoint, ComplianceBundle,
    GENESIS_DIGEST, _sha256, _merkle_root,
)


@pytest.fixture
def engine():
    return SurgeEngine(
        config=SovereignConfig(
            deployment_id="test-uk-001",
            jurisdiction="GB",
            operator="Test Corp",
            infrastructure="on-premise",
            data_residency="GB",
        ),
        checkpoint_interval=0,  # Manual checkpoints for testing
    )


@pytest.fixture
def loaded_engine(engine):
    """Engine with 10 receipts."""
    for i in range(10):
        engine.issue(
            tool=["shell", "http_get", "read_file"][i % 3],
            decision=["allow", "allow", "block"][i % 3],
            risk_score=i * 10,
            explanation=f"Test evaluation {i}",
            policy_ids=[f"pol_{i}"] if i % 2 == 0 else [],
            agent_id="agent_001",
            session_id="sess_test",
        )
    return engine


# ═══ BASIC RECEIPT ISSUANCE ═══

class TestReceiptIssuance:

    def test_issue_receipt(self, engine):
        r = engine.issue(tool="shell", decision="block", risk_score=85,
                         explanation="Injection detected")
        assert r.receipt_id.startswith("surge-")
        assert r.sequence == 0
        assert r.tool == "shell"
        assert r.decision == "block"
        assert r.risk_score == 85
        assert len(r.digest) == 64  # SHA-256 hex

    def test_sequence_increments(self, engine):
        r1 = engine.issue(tool="a", decision="allow", risk_score=0)
        r2 = engine.issue(tool="b", decision="allow", risk_score=0)
        r3 = engine.issue(tool="c", decision="allow", risk_score=0)
        assert r1.sequence == 0
        assert r2.sequence == 1
        assert r3.sequence == 2

    def test_receipt_count(self, loaded_engine):
        assert loaded_engine.receipt_count == 10
        assert loaded_engine.chain_length == 10

    def test_sovereign_attestation(self, engine):
        r = engine.issue(tool="test", decision="allow", risk_score=0)
        assert r.sovereign["deployment_id"] == "test-uk-001"
        assert r.sovereign["jurisdiction"] == "GB"
        assert r.sovereign["operator"] == "Test Corp"
        assert r.sovereign["infrastructure"] == "on-premise"
        assert r.sovereign["data_residency"] == "GB"


# ═══ HASH CHAIN ═══

class TestHashChain:

    def test_genesis_link(self, engine):
        r = engine.issue(tool="test", decision="allow", risk_score=0)
        assert r.previous_digest == GENESIS_DIGEST

    def test_chain_links(self, engine):
        r1 = engine.issue(tool="a", decision="allow", risk_score=0)
        r2 = engine.issue(tool="b", decision="allow", risk_score=0)
        r3 = engine.issue(tool="c", decision="allow", risk_score=0)
        assert r2.previous_digest == r1.digest
        assert r3.previous_digest == r2.digest

    def test_digest_deterministic(self, engine):
        r = engine.issue(tool="test", decision="allow", risk_score=50,
                         explanation="test", policy_ids=["pol_1"])
        recomputed = _sha256(r.payload_string())
        assert recomputed == r.digest

    def test_unique_digests(self, loaded_engine):
        digests = [r.digest for r in loaded_engine.get_receipts(limit=100)]
        assert len(digests) == len(set(digests))


# ═══ CHAIN VERIFICATION ═══

class TestChainVerification:

    def test_valid_chain(self, loaded_engine):
        result = loaded_engine.verify_chain()
        assert result.valid is True
        assert result.receipts_checked == 10
        assert len(result.errors) == 0

    def test_empty_chain_valid(self, engine):
        result = engine.verify_chain()
        assert result.valid is True
        assert result.receipts_checked == 0

    def test_tampered_digest_detected(self, loaded_engine):
        # Tamper with a receipt's digest
        loaded_engine._receipts[5].digest = "deadbeef" * 8
        result = loaded_engine.verify_chain()
        assert result.valid is False
        assert result.first_broken_at == 5

    def test_tampered_chain_link_detected(self, loaded_engine):
        # Tamper with a receipt's previous_digest
        loaded_engine._receipts[3].previous_digest = "cafebabe" * 8
        result = loaded_engine.verify_chain()
        assert result.valid is False
        assert result.first_broken_at == 3

    def test_tampered_payload_detected(self, loaded_engine):
        # Tamper with a receipt's decision (changes payload, digest no longer matches)
        loaded_engine._receipts[7].decision = "allow"  # Change from whatever it was
        loaded_engine._receipts[7].risk_score = 99      # Change risk score
        result = loaded_engine.verify_chain()
        assert result.valid is False

    def test_single_receipt_verification(self, loaded_engine):
        receipts = loaded_engine.get_receipts(limit=10)
        r = receipts[0]  # Most recent
        result = loaded_engine.verify_single(r.receipt_id)
        assert result["valid"] is True
        assert result["digest_valid"] is True
        assert result["chain_link_valid"] is True

    def test_single_receipt_not_found(self, engine):
        result = engine.verify_single("nonexistent")
        assert result["valid"] is False
        assert "not found" in result.get("error", "")


# ═══ MERKLE CHECKPOINTS ═══

class TestMerkleCheckpoints:

    def test_create_checkpoint(self, loaded_engine):
        cp = loaded_engine.checkpoint()
        assert cp.receipt_count == 10
        assert cp.sequence_start == 0
        assert cp.sequence_end == 9
        assert len(cp.merkle_root) == 64
        assert len(cp.leaf_digests) == 10

    def test_merkle_root_deterministic(self):
        leaves = ["aaa", "bbb", "ccc", "ddd"]
        root1 = _merkle_root(leaves)
        root2 = _merkle_root(leaves)
        assert root1 == root2

    def test_merkle_root_changes_with_data(self):
        root1 = _merkle_root(["aaa", "bbb"])
        root2 = _merkle_root(["aaa", "ccc"])
        assert root1 != root2

    def test_merkle_single_leaf(self):
        root = _merkle_root(["abc"])
        assert root == "abc"

    def test_checkpoint_tags_receipts(self, loaded_engine):
        cp = loaded_engine.checkpoint()
        for r in loaded_engine._receipts:
            assert r.merkle_root == cp.merkle_root

    def test_multiple_checkpoints(self, engine):
        for i in range(5):
            engine.issue(tool="a", decision="allow", risk_score=0)
        cp1 = engine.checkpoint()

        for i in range(5):
            engine.issue(tool="b", decision="allow", risk_score=0)
        cp2 = engine.checkpoint()

        assert cp1.merkle_root != cp2.merkle_root
        assert cp1.sequence_end == 4
        assert cp2.sequence_start == 5
        assert len(engine.get_checkpoints()) == 2

    def test_auto_checkpoint(self):
        engine = SurgeEngine(checkpoint_interval=5)
        for i in range(12):
            engine.issue(tool="test", decision="allow", risk_score=0)
        # Should have auto-checkpointed at 5 and 10
        assert len(engine.get_checkpoints()) == 2

    def test_merkle_verification_in_chain_verify(self, loaded_engine):
        loaded_engine.checkpoint()
        result = loaded_engine.verify_chain()
        assert result.valid is True


# ═══ COMPLIANCE TAGGING ═══

class TestComplianceTagging:

    def test_every_receipt_has_art12(self, engine):
        """Art.12 (Record-Keeping) applies to every receipt."""
        r = engine.issue(tool="test", decision="allow", risk_score=0)
        assert "Art.12" in r.compliance["eu_ai_act"]

    def test_block_gets_art9(self, engine):
        """Blocked actions provide Art.9 (Risk Management) evidence."""
        r = engine.issue(tool="test", decision="block", risk_score=80,
                         explanation="High risk blocked")
        assert "Art.9" in r.compliance["eu_ai_act"]

    def test_injection_gets_art15(self, engine):
        """Injection detection provides Art.15 (Cybersecurity) evidence."""
        r = engine.issue(tool="shell", decision="block", risk_score=95,
                         explanation="Injection detected: jailbreak attempt")
        assert "Art.15" in r.compliance["eu_ai_act"]

    def test_kill_switch_gets_art14(self, engine):
        """Kill switch provides Art.14 (Human Oversight) evidence."""
        r = engine.issue(tool="any", decision="block", risk_score=99,
                         explanation="Kill switch engaged by operator")
        assert "Art.14" in r.compliance["eu_ai_act"]

    def test_owasp_injection_tag(self, engine):
        r = engine.issue(tool="shell", decision="block", risk_score=95,
                         explanation="Injection pattern detected")
        assert "LLM01" in r.compliance["owasp_llm"]

    def test_owasp_pii_tag(self, engine):
        r = engine.issue(tool="http", decision="block", risk_score=80,
                         explanation="PII credential leak in output")
        assert "LLM02" in r.compliance["owasp_llm"]

    def test_owasp_excessive_agency_tag(self, engine):
        r = engine.issue(tool="admin", decision="block", risk_score=90,
                         explanation="Scope violation: tool blocked")
        assert "LLM06" in r.compliance["owasp_llm"]

    def test_nist_tags(self, engine):
        r = engine.issue(tool="test", decision="block", risk_score=80,
                         explanation="Risk score exceeded threshold",
                         policy_ids=["pol_1"])
        assert "GOVERN-1.1" in r.compliance["nist_ai_rmf"]
        assert "MANAGE-1.1" in r.compliance["nist_ai_rmf"]

    def test_multiple_frameworks_simultaneously(self, engine):
        r = engine.issue(tool="shell", decision="block", risk_score=95,
                         explanation="Injection detected, kill switch engaged",
                         policy_ids=["pol_sec_1"])
        assert len(r.compliance["eu_ai_act"]) >= 3
        assert len(r.compliance["owasp_llm"]) >= 1
        assert len(r.compliance["nist_ai_rmf"]) >= 2


# ═══ EXPORT ═══

class TestExport:

    def test_export_bundle(self, loaded_engine):
        loaded_engine.checkpoint()
        bundle = loaded_engine.export()
        assert bundle.total_receipts == 10
        assert bundle.chain_valid is True
        assert len(bundle.receipts) == 10
        assert len(bundle.checkpoints) >= 1
        assert bundle.deployment["deployment_id"] == "test-uk-001"

    def test_export_contains_verification_instructions(self, loaded_engine):
        bundle = loaded_engine.export()
        assert "SHA256" in bundle.verification_instructions
        assert "NOVTIA_SURGE_GENESIS_v2" in bundle.verification_instructions

    def test_export_summary(self, loaded_engine):
        bundle = loaded_engine.export()
        s = bundle.summary
        assert s["total_receipts"] == 10
        assert "decisions" in s
        assert "eu_ai_act_coverage" in s
        assert s["chain_integrity"] == "VERIFIED"

    def test_export_period_filter(self, loaded_engine):
        # All receipts have timestamps from "now" — filter for future = empty
        bundle = loaded_engine.export(period_start="2099-01-01")
        assert bundle.total_receipts == 0

    def test_export_serializable(self, loaded_engine):
        loaded_engine.checkpoint()
        bundle = loaded_engine.export()
        # Should be JSON-serializable
        json_str = json.dumps(bundle.to_dict())
        parsed = json.loads(json_str)
        assert parsed["total_receipts"] == 10
        assert parsed["chain_valid"] is True

    def test_export_eu_coverage(self, engine):
        """Export should show which EU AI Act articles are covered."""
        engine.issue(tool="shell", decision="block", risk_score=95,
                     explanation="Injection detected, kill switch engaged, escalation triggered")
        engine.issue(tool="db", decision="allow", risk_score=10,
                     explanation="Normal operation, monitoring active")
        bundle = engine.export()
        coverage = bundle.summary["eu_ai_act_coverage"]
        assert "Art.12" in coverage  # Record-keeping — always present
        assert coverage["Art.12"] >= 2


# ═══ QUERY ═══

class TestQuery:

    def test_get_receipts_limit(self, loaded_engine):
        receipts = loaded_engine.get_receipts(limit=3)
        assert len(receipts) == 3

    def test_get_receipts_by_agent(self, loaded_engine):
        receipts = loaded_engine.get_receipts(agent_id="agent_001")
        assert len(receipts) == 10
        receipts = loaded_engine.get_receipts(agent_id="nonexistent")
        assert len(receipts) == 0

    def test_get_receipts_by_decision(self, loaded_engine):
        blocked = loaded_engine.get_receipts(decision="block")
        for r in blocked:
            assert r.decision == "block"

    def test_status(self, loaded_engine):
        s = loaded_engine.status()
        assert s["engine"] == "SURGE v2"
        assert s["chain_length"] == 10
        assert s["total_receipts"] == 10
        assert s["chain_intact"] is True
        assert s["deployment"]["jurisdiction"] == "GB"


# ═══ EDGE CASES ═══

class TestEdgeCases:

    def test_empty_policy_ids(self, engine):
        r = engine.issue(tool="test", decision="allow", risk_score=0)
        assert r.policy_ids == []
        assert len(r.digest) == 64

    def test_long_explanation(self, engine):
        r = engine.issue(tool="test", decision="allow", risk_score=0,
                         explanation="x" * 10000)
        assert len(r.digest) == 64

    def test_unicode_content(self, engine):
        r = engine.issue(tool="翻译", decision="allow", risk_score=0,
                         explanation="日本語テスト")
        assert len(r.digest) == 64
        result = engine.verify_chain()
        assert result.valid is True

    def test_all_decisions(self, engine):
        for d in ["allow", "block", "review"]:
            r = engine.issue(tool="test", decision=d, risk_score=50)
            assert r.decision == d

    def test_large_chain(self):
        """Test chain integrity with 500 receipts."""
        engine = SurgeEngine(checkpoint_interval=100)
        for i in range(500):
            engine.issue(tool=f"tool_{i % 10}", decision="allow",
                         risk_score=i % 100)
        result = engine.verify_chain()
        assert result.valid is True
        assert result.receipts_checked == 500
        assert len(engine.get_checkpoints()) == 5  # 500/100
