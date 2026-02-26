import os
from typing import Optional

import httpx
import jwt
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

app = FastAPI(title="OpenClaw Governor Proxy")

# Config via env
PROXY_TOKEN = os.getenv("PROXY_TOKEN")
GOVERNOR_URL = os.getenv("GOVERNOR_URL")
GOVERNOR_API_KEY = os.getenv("GOVERNOR_API_KEY")
# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
REQUIRED_ISSUER = os.getenv("REQUIRED_ISSUER")
REQUIRED_AUDIENCE = os.getenv("REQUIRED_AUDIENCE")
REQUIRED_SCOPE = os.getenv("REQUIRED_SCOPE")


def _validate_jwt(token: str) -> dict:
    options = {"verify_signature": True}
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options=options, audience=REQUIRED_AUDIENCE if REQUIRED_AUDIENCE else None)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token_expired")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=403, detail="invalid_audience")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=403, detail="invalid_issuer")
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_token")

    if REQUIRED_ISSUER and payload.get("iss") != REQUIRED_ISSUER:
        raise HTTPException(status_code=403, detail="invalid_issuer")

    if REQUIRED_SCOPE:
        scopes = payload.get("scope") or payload.get("scopes") or ""
        if isinstance(scopes, str):
            ok = REQUIRED_SCOPE in scopes.split()
        elif isinstance(scopes, list):
            ok = REQUIRED_SCOPE in scopes
        else:
            ok = False
        if not ok:
            raise HTTPException(status_code=403, detail="insufficient_scope")

    return payload


async def _forward_request(request: Request, path: str, method: str, body: Optional[bytes], headers: dict) -> Response:
    if not GOVERNOR_URL:
        raise HTTPException(status_code=500, detail="upstream_not_configured")

    upstream_url = f"{GOVERNOR_URL.rstrip('/')}/{path.lstrip('/')}"

    # prepare headers: remove host, replace authorization with governor api key if provided
    headers = {k: v for k, v in headers.items() if k.lower() != "host"}
    if GOVERNOR_API_KEY:
        headers["Authorization"] = f"Bearer {GOVERNOR_API_KEY}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(method, upstream_url, content=body, headers=headers)

    return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))


@app.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(path: str, request: Request, authorization: Optional[str] = Header(None)):
    # Require Authorization header
    if not authorization:
        raise HTTPException(status_code=401, detail="missing_authorization")

    if authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]

        # Static proxy token allowed
        if PROXY_TOKEN and token == PROXY_TOKEN:
            pass
        else:
            # Validate as JWT if secret present
            if not JWT_SECRET:
                raise HTTPException(status_code=401, detail="unauthorized")
            _validate_jwt(token)
    else:
        raise HTTPException(status_code=401, detail="unsupported_auth_scheme")

    body = await request.body()
    return await _forward_request(request, path, request.method, body, dict(request.headers))
