import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class GatewayResult:
    answer: str
    model: str
    usage: dict[str, int] | None = None


class Gateway(Protocol):
    async def complete(self, messages: list[dict[str, str]], request_id: str) -> GatewayResult: ...

    def stream(self, messages: list[dict[str, str]], request_id: str) -> AsyncIterator[str]: ...


class HttpGateway:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client
        self.semaphore = asyncio.Semaphore(settings.ai_concurrency)

    async def complete(self, messages: list[dict[str, str]], request_id: str) -> GatewayResult:
        async with self.semaphore:
            response = await self.client.post(
                f"{self.settings.ai_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.ai_api_key}",
                    "X-Request-ID": request_id,
                },
                json={
                    "model": self.settings.ai_model,
                    "messages": messages,
                    "max_tokens": self.settings.ai_max_tokens,
                },
                timeout=self.settings.ai_timeout_seconds,
            )
        response.raise_for_status()
        data = response.json()
        return GatewayResult(
            answer=data["choices"][0]["message"]["content"],
            model=data.get("model", self.settings.ai_model),
            usage=data.get("usage"),
        )

    async def stream(self, messages: list[dict[str, str]], request_id: str) -> AsyncIterator[str]:
        async with self.semaphore:
            async with self.client.stream(
                "POST",
                f"{self.settings.ai_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.ai_api_key}",
                    "X-Request-ID": request_id,
                },
                json={
                    "model": self.settings.ai_model,
                    "messages": messages,
                    "max_tokens": self.settings.ai_max_tokens,
                    "stream": True,
                },
                timeout=self.settings.ai_timeout_seconds,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    data = json.loads(line[6:])
                    delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        yield delta


class FakeGateway:
    async def complete(self, messages: list[dict[str, str]], request_id: str) -> GatewayResult:
        return GatewayResult("The supplied source supports this answer. [c1]", "fake-model")

    async def stream(self, messages: list[dict[str, str]], request_id: str) -> AsyncIterator[str]:
        yield "The supplied source supports "
        yield "this answer. [c1]"
