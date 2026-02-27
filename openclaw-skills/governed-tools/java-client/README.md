# OpenClaw Governor Client — Java

Java client for the **OpenClaw Governor** – a runtime governance layer for AI agents.

Uses `java.net.http.HttpClient` (Java 11+) with **zero external dependencies**.

## Installation

### Maven

```xml
<dependency>
    <groupId>dev.openclaw</groupId>
    <artifactId>governor-client</artifactId>
    <version>0.3.0</version>
</dependency>
```

### Gradle

```groovy
implementation 'dev.openclaw:governor-client:0.3.0'
```

## Quick start

```java
import dev.openclaw.governor.*;
import java.util.Map;

GovernorClient gov = new GovernorClient.Builder()
    .baseUrl("https://openclaw-governor.fly.dev")
    .apiKey("ocg_your_key_here")
    .build();

try {
    GovernorDecision d = gov.evaluate("shell_exec", Map.of("command", "ls -la"));
    System.out.println(d.getDecision());   // "allow" | "review"
    System.out.println(d.getRiskScore());  // 0.0 – 100.0
    System.out.println(d.getExplanation());
} catch (GovernorBlockedError e) {
    System.err.println("Blocked: " + e.getMessage());
}
```

## Configuration

| Builder method | Env variable | Default | Description |
|---|---|---|---|
| `.baseUrl(url)` | `GOVERNOR_URL` | `http://localhost:8000` | Base URL of the Governor service |
| `.apiKey(key)` | `GOVERNOR_API_KEY` | *(empty)* | API key (`ocg_…`) sent as `X-API-Key` header |
| `.timeout(duration)` | — | 10 seconds | HTTP request timeout |

Environment variables are read automatically when builder methods are not called.

## API

### `GovernorClient.Builder`

Fluent builder. Call `.build()` to create the client.

### `client.evaluate(tool, args)` / `client.evaluate(tool, args, context)`

Evaluate a tool call. Returns `GovernorDecision`. Throws `GovernorBlockedError` if blocked.

### `client.governedCall(tool, args, context)`

Alias for `evaluate`.

### `client.getStatus()`

Returns admin status as `Map<String, Object>`.

### `client.getSummary()`

Returns governor summary as `Map<String, Object>`.

### `client.ingestSpans(spans)`

Batch-ingest agent trace spans (up to 500). Idempotent — duplicate `span_id` values are silently skipped.

```java
List<Map<String, Object>> spans = List.of(
    Map.of("trace_id", "t-123", "span_id", "s-1", "kind", "agent",
           "name", "main", "start_time", "2026-01-01T00:00:00Z"),
    Map.of("trace_id", "t-123", "span_id", "s-2", "kind", "llm",
           "name", "gpt-4", "start_time", "2026-01-01T00:00:01Z",
           "parent_span_id", "s-1")
);
Map<String, Object> result = gov.ingestSpans(spans);
// {"inserted": 2, "skipped": 0}
```

### `client.listTraces()` / `client.listTraces(filters)`

List traces. Optional filters: `agent_id`, `session_id`, `has_blocks`, `limit`, `offset`.

### `client.getTrace(traceId)`

Full trace detail — all spans plus correlated governance decisions.

### `client.deleteTrace(traceId)`

Delete all spans for a trace. Returns `{"trace_id": "…", "spans_deleted": N}`.

### Trace correlation

Pass `trace_id` and `span_id` in the context map of `evaluate()` to auto-create
a governance span in the agent's trace tree:

```java
Map<String, Object> ctx = Map.of(
    "trace_id", "t-123",
    "span_id", "s-2",       // governance span becomes a child of this span
    "agent_id", "my-agent"
);
GovernorDecision d = gov.evaluate("shell_exec", Map.of("command", "ls"), ctx);
```

### Exception hierarchy

| Class | Description |
|---|---|
| `GovernorException` (extends `RuntimeException`) | Network, HTTP, or parse errors |
| `GovernorBlockedError` (extends `RuntimeException`) | Tool was blocked by policy |

## Requirements

- Java ≥ 11
- Zero runtime dependencies

## License

MIT — see [LICENSE](../LICENSE).
