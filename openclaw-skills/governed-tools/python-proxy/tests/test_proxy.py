import os

from fastapi.testclient import TestClient

from proxy_server import app


def test_missing_auth_returns_401():
    client = TestClient(app)
    r = client.get("/proxy/somepath")
    assert r.status_code == 401


def test_static_token_allows_forward(monkeypatch):
    os.environ["PROXY_TOKEN"] = "static-secret"
    # monkeypatch upstream forward to avoid real HTTP call
    async def fake_forward(request, path, method, body, headers):
        from fastapi.responses import Response

        return Response(content=b"ok", status_code=200, headers={})

    monkeypatch.setattr("proxy_server._forward_request", fake_forward)

    client = TestClient(app)
    r = client.get("/proxy/ok", headers={"Authorization": "Bearer static-secret"})
    assert r.status_code == 200
    assert r.content == b"ok"
