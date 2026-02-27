package dev.openclaw.governor;

import org.junit.Test;
import static org.junit.Assert.*;

import java.util.Map;

public class GovernorClientTest {

    @Test
    public void testBuilderDefaults() {
        GovernorClient client = new GovernorClient.Builder().build();
        assertNotNull(client);
    }

    @Test
    public void testBuilderCustom() {
        GovernorClient client = new GovernorClient.Builder()
                .baseUrl("https://example.com")
                .apiKey("ocg_test123")
                .build();
        assertNotNull(client);
    }

    @Test
    public void testDecisionParsing() {
        GovernorDecision d = new GovernorDecision(
                "allow", 15.0, "Safe operation",
                java.util.List.of("shell-guard"), null,
                Map.of("decision", "allow", "risk_score", 15.0));
        assertEquals("allow", d.getDecision());
        assertEquals(15.0, d.getRiskScore(), 0.01);
        assertEquals("Safe operation", d.getExplanation());
        assertEquals(1, d.getPolicyIds().size());
        assertNull(d.getModifiedArgs());
    }

    @Test
    public void testBlockedError() {
        GovernorDecision d = new GovernorDecision(
                "block", 95.0, "Dangerous command",
                java.util.List.of("shell-dangerous"), null, null);
        GovernorBlockedError err = new GovernorBlockedError("shell", d);
        assertTrue(err.getMessage().contains("Dangerous command"));
        assertEquals("block", err.getDecision().getDecision());
    }

    @Test
    public void testSimpleJsonParse() {
        @SuppressWarnings("unchecked")
        Map<String, Object> m = (Map<String, Object>) SimpleJson.parse(
                "{\"decision\":\"allow\",\"risk_score\":10.5,\"explanation\":\"ok\",\"policy_ids\":[\"p1\"],\"modified_args\":null}");
        assertEquals("allow", m.get("decision"));
        assertEquals(10.5, ((Number) m.get("risk_score")).doubleValue(), 0.01);
        assertEquals("ok", m.get("explanation"));
        assertNull(m.get("modified_args"));
    }

    @Test
    public void testGovernorExceptionMessage() {
        GovernorException e = new GovernorException("test error");
        assertEquals("test error", e.getMessage());
    }
}
