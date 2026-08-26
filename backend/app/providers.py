"""Provider adapters.

Each adapter maps a proxied provider onto TAP's internal model: how to build the
upstream URL, and how to read token usage out of a response body. Adapters only
ever see paths and parsed JSON bodies, never headers or key material.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import settings

DEFAULT_PROVIDER = "openai"


@dataclass
class Usage:
    model: str
    input_tokens: int
    output_tokens: int
    # The subset of input_tokens the provider served from its prompt cache.
    cached_input_tokens: int = 0


def _as_token_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _cached_input_tokens(usage: dict) -> int:
    """Prompt-cache hits, reported under a details block that may be absent.

    Chat Completions nests it under `prompt_tokens_details`, the Responses API
    under `input_tokens_details`.
    """
    for key in ("prompt_tokens_details", "input_tokens_details"):
        details = usage.get(key)
        if isinstance(details, dict):
            return _as_token_count(details.get("cached_tokens"))
    return 0


class ProviderAdapter(ABC):
    @abstractmethod
    def build_upstream_url(self, path: str) -> str: ...

    @abstractmethod
    def extract_usage(self, response_json: dict) -> Usage: ...


class OpenAIAdapter(ProviderAdapter):
    def build_upstream_url(self, path: str) -> str:
        return f"{settings.upstream_base_url}/v1/{path}"

    def extract_usage(self, response_json: dict) -> Usage:
        """Read token usage, yielding zeros for a body that reports none.

        Accepts the Chat Completions spelling (prompt_tokens /
        completion_tokens) and the Responses API spelling (input_tokens /
        output_tokens), including each one's prompt-cache detail block.
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
            cached_input_tokens=_cached_input_tokens(usage),
        )


_ADAPTERS: dict[str, ProviderAdapter] = {"openai": OpenAIAdapter()}


def get_adapter(provider: str = DEFAULT_PROVIDER) -> ProviderAdapter:
    return _ADAPTERS.get(provider, _ADAPTERS[DEFAULT_PROVIDER])
