# Architecture – OpenClaw Governor (Harmonized)

## Request Lifecycle

```
OpenClaw Agent
     │
     ▼ POST /actions/evaluate
 governor-service (FastAPI)
     │
     ├─1─ Kill Switch          ← instant block if globally halted
     │
     ├─2─ Injection Firewall   ← scans payload for prompt-injection patterns
     │
     ├─3─ Scope Enforcer       ← enforces allowed_tools from context
     │
     ├─4─ Policy Engine        ← YAML base policies + DB dynamic policies
     │        ├─ base_policies.yml  (loaded at startup)
     │        └─ PolicyModel (DB)   (created at runtime via API)
     │
     ├─5─ Neuro Risk Estimator ← heuristic scoring (tool type, keywords,
     │                           bulk-recipients) → elevates risk_score
     │
     └─► ActionDecision { decision, risk_score, explanation, policy_ids }
              │
              ▼
         Audit Logger  →  action_logs table (SQLite / Postgres)
```

## File Map

```
governor-service/
├── app/
│   ├── main.py               ← FastAPI app init, CORS, route registration
│   ├── config.py             ← Settings (pydantic-settings, env vars)
│   ├── database.py           ← SQLAlchemy engine, SessionLocal, db_session()
│   ├── models.py             ← ActionLog, PolicyModel ORM models
│   ├── schemas.py            ← Pydantic schemas (ActionInput, ActionDecision, etc.)
│   ├── state.py              ← In-memory kill switch with thread lock
│   ├── api/
│   │   ├── routes_actions.py ← POST /actions/evaluate, GET /actions
│   │   ├── routes_policies.py← GET/POST/DELETE /policies
│   │   ├── routes_summary.py ← GET /summary/moltbook
│   │   └── routes_admin.py   ← GET /admin/status, POST /admin/kill|resume
│   ├── policies/
│   │   ├── engine.py         ← evaluate_action() – full evaluation pipeline
│   │   ├── loader.py         ← Policy dataclass, load_base_policies(), load_db_policies()
│   │   └── base_policies.yml ← YAML-defined static policies
│   ├── neuro/
│   │   └── risk_estimator.py ← estimate_neural_risk() heuristic
│   └── telemetry/
│       └── logger.py         ← log_action() – writes to action_logs table
│
dashboard/
├── app/
│   ├── layout.tsx            ← Root layout (dark theme, nav)
│   └── page.tsx              ← Dashboard page (grid of components)
└── components/
    ├── ApiClient.ts          ← Axios instance pointing to NEXT_PUBLIC_GOVERNOR_API
    ├── ActionTester.tsx      ← POST /actions/evaluate UI
    ├── AdminStatus.tsx       ← Kill switch toggle
    ├── PolicyEditor.tsx      ← Create/delete dynamic policies
    └── RecentActions.tsx     ← GET /actions audit feed
│
openclaw-skills/
├── governed-tools/
│   ├── governor_client.py    ← evaluate_action(), governed_call() wrappers
│   └── skill.toml
└── moltbook-reporter/
    ├── reporter.py           ← fetch_summary(), build_status_text()
    └── skill.toml
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Layered evaluation (kill → firewall → scope → policy → neuro) | Short-circuit on most critical checks first |
| YAML + DB policies | Static policies version-controlled; dynamic policies editable at runtime |
| `Policy.matches()` method | Encapsulates matching logic cleanly; easy to extend |
| Neuro estimator raises risk, not decision | Risk scoring is advisory; only explicit policies change allow→block |
| Context metadata indexed in DB | Enables efficient filtering by agent_id, user_id, channel |
| CORS middleware on FastAPI | Allows dashboard on different origin (Vercel) to talk to backend (Fly.io) |
