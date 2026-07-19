"""Provider adapters for TAP.

Each adapter maps a proxied provider (currently OpenAI) onto TAP's internal
model: how to build the upstream URL and how to read token usage out of a
response body. `extract_usage` is the A3 assignment stub.

SECURITY: adapters never receive, store, or log Authorization headers or key
material. They operate only on paths and parsed JSON response bodies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import settings


@dataclass
class Usage:
    """Normalized token usage extracted from a provider response."""

    model: str
    input_tokens: int
    output_tokens: int


class ProviderAdapter(ABC):
    """Interface every provider adapter implements."""

    @abstractmethod
    def build_upstream_url(self, path: str) -> str:
        """Return the absolute upstream URL for a proxied `/v1/{path}` request."""
        ...

    @abstractmethod
    def extract_usage(self, response_json: dict) -> Usage:
        """Read token usage out of a parsed provider response body."""
        ...


class OpenAIAdapter(ProviderAdapter):
    """Adapter for the OpenAI-compatible upstream."""

    def build_upstream_url(self, path: str) -> str:
        return f"{settings.upstream_base_url}/v1/{path}"

    def extract_usage(self, response_json: dict) -> Usage:
        # ============================================================
        # ASSIGNMENT: A3 extract OpenAI usage
        # ------------------------------------------------------------
        # Implement: read the `usage` object from an OpenAI chat completion response
        #            and return Usage(model, input_tokens, output_tokens).
        # Why:       token counts feed cost computation (A4) and the metrics endpoints.
        # Done when: a real /v1/chat/completions response yields correct prompt/completion
        #            token counts (0 or None handled safely).
        # Reference: https://platform.openai.com/docs/api-reference/chat/object
        #            https://docs.python.org/3/library/json.html
        # ============================================================
        raise NotImplementedError("ASSIGNMENT: A3 extract OpenAI usage")
