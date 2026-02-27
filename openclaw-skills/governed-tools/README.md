# openclaw-governor-client

Python client for the **OpenClaw Governor** – a runtime governance layer for AI agents.

The Governor evaluates every tool invocation against configurable policies and
returns an **allow / block / review** decision before the tool executes.

## Installation

```bash
pip install openclaw-governor-client
```

## Quick start

```python
from governor_client import evaluate_action, GovernorBlockedError
import governor_client

# Set your API key (or export GOVERNOR_API_KEY in your environment)
governor_client.GOVERNOR_API_KEY = "ocg_your_key_here"
governor_client.GOVERNOR_URL = "https://openclaw-governor.fly.dev"

# Evaluate a tool call against the Governor
try:
    decision = evaluate_action(
        tool="shell_exec",
        args={"command": "ls -la /tmp"},
        context={"session_id": "abc-123"},
    )
    print(decision["decision"])      # "allow" | "review"
    print(decision["risk_score"])    # 0.0 – 1.0
    print(decision["explanation"])
except GovernorBlockedError as e:
    print(f"Blocked: {e}")
```

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `GOVERNOR_URL` | `http://localhost:8000` | Base URL of the Governor service |
| `GOVERNOR_API_KEY` | *(empty)* | API key (`ocg_…`) sent as `X-API-Key` header |

You can also set them programmatically:

```python
import governor_client

governor_client.GOVERNOR_URL = "https://openclaw-governor.fly.dev"
governor_client.GOVERNOR_API_KEY = "ocg_your_key_here"
```

## API

### `evaluate_action(tool, args, context=None) → dict`

Send a tool call to the Governor for evaluation.

Returns the full decision dict:

```python
{
    "decision": "allow",        # "allow" | "block" | "review"
    "risk_score": 0.15,
    "explanation": "Low-risk read operation",
    "policy_ids": ["shell-guard"],
    "modified_args": None,
}
```

Raises `GovernorBlockedError` if the decision is `"block"`.

### `governed_call(tool, args, context=None) → dict`

Convenience wrapper around `evaluate_action`. Identical behaviour — callers
should inspect `decision` for `"review"` and handle accordingly.

### `GovernorBlockedError`

Exception raised when the Governor blocks a tool invocation. Subclass of
`RuntimeError`.

## Requirements

- Python ≥ 3.9
- [httpx](https://www.python-httpx.org/) ≥ 0.24.0

## License

MIT — see [LICENSE](LICENSE).
