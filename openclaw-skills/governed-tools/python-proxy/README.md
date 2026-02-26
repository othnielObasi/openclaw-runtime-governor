# Python FastAPI proxy (example)

This is a minimal, hardened FastAPI proxy example for forwarding browser requests to the Governor backend without exposing tenant API keys.

Environment variables:

- `PROXY_TOKEN` — optional static bearer token allowed to call the proxy.
- `JWT_SECRET` — optional secret (or public key) used to validate incoming JWTs.
- `JWT_ALGORITHM` — default `HS256`.
- `REQUIRED_ISSUER` — optional issuer to require on incoming JWTs.
- `REQUIRED_AUDIENCE` — optional audience to require on incoming JWTs.
- `REQUIRED_SCOPE` — optional required scope claim (space-separated or list) in the JWT.
- `GOVERNOR_URL` — upstream Governor base URL to forward requests to.
- `GOVERNOR_API_KEY` — optional API key to set when forwarding to Governor.

Run locally for development:

```bash
pip install -r requirements.txt
PROXY_TOKEN=devsecret GOVERNOR_URL=https://governor.example:8443 uvicorn proxy_server:app --reload
```
