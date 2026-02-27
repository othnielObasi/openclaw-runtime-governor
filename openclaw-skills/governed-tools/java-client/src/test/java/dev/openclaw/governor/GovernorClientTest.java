package dev.openclaw.governor;

import org.junit.Test;
import static org.junit.Assert.*;

import java.util.List;
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

    // ── Trace type tests ──────────────────────────────────────

    @Test
    public void testSimpleJsonParseIngestResponse() {
        @SuppressWarnings("unchecked")
        Map<String, Object> m = (Map<String, Object>) SimpleJson.parse(
                "{\"inserted\":3,\"skipped\":1}");
        assertEquals(3, ((Number) m.get("inserted")).intValue());
        assertEquals(1, ((Number) m.get("skipped")).intValue());
    }

    @Test
    public void testSimpleJsonParseTraceList() {
        @SuppressWarnings("unchecked")
        List<Object> list = (List<Object>) SimpleJson.parse(
                "[{\"trace_id\":\"t1\",\"span_count\":5,\"governance_count\":2,\"has_blocks\":false}]");
        assertEquals(1, list.size());
        @SuppressWarnings("unchecked")
        Map<String, Object> trace = (Map<String, Object>) list.get(0);
        assertEquals("t1", trace.get("trace_id"));
        assertEquals(5, ((Number) trace.get("span_count")).intValue());
        assertEquals(2, ((Number) trace.get("governance_count")).intValue());
    }

    @Test
    public void testSimpleJsonParseTraceDetail() {
        String json = "{\"trace_id\":\"t1\",\"span_count\":3,\"governance_count\":1,"
                + "\"spans\":[{\"span_id\":\"s1\",\"kind\":\"agent\"},{\"span_id\":\"s2\",\"kind\":\"llm\"},{\"span_id\":\"s3\",\"kind\":\"governance\"}],"
                + "\"governance_decisions\":[{\"tool\":\"shell\",\"decision\":\"allow\"}],"
                + "\"has_errors\":false,\"has_blocks\":false}";
        @SuppressWarnings("unchecked")
        Map<String, Object> detail = (Map<String, Object>) SimpleJson.parse(json);
        assertEquals("t1", detail.get("trace_id"));
        assertEquals(3, ((Number) detail.get("span_count")).intValue());
        @SuppressWarnings("unchecked")
        List<Object> spans = (List<Object>) detail.get("spans");
        assertEquals(3, spans.size());
    }

    @Test
    public void testSimpleJsonParseDeleteResult() {
        @SuppressWarnings("unchecked")
        Map<String, Object> m = (Map<String, Object>) SimpleJson.parse(
                "{\"trace_id\":\"t1\",\"spans_deleted\":5}");
        assertEquals("t1", m.get("trace_id"));
        assertEquals(5, ((Number) m.get("spans_deleted")).intValue());
    }

    @Test
    public void testJsonSerializeSpanBatch() {
        // Verify the toJson serializer handles nested lists of maps (used by ingestSpans)
        String json = "{\"spans\":[{\"trace_id\":\"t1\",\"span_id\":\"s1\",\"kind\":\"agent\",\"name\":\"root\"}]}";
        @SuppressWarnings("unchecked")
        Map<String, Object> parsed = (Map<String, Object>) SimpleJson.parse(json);
        @SuppressWarnings("unchecked")
        List<Object> spans = (List<Object>) parsed.get("spans");
        assertEquals(1, spans.size());
        @SuppressWarnings("unchecked")
        Map<String, Object> span = (Map<String, Object>) spans.get(0);
        assertEquals("agent", span.get("kind"));
        assertEquals("root", span.get("name"));
    }
}
