import json
from pathlib import Path

import httpx
import pytest

from app.main import app


def test_pinned_openapi_documents_bearer_and_stream():
    pinned = json.loads(Path("contracts/openapi.json").read_text())
    assert pinned == app.openapi()
    assert pinned["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    path = pinned["paths"]["/api/v1/conversations/{conversation_id}/messages:stream"]["post"]
    assert "text/event-stream" in path["responses"]["200"]["content"]
    assert any(
        item["name"] == "idempotency-key" and item["required"] for item in path["parameters"]
    )


@pytest.mark.asyncio
async def test_cors_exact_chat_origin_and_safe_auth_error():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = "/api/v1/conversations/01900000-0000-7000-8000-000000000001"
        preflight = await client.options(
            path,
            headers={
                "Origin": "https://chat.mobinshaterian.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.headers["access-control-allow-origin"] == "https://chat.mobinshaterian.com"
        blocked = await client.options(
            path, headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
        )
        assert "access-control-allow-origin" not in blocked.headers
        response = await client.get(path)
        assert response.status_code == 401
        assert set(response.json()) == {"code", "message", "request_id"}
        assert response.headers["X-Request-ID"] == response.json()["request_id"]
