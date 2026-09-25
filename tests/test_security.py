import httpx
import pytest

from app.core.config import Settings
from app.core.security import client_ip
from app.providers.turnstile import HttpTurnstile


def test_forwarded_ip_only_from_trusted_proxy():
    settings = Settings(_env_file=None, trusted_proxies="172.30.80.10/32")
    assert client_ip("198.51.100.8", "203.0.113.7", settings) == ("198.51.100.8", "socket")
    assert client_ip("172.30.80.10", "2001:db8::1", settings) == ("2001:db8::1", "trusted_proxy")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,expected",
    [
        (
            {"success": True, "hostname": "chat.mobinshaterian.com", "action": "client_register"},
            True,
        ),
        ({"success": True, "hostname": "evil.example", "action": "client_register"}, False),
        ({"success": True, "hostname": "chat.mobinshaterian.com", "action": "other"}, False),
        (
            {"success": False, "hostname": "chat.mobinshaterian.com", "action": "client_register"},
            False,
        ),
    ],
)
async def test_turnstile_checks_hostname_and_action(payload, expected):
    async def handler(request):
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = HttpTurnstile(Settings(_env_file=None), client)
        assert await service.verify("token", "198.51.100.8") is expected
