"""Factories for external services. Tests replace these (monkeypatch) with fakes."""
from app.extraction.llm import OpenAIClient, LLMClient
from app.search.embeddings import Embedder, OpenAIEmbedder


def get_llm() -> LLMClient:
    return OpenAIClient()


def get_embedder() -> Embedder:
    return OpenAIEmbedder()
