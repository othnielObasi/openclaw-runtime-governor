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

### `client.ingestSpans(spans) → Promise<IngestResult>`

Batch-ingest agent trace spans (up to 500). Idempotent — duplicate `span_id` values are silently skipped.

Valid span kinds: `agent`, `llm`, `tool`, `governance`, `retrieval`, `chain`, `custom`.

Returns `{ inserted, skipped }`.

```ts
await gov.ingestSpans([
  { trace_id: "t-123", span_id: "s-1", kind: "agent", name: "main", start_time: new Date().toISOString() },
  { trace_id: "t-123", span_id: "s-2", kind: "llm", name: "gpt-4", start_time: new Date().toISOString(), parent_span_id: "s-1" },
]);
```

### `client.listTraces(options?) → Promise<TraceListItem[]>`

List traces. Optional filters: `agent_id`, `session_id`, `has_blocks`, `limit`, `offset`.

### `client.getTrace(traceId) → Promise<TraceDetail>`

Full trace detail — all spans plus correlated governance decisions.

### `client.deleteTrace(traceId) → Promise<DeleteTraceResult>`

Delete all spans for a trace. Returns `{ trace_id, spans_deleted }`.

### `GovernorBlockedError`

Error thrown when the Governor blocks a tool invocation. Has a `.decision` property
with the full `GovernorDecision` object.

## Trace correlation

Pass `trace_id` and `span_id` in the `context` parameter of `evaluate()` to auto-create
a governance span in the agent's trace tree:

```ts
const decision = await gov.evaluate("shell_exec", { command: "ls" }, {
  trace_id: "t-123",
  span_id: "s-2",   // governance span will be a child of this span
  agent_id: "my-agent",
});
```

## Requirements

- Node.js ≥ 18 (uses built-in `fetch`)
- Zero runtime dependencies

## License

MIT — see [LICENSE](../LICENSE).
