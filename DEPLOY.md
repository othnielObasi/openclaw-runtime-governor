# Deployment Guide

## Governor Service → Fly.io

```bash
cd governor-service
fly launch        # first time only
fly deploy
```

Set secrets on Fly:
```bash
fly secrets set GOVERNOR_DATABASE_URL="postgresql://..."
```

## Dashboard → Vercel

```bash
cd dashboard
npm install
npm run build
```

Then import the repo into Vercel and set:

```
NEXT_PUBLIC_GOVERNOR_API=https://your-app.fly.dev
```

## Local Development

```bash
# Backend
cd governor-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Dashboard (new terminal)
cd dashboard
npm install
npm run dev
# open http://localhost:3000
```

## Environment Variables

### Governor Service
| Variable | Default | Description |
|----------|---------|-------------|
| `GOVERNOR_DATABASE_URL` | `sqlite:///./governor.db` | Database URL |
| `GOVERNOR_LOG_SQL` | `false` | Print SQL to stdout |
| `GOVERNOR_ALLOW_CORS_ORIGINS` | `["*"]` | CORS allowed origins |
| `POLICIES_PATH` | `app/policies/base_policies.yml` | Base policy YAML |

### Dashboard
| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_GOVERNOR_API` | URL of the governor service |

## Auth Setup

### Environment Variables

Add to governor-service (Fly secrets or .env):
```
GOVERNOR_JWT_SECRET=your-long-random-secret-here
GOVERNOR_ADMIN_EMAIL=admin@yourorg.io
GOVERNOR_ADMIN_PASSWORD=your-secure-password
GOVERNOR_ADMIN_NAME=Governor Admin
```

On first startup, a default admin account is created automatically from these env vars.

### Default Credentials (local dev only)
- Email: `admin@openclaw.io`
- Password: `changeme`

**Change these before any deployment.**

### Role Summary
| Role | Tabs visible | Kill switch | Policy editor | User management |
|------|-------------|-------------|---------------|-----------------|
| admin | All | ✓ | ✓ | ✓ |
| operator | Dashboard, Tester, Simulator, Policies, Audit | ✓ | ✓ | ✗ |
| auditor | Dashboard, Audit | ✗ | ✗ | ✗ |

### Adding operators (after deployment)
1. Login as admin
2. Go to User Management tab
3. Click + ADD OPERATOR
4. Set role to `operator` or `auditor`
