"""The ONLY file that knows about OpenAI. Swap provider = rewrite this file."""
import os
from typing import Protocol

from .schema import InvoiceLLM


class LLMClient(Protocol):
    model: str

    def extract(self, system: str, user: str) -> tuple[InvoiceLLM, dict]:
        """Return (parsed_invoice, usage_dict). Raise on failure."""


class OpenAIClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        from openai import OpenAI  # imported lazily so tests don't need a key

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set (put it in backend/.env)")
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._client = OpenAI(api_key=key, max_retries=3, timeout=90)

    def extract(self, system: str, user: str) -> tuple[InvoiceLLM, dict]:
        resp = self._client.chat.completions.parse(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format=InvoiceLLM,
            temperature=0,  # extraction, not creativity: same input, same output
        )
        msg = resp.choices[0].message
        if msg.refusal or msg.parsed is None:
            raise RuntimeError(f"Model returned no parsable result: {msg.refusal or 'empty'}")
        u = resp.usage
        usage = {"prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens} if u else {}
        return msg.parsed, usage
