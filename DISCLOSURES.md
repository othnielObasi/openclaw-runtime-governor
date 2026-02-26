# SUBMISSION COMPLIANCE — SURGE × OpenClaw Hackathon

## Rule 1: Original Work Created During the Hackathon

**STATUS: COMPLIANT — with one disclosure required**

The entire codebase was created specifically for this hackathon (Feb 4 – Mar 1, 2026):

| Component | Originality | Notes |
|-----------|-------------|-------|
| `governor-service/` FastAPI backend | ✅ 100% original | Custom-written 5-layer evaluation pipeline, policy engine, schema design, audit logger |
| `governor-service/app/policies/` | ✅ 100% original | Policy dataclass, YAML loader, engine logic — no templates used |
| `governor-service/app/neuro/` | ✅ 100% original | Heuristic risk estimator designed for this project |
| `openclaw-skills/governed-tools/` | ✅ 100% original | Governor client, GovernorBlockedError, governed_call wrapper |
| `openclaw-skills/moltbook-reporter/` | ✅ 100% original | Full Moltbook API client, post composer, autonomous loop, register helper |
| `dashboard/` Next.js | ✅ 100% original | All components hand-written (SummaryPanel, RecentActions, ActionTester, PolicyEditor, AdminStatus) |
| `docs/` | ✅ 100% original | Architecture diagrams, deployment guides |
| Test suite (10 tests) | ✅ 100% original | Written to match the actual implementation |

---

## Rule 2: Open Source Recommended

**STATUS: COMPLIANT**

- Recommend MIT License (the standard for LabLab.ai hackathons per the rules)
- Add `LICENSE` file to the repository root before submission

```
MIT License
Copyright (c) 2026 NOVTIA / Othniel [your surname]
```

---

## Rule 3: No Malware, Keyloggers, or Harmful Functionality

**STATUS: COMPLIANT — verified**

The project is specifically a *safety and governance* tool. A review of every file confirms:

| Check | Result |
|-------|--------|
| No network exfiltration of user data | ✅ Confirmed |
| No keystroke capture or screen recording | ✅ Confirmed |
| No code execution of user-supplied input | ✅ Confirmed — payloads are evaluated but never executed |
| No hidden outbound connections | ✅ Confirmed — only calls to `GOVERNOR_URL` and `MOLTBOOK_API_URL` (both user-configurable) |
| Injection firewall patterns are *detection* logic, not attack code | ✅ Confirmed — patterns are compared against, never executed |
| Policy `args_regex` values match against strings, never `eval()`'d | ✅ Confirmed — Python `re.search()` only |

The `governed-tools/governor_client.py` skill raises `GovernorBlockedError` on block — it does not execute the blocked action. No tool execution happens inside the governor at all.

---

## Rule 4: Third-Party Code, Models, and Services — REQUIRED DISCLOSURES

This is the most important section for submission compliance. Everything used must be named.

### Python Dependencies (`requirements.txt`)

| Library | Version | Purpose | License |
|---------|---------|---------|---------|
| FastAPI | 0.115.0 | HTTP API framework | MIT |
| Uvicorn | 0.30.5 | ASGI server | BSD-3 |
| SQLAlchemy | 2.0.32 | ORM / database layer | MIT |
| Pydantic | 2.8.2 | Data validation & schemas | MIT |
| pydantic-settings | 2.4.0 | Settings from env vars | MIT |
| PyYAML | 6.0.2 | YAML policy file parsing | MIT |
| python-dotenv | 1.0.1 | .env file loading | BSD-3 |
| httpx | 0.27.2 | Async/sync HTTP client (reporter + governed-tools) | BSD-3 |
| pytest | 8.3.3 | Test runner | MIT |

### JavaScript / Node Dependencies (`dashboard/package.json`)

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| Next.js | 14.2.5 | React framework with App Router | MIT |
| React | 18.3.1 | UI rendering | MIT |
| Axios | 1.7.3 | HTTP client for API calls from dashboard | MIT |
| TypeScript | 5.x | Type safety | Apache-2.0 |

### External Services

| Service | Used For | Disclosure Text |
|---------|----------|-----------------|
| **Moltbook** (`moltbook.com`) | Agent social network — reporter posts governance updates to the `lablab` submolt | Required for hackathon prize eligibility |
| **OpenClaw** (runtime) | Agent runtime this tool is built for | Core platform of this hackathon |
| **Fly.io** (optional) | Backend deployment | Infrastructure provider |
| **Vercel** (optional) | Dashboard deployment | Infrastructure provider |

### AI Models / Pre-trained Components

**None.** The neuro risk estimator (`app/neuro/risk_estimator.py`) is a hand-written heuristic function — no ML model, no API call, no pre-trained weights. This is intentional and should be called out positively: it's a deterministic, auditable, explainable risk scorer, which is appropriate for a compliance/governance context.

---

## Submission Form Disclosure Language

Copy this into the "Long Description" or "Disclosures" field of the LabLab submission form:

> **Third-party disclosures:**
> Backend: FastAPI, SQLAlchemy, Pydantic, PyYAML, httpx, Uvicorn (all MIT/BSD).
> Dashboard: Next.js 14, React 18, Axios (all MIT).
> External services: Moltbook API (agent social network, used for autonomous status reporting to the lablab submolt as required by hackathon rules). OpenClaw (the agent runtime platform this tool governs).
> No pre-trained AI models or third-party ML APIs are used. The risk estimator is an original heuristic function.
> All code was written during the Feb 4–Mar 1, 2026 hackathon period.

---

## Action Items Before Submission

- [ ] Add `LICENSE` (MIT) to repo root
- [ ] Add `DISCLOSURES.md` (this file, minus the action items) to repo root
- [ ] Confirm public GitHub repo is set to public
- [ ] Verify no `.env` files with real secrets are committed (add `.env` to `.gitignore`)
- [ ] Add `MOLTBOOK_API_KEY` to Fly.io secrets, not to code
