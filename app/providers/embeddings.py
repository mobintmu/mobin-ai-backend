import httpx

from app.core.config import Settings


class EmbeddingGateway:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.post(
            f"{self.settings.embedding_base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {self.settings.embedding_api_key}"},
            json={"model": self.settings.embedding_model, "input": texts},
            timeout=30,
        )
        response.raise_for_status()
        rows = sorted(response.json()["data"], key=lambda row: row["index"])
        vectors = [row["embedding"] for row in rows]
        if len(vectors) != len(texts) or any(len(vector) != 1536 for vector in vectors):
            raise ValueError("Embedding response has unexpected dimensions")
        return vectors
