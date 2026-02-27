# @openclaw/governor-client

TypeScript/JavaScript client for the **OpenClaw Governor** – a runtime governance layer for AI agents.

The Governor evaluates every tool invocation against configurable policies and
returns an **allow / block / review** decision before the tool executes.

## Installation

```bash
npm install @openclaw/governor-client
```

## Quick start

```typescript
import { GovernorClient, GovernorBlockedError } from "@openclaw/governor-client";

const gov = new GovernorClient({
  baseUrl: "https://openclaw-governor.fly.dev",
  apiKey: "ocg_your_key_here",
});

try {
  const decision = await gov.evaluate("shell_exec", { command: "ls -la /tmp" });
  console.log(decision.decision);   // "allow" | "review"
  console.log(decision.risk_score); // 0 – 100
  console.log(decision.explanation);
} catch (err) {
  if (err instanceof GovernorBlockedError) {
    console.error("Blocked:", err.message);
  }
}
```

## Configuration

| Option | Env variable | Default | Description |
|---|---|---|---|
| `baseUrl` | `GOVERNOR_URL` | `http://localhost:8000` | Base URL of the Governor service |
| `apiKey` | `GOVERNOR_API_KEY` | *(empty)* | API key (`ocg_…`) sent as `X-API-Key` header |
| `timeoutMs` | — | `10000` | Request timeout in milliseconds |

Environment variables are read automatically when options are not provided.

## API

### `new GovernorClient(options?)`

Create a client instance. All options are optional.

### `client.evaluate(tool, args, context?) → Promise<GovernorDecision>`

Evaluate a tool call. Throws `GovernorBlockedError` if the decision is `"block"`.

### `client.governedCall(tool, args, context?) → Promise<GovernorDecision>`

Alias for `evaluate`.

### `client.getStatus() → Promise<object>`

Fetch the current admin status (kill switch state, etc.).

### `client.getSummary() → Promise<object>`

Fetch the governor summary (total actions, block rate, etc.).

### `GovernorBlockedError`

Error thrown when the Governor blocks a tool invocation. Has a `.decision` property
with the full `GovernorDecision` object.

## Requirements

- Node.js ≥ 18 (uses built-in `fetch`)
- Zero runtime dependencies

## License

MIT — see [LICENSE](../LICENSE).
