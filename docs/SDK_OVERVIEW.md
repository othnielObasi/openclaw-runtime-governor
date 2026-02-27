# SDK Overview — OpenClaw Governor

Three official client SDKs for integrating AI agents with the Governor runtime governance layer.

All SDKs share the same design principles:
- **Authenticate with `X-API-Key`** (or JWT Bearer token)
- **Throw/raise on `block` decisions** — `GovernorBlockedError`
- **Zero or minimal runtime dependencies**
- **Environment variable configuration** (`GOVERNOR_URL`, `GOVERNOR_API_KEY`)

> **Real-time streaming**: The Governor also exposes `GET /actions/stream` (Server-Sent Events) for real-time monitoring of all governance decisions. SSE can be consumed from any language using standard EventSource or HTTP streaming clients — see the main [README](../README.md#real-time-monitoring) for examples.

---

## Comparison

| Feature | Python | TypeScript / JavaScript | Java |
|---------|--------|------------------------|------|
| **Package** | `openclaw-governor-client` | `@openclaw/governor-client` | `dev.openclaw:governor-client` |
| **Registry** | PyPI | npm | Maven Central |
| **Version** | 0.2.0 | 0.2.0 | 0.2.0 |
| **Runtime** | Python 3.8+ | Node.js 18+ | Java 11+ |
| **HTTP library** | `httpx` | Built-in `fetch` | `java.net.http.HttpClient` |
| **Runtime deps** | 1 (httpx) | 0 | 0 |
| **Module format** | Python module | Dual CJS + ESM | JAR (Maven) |
| **Auth** | `X-API-Key` header | `X-API-Key` header | `X-API-Key` header |
| **Blocked error** | `GovernorBlockedError` | `GovernorBlockedError` | `GovernorBlockedError` |
| **Config** | Module globals or env vars | Constructor options or env vars | Builder pattern or env vars |
| **Timeout** | 10s default | 10s default | 10s default |
| **Tests** | — | 6 (node:test) | 6 (JUnit 4) |

---

## Installation

### Python

```bash
pip install openclaw-governor-client
```

### TypeScript / JavaScript

```bash
npm install @openclaw/governor-client
```

### Java (Maven)

```xml
<dependency>
    <groupId>dev.openclaw</groupId>
    <artifactId>governor-client</artifactId>
    <version>0.2.0</version>
</dependency>
```

### Java (Gradle)

```groovy
implementation 'dev.openclaw:governor-client:0.2.0'
```

---

## Quick Start

### Python

```python
import governor_client
from governor_client import evaluate_action, GovernorBlockedError

governor_client.GOVERNOR_URL = "https://openclaw-governor.fly.dev"
governor_client.GOVERNOR_API_KEY = "ocg_your_key_here"

try:
    decision = evaluate_action("shell_exec", {"command": "ls -la /tmp"})
    print(decision["decision"])      # "allow" | "review"
    print(decision["risk_score"])    # 0 – 100
    print(decision["explanation"])
except GovernorBlockedError as e:
    print(f"Blocked: {e}")
```

Or via environment variables:

```bash
export GOVERNOR_URL=https://openclaw-governor.fly.dev
export GOVERNOR_API_KEY=ocg_your_key_here
python my_agent.py
```

### TypeScript / JavaScript

```typescript
import { GovernorClient, GovernorBlockedError } from "@openclaw/governor-client";

const gov = new GovernorClient({
  baseUrl: "https://openclaw-governor.fly.dev",
  apiKey: "ocg_your_key_here",
});

try {
  const decision = await gov.evaluate("shell_exec", { command: "ls -la /tmp" });
  console.log(decision.decision);    // "allow" | "review"
  console.log(decision.risk_score);  // 0 – 100
  console.log(decision.explanation);
} catch (err) {
  if (err instanceof GovernorBlockedError) {
    console.error("Blocked:", err.message);
  }
}
```

CommonJS is also supported:

```javascript
const { GovernorClient, GovernorBlockedError } = require("@openclaw/governor-client");
```

### Java

```java
import dev.openclaw.governor.*;
import java.util.Map;

GovernorClient gov = new GovernorClient.Builder()
    .baseUrl("https://openclaw-governor.fly.dev")
    .apiKey("ocg_your_key_here")
    .build();

try {
    GovernorDecision d = gov.evaluate("shell_exec", Map.of("command", "ls -la"));
    System.out.println(d.getDecision());    // "allow" | "review"
    System.out.println(d.getRiskScore());   // 0.0 – 100.0
    System.out.println(d.getExplanation());
} catch (GovernorBlockedError e) {
    System.err.println("Blocked: " + e.getMessage());
}
```

---

## Configuration

### Environment Variables (all SDKs)

| Variable | Default | Description |
|----------|---------|-------------|
| `GOVERNOR_URL` | `http://localhost:8000` | Base URL of the Governor service |
| `GOVERNOR_API_KEY` | *(empty)* | API key (`ocg_…`) sent as `X-API-Key` header |

All SDKs read these automatically when explicit configuration is not provided.

### Python — Module Globals

```python
import governor_client
governor_client.GOVERNOR_URL = "https://..."
governor_client.GOVERNOR_API_KEY = "ocg_..."
```

### TypeScript/JS — Constructor Options

```typescript
const gov = new GovernorClient({
  baseUrl: "https://...",
  apiKey: "ocg_...",
  timeoutMs: 15000,  // default: 10000
});
```

### Java — Builder Pattern

```java
GovernorClient gov = new GovernorClient.Builder()
    .baseUrl("https://...")
    .apiKey("ocg_...")
    .timeout(Duration.ofSeconds(15))  // default: 10s
    .build();
```

---

## API Methods

| Method | Python | TypeScript/JS | Java |
|--------|--------|---------------|------|
| Evaluate tool call | `evaluate_action(tool, args, ctx)` | `gov.evaluate(tool, args, ctx)` | `gov.evaluate(tool, args, ctx)` |
| Evaluate (alias) | `governed_call(tool, args, ctx)` | `gov.governedCall(tool, args, ctx)` | `gov.governedCall(tool, args, ctx)` |
| Admin status | — | `gov.getStatus()` | `gov.getStatus()` |
| Summary | — | `gov.getSummary()` | `gov.getSummary()` |

---

## Error Handling

All SDKs throw/raise `GovernorBlockedError` when the Governor returns a `block` decision. This allows a simple try/catch pattern.

| Language | Error class | Access decision |
|----------|-------------|----------------|
| Python | `GovernorBlockedError` | `str(e)` (message) |
| TypeScript/JS | `GovernorBlockedError` | `e.decision` (full `GovernorDecision`) |
| Java | `GovernorBlockedError` | `e.getMessage()` |

Network and HTTP errors:
- **Python**: Raises standard `httpx` exceptions
- **TypeScript/JS**: Throws native `Error` (fetch failure) or error with HTTP details
- **Java**: Throws `GovernorException` (wraps `IOException`, `InterruptedException`, parse errors)

---

## Authentication

### Getting an API Key

1. **Dashboard**: Log in → **API Keys** tab → copy or regenerate
2. **API**: `POST /auth/me/rotate-key` with JWT auth — returns new key
3. **Admin**: `POST /auth/users/{id}/rotate-key` — rotate any user's key

Keys use the `ocg_` prefix + `secrets.token_urlsafe(32)` (~43 characters).

### Using the API Key

```bash
# cURL
curl -X POST https://governor.fly.dev/actions/evaluate \
  -H "X-API-Key: ocg_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"tool": "shell", "args": {"command": "ls"}}'
```

All three SDKs send the key automatically as the `X-API-Key` header.

---

## Proxy Servers

For environments where agents can't reach the Governor directly (firewall, network isolation), proxy servers are included:

| Proxy | Path | Stack |
|-------|------|-------|
| Python | `openclaw-skills/governed-tools/python-proxy/` | FastAPI |
| JavaScript | `openclaw-skills/governed-tools/js-client/examples/proxy-server.js` | Express |

---

## Testing

```bash
# TypeScript/JS SDK
cd openclaw-skills/governed-tools/js-client
npm test     # 6 tests

# Java SDK
cd openclaw-skills/governed-tools/java-client
mvn test     # 6 tests

# Python proxy
cd openclaw-skills/governed-tools/python-proxy
pytest tests/ -v
```

---

## Publishing

See [`PUBLISHING.md`](../PUBLISHING.md) for full publish instructions for all three registries (PyPI, npm, Maven Central).

---

## Links

| SDK | README | Source |
|-----|--------|--------|
| Python | [`openclaw-skills/governed-tools/README.md`](../openclaw-skills/governed-tools/README.md) | [`governor_client.py`](../openclaw-skills/governed-tools/governor_client.py) |
| TypeScript/JS | [`js-client/README.md`](../openclaw-skills/governed-tools/js-client/README.md) | [`js-client/src/index.ts`](../openclaw-skills/governed-tools/js-client/src/index.ts) |
| Java | [`java-client/README.md`](../openclaw-skills/governed-tools/java-client/README.md) | [`java-client/src/`](../openclaw-skills/governed-tools/java-client/src/main/java/dev/openclaw/governor/) |
