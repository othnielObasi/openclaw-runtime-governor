package dev.openclaw.governor;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.*;

/**
 * Java client for the OpenClaw Governor – a runtime governance layer for AI agents.
 *
 * <p>The Governor evaluates every tool invocation against configurable policies
 * and returns an <b>allow / block / review</b> decision before the tool executes.</p>
 *
 * <h3>Quick start</h3>
 * <pre>{@code
 * GovernorClient gov = new GovernorClient.Builder()
 *     .baseUrl("https://openclaw-governor.fly.dev")
 *     .apiKey("ocg_your_key_here")
 *     .build();
 *
 * GovernorDecision d = gov.evaluate("shell_exec", Map.of("command", "ls -la"));
 * System.out.println(d.getDecision()); // "allow" | "review"
 * }</pre>
 *
 * <h3>Configuration</h3>
 * <ul>
 *   <li>{@code GOVERNOR_URL} env var → base URL (default {@code http://localhost:8000})</li>
 *   <li>{@code GOVERNOR_API_KEY} env var → API key sent as {@code X-API-Key} header</li>
 * </ul>
 *
 * <p>Uses {@code java.net.http.HttpClient} (Java 11+). Zero external dependencies.</p>
 */
public class GovernorClient {

    private final String baseUrl;
    private final String apiKey;
    private final Duration timeout;
    private final HttpClient httpClient;

    private GovernorClient(String baseUrl, String apiKey, Duration timeout) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.apiKey = apiKey != null ? apiKey : "";
        this.timeout = timeout;
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(timeout)
                .build();
    }

    // ── Builder ───────────────────────────────────────────────

    public static class Builder {
        private String baseUrl;
        private String apiKey;
        private Duration timeout = Duration.ofSeconds(10);

        /** Set the Governor service base URL. Defaults to env {@code GOVERNOR_URL} or {@code http://localhost:8000}. */
        public Builder baseUrl(String baseUrl) { this.baseUrl = baseUrl; return this; }

        /** Set the API key ({@code ocg_…}). Defaults to env {@code GOVERNOR_API_KEY}. */
        public Builder apiKey(String apiKey) { this.apiKey = apiKey; return this; }

        /** Set the HTTP request timeout. Default 10 seconds. */
        public Builder timeout(Duration timeout) { this.timeout = timeout; return this; }

        public GovernorClient build() {
            String url = baseUrl != null ? baseUrl : envOrDefault("GOVERNOR_URL", "http://localhost:8000");
            String key = apiKey != null ? apiKey : envOrDefault("GOVERNOR_API_KEY", "");
            return new GovernorClient(url, key, timeout);
        }
    }

    // ── Public API ────────────────────────────────────────────

    /**
     * Evaluate a tool call against the Governor.
     *
     * @param tool    tool name (e.g. "shell_exec", "http_request")
     * @param args    tool arguments as a map
     * @return the Governor's decision
     * @throws GovernorBlockedError if the decision is "block"
     * @throws GovernorException    on network or parse errors
     */
    public GovernorDecision evaluate(String tool, Map<String, Object> args) {
        return evaluate(tool, args, null);
    }

    /**
     * Evaluate a tool call with optional context.
     *
     * @param tool    tool name
     * @param args    tool arguments
     * @param context optional context map (session id, agent id, etc.)
     * @return the Governor's decision
     * @throws GovernorBlockedError if the decision is "block"
     * @throws GovernorException    on network or parse errors
     */
    public GovernorDecision evaluate(String tool, Map<String, Object> args, Map<String, Object> context) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("tool", tool);
        payload.put("args", args);
        payload.put("context", context);

        Map<String, Object> raw = post("/actions/evaluate", payload);
        GovernorDecision decision = parseDecision(raw);

        if ("block".equals(decision.getDecision())) {
            throw new GovernorBlockedError(tool, decision);
        }

        return decision;
    }

    /**
     * Convenience alias for {@link #evaluate(String, Map, Map)}.
     */
    public GovernorDecision governedCall(String tool, Map<String, Object> args, Map<String, Object> context) {
        return evaluate(tool, args, context);
    }

    /**
     * Fetch administrative status (kill switch state, etc.).
     */
    public Map<String, Object> getStatus() {
        return get("/admin/status");
    }

    /**
     * Fetch governor summary (total actions, block rate, etc.).
     */
    public Map<String, Object> getSummary() {
        return get("/summary/moltbook");
    }

    // ── Internal ──────────────────────────────────────────────

    private Map<String, Object> post(String path, Map<String, Object> body) {
        String json = toJson(body);
        HttpRequest.Builder rb = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + path))
                .timeout(timeout)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json));
        addAuth(rb);
        return execute(rb.build());
    }

    private Map<String, Object> get(String path) {
        HttpRequest.Builder rb = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + path))
                .timeout(timeout)
                .GET();
        addAuth(rb);
        return execute(rb.build());
    }

    private void addAuth(HttpRequest.Builder rb) {
        if (!apiKey.isEmpty()) {
            rb.header("X-API-Key", apiKey);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> execute(HttpRequest request) {
        try {
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 400) {
                throw new GovernorException("Governor API returned " + response.statusCode() + ": " + response.body());
            }
            return (Map<String, Object>) SimpleJson.parse(response.body());
        } catch (IOException e) {
            throw new GovernorException("Failed to reach Governor at " + baseUrl + ": " + e.getMessage(), e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new GovernorException("Request interrupted", e);
        }
    }

    @SuppressWarnings("unchecked")
    private GovernorDecision parseDecision(Map<String, Object> raw) {
        String decision = (String) raw.getOrDefault("decision", "");
        double riskScore = toDouble(raw.get("risk_score"));
        String explanation = (String) raw.getOrDefault("explanation", "");
        List<String> policyIds = (List<String>) raw.getOrDefault("policy_ids", Collections.emptyList());
        Map<String, Object> modifiedArgs = (Map<String, Object>) raw.get("modified_args");
        return new GovernorDecision(decision, riskScore, explanation, policyIds, modifiedArgs, raw);
    }

    private static double toDouble(Object o) {
        if (o instanceof Number) return ((Number) o).doubleValue();
        if (o instanceof String) {
            try { return Double.parseDouble((String) o); } catch (NumberFormatException e) { return 0; }
        }
        return 0;
    }

    private static String envOrDefault(String key, String defaultValue) {
        String v = System.getenv(key);
        return (v != null && !v.isEmpty()) ? v : defaultValue;
    }

    // ── Minimal JSON serializer (zero-dependency) ─────────────

    private static String toJson(Object obj) {
        if (obj == null) return "null";
        if (obj instanceof String) return "\"" + escapeJson((String) obj) + "\"";
        if (obj instanceof Number || obj instanceof Boolean) return obj.toString();
        if (obj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> map = (Map<String, Object>) obj;
            StringBuilder sb = new StringBuilder("{");
            boolean first = true;
            for (Map.Entry<String, Object> e : map.entrySet()) {
                if (!first) sb.append(",");
                sb.append("\"").append(escapeJson(e.getKey())).append("\":").append(toJson(e.getValue()));
                first = false;
            }
            return sb.append("}").toString();
        }
        if (obj instanceof Collection) {
            StringBuilder sb = new StringBuilder("[");
            boolean first = true;
            for (Object item : (Collection<?>) obj) {
                if (!first) sb.append(",");
                sb.append(toJson(item));
                first = false;
            }
            return sb.append("]").toString();
        }
        return "\"" + escapeJson(obj.toString()) + "\"";
    }

    private static String escapeJson(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }
}
