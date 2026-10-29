import os
from typing import Protocol

MAX_CHARS = 8000  # per page; keeps one request well inside the model's input limit


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        from openai import OpenAI

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.model = model or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
        self._client = OpenAI(api_key=key, max_retries=3, timeout=60)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 32):
            batch = [t[:MAX_CHARS] for t in texts[i:i + 32]]
            resp = self._client.embeddings.create(model=self.model, input=batch)
            out.extend(d.embedding for d in resp.data)
        return out
