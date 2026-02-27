# OpenClaw Governor Client — Java

Java client for the **OpenClaw Governor** – a runtime governance layer for AI agents.

Uses `java.net.http.HttpClient` (Java 11+) with **zero external dependencies**.

## Installation

### Maven

```xml
<dependency>
    <groupId>dev.openclaw</groupId>
    <artifactId>governor-client</artifactId>
    <version>0.2.0</version>
</dependency>
```

### Gradle

```groovy
implementation 'dev.openclaw:governor-client:0.2.0'
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
