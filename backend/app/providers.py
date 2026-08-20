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


def _as_token_count(value: object) -> int:
    """Coerce a provider-reported token count to a non-negative int."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


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
        """Read token usage from an OpenAI-compatible response body.

        Tolerates a missing or partial ``usage`` object — an error response or a
        streamed chunk without usage yields zero counts rather than raising, so
        the logging path can never fail on a malformed body.

        Both the Chat Completions spelling (``prompt_tokens`` /
        ``completion_tokens``) and the Responses API spelling (``input_tokens`` /
        ``output_tokens``) are accepted, since the upstream is configurable to
        any OpenAI-compatible provider.
        """
        if not isinstance(response_json, dict):
            return Usage(model="", input_tokens=0, output_tokens=0)

        usage = response_json.get("usage")
        if not isinstance(usage, dict):
            usage = {}

        model = response_json.get("model")
        return Usage(
            model=model if isinstance(model, str) else "",
            input_tokens=_as_token_count(
                usage.get("prompt_tokens", usage.get("input_tokens"))
            ),
            output_tokens=_as_token_count(
                usage.get("completion_tokens", usage.get("output_tokens"))
            ),
        )


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

DEFAULT_PROVIDER = "openai"

_ADAPTERS: dict[str, ProviderAdapter] = {"openai": OpenAIAdapter()}


def get_adapter(provider: str = DEFAULT_PROVIDER) -> ProviderAdapter:
    """Return the adapter for `provider`, falling back to the default."""
    return _ADAPTERS.get(provider, _ADAPTERS[DEFAULT_PROVIDER])
