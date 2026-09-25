from typing import Protocol

import httpx

from app.core.config import Settings


class Turnstile(Protocol):
    async def verify(self, token: str, ip: str) -> bool: ...


class HttpTurnstile:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    async def verify(self, token: str, ip: str) -> bool:
        try:
            response = await self.client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": self.settings.turnstile_secret, "response": token, "remoteip": ip},
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
            return bool(
                data.get("success")
                and data.get("hostname") == self.settings.turnstile_hostname
                and data.get("action") == self.settings.turnstile_action
            )
        except (httpx.HTTPError, ValueError):
            return False


class FakeTurnstile:
    async def verify(self, token: str, ip: str) -> bool:
        return token == "test-pass"
