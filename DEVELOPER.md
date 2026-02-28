# Developer Guide

> **New here?** Start with the comprehensive [Getting Started Guide](docs/GETTING_STARTED.md) — it covers setup, architecture, integration, deployment, and everything in between.

This file is a quick-reference for contributors already familiar with the project.

---

## Quick Reference

### Run Locally

```bash
# Backend
cd governor-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Dashboard (separate terminal)
cd dashboard
npm install
NEXT_PUBLIC_GOVERNOR_API=http://localhost:8000 npm run dev
```

Default login: `admin` / `changeme`

### Run Tests

```bash
cd governor-service
pytest tests/ -v          # 246 tests across 8 files
```

### Run Demo Agent

```bash
python demo_agent.py              # 17 evaluations + 8 verifications
python demo_agent.py --verbose    # with trace detail
```

---

## Key Files for Contributors

| What | Where |
|------|-------|
| Evaluation pipeline | `governor-service/app/policies/engine.py` |
| ORM models (17 tables) | `governor-service/app/models.py` |
| Request/response schemas | `governor-service/app/schemas.py` |
| Base governance policies | `governor-service/app/policies/base_policies.yml` |
| Chain analysis (11 patterns) | `governor-service/app/chain_analysis.py` |
| Verification engine (8 checks) | `governor-service/app/verification/engine.py` |
| Escalation engine | `governor-service/app/escalation/engine.py` |
| Auth (JWT, API keys, RBAC) | `governor-service/app/auth/` |
| SSE event bus | `governor-service/app/event_bus.py` |
| Dashboard (16 tabs) | `dashboard/components/GovernorDashboard.jsx` |
| Python SDK | `openclaw-skills/governed-tools/governor_client.py` |
| JS/TS SDK | `openclaw-skills/governed-tools/js-client/` |
| Java SDK | `openclaw-skills/governed-tools/java-client/` |
| Test fixtures | `governor-service/conftest.py` |

---

## Extending the System

### Add a Policy (YAML)

Edit `governor-service/app/policies/base_policies.yml`:

```yaml
- policy_id: my-custom-rule
  description: "Block dangerous custom tool"
  tool: "my_dangerous_tool"
  severity: critical
  action: block
  args_regex: "(dangerous_pattern)"
```

### Add a Pipeline Layer

1. Implement the check in `app/` (new file or existing)
2. Hook it into `evaluate_action()` in `app/policies/engine.py`
3. Emit a `TraceStep` for observability
4. Add tests in `tests/test_governor.py`

### Add a Dashboard Tab

Use inline styles with the project design tokens:

```javascript
const C = {
  bg0: "#080e1a", bg1: "#0f1b2d", bg2: "#1d3452", line: "#1d3452",
  p1: "#e2e8f0", p2: "#8fa3bf", p3: "#4a6785",
  accent: "#e8412a", green: "#22c55e", amber: "#f59e0b", red: "#ef4444",
};
const mono = "'IBM Plex Mono', monospace";
const sans = "'DM Sans', sans-serif";
```

Use `ApiClient` for API calls, `useAuth()` for auth context.

### Add a Test

```python
from app.schemas import ActionInput
from app.policies.engine import evaluate_action

def test_my_scenario():
    inp = ActionInput(tool="shell", args={"command": "echo hello"}, context={"agent_id": "test"})
    result = evaluate_action(inp)
    assert result.decision == "allow"
    assert result.risk_score < 50
```

---

## Code Style

- **Python**: Type hints, Pydantic v2, `snake_case`
- **TypeScript/React**: Inline styles, functional components, `camelCase`
- **Commits**: Conventional commits — `feat:`, `fix:`, `docs:`, `test:`

---

## Contributing

1. Fork → branch (`feat/my-feature`) → code + tests
2. `pytest tests/ -v` (all 246 pass)
3. `cd dashboard && npm run build` (clean build)
4. PR against `main`

---

## Documentation Map

| Document | Description |
|----------|-------------|
| **[Getting Started](docs/GETTING_STARTED.md)** | Comprehensive setup, architecture, integration, deployment guide |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, request lifecycle |
| [GOVERNANCE_AUDIT.md](docs/GOVERNANCE_AUDIT.md) | Governance coverage audit |
| [SDK_OVERVIEW.md](docs/SDK_OVERVIEW.md) | Multi-language SDK comparison |
| [AGENT.md](docs/AGENT.md) | Demo agent documentation |
| [DEPLOY.md](DEPLOY.md) | Deployment instructions (Fly.io, Vultr, Vercel) |
| [PUBLISHING.md](PUBLISHING.md) | SDK publishing (PyPI, npm, Maven) |

---

**License**: [MIT](LICENSE) — Copyright © 2026 Sovereign AI Lab
