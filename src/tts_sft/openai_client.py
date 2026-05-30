"""Thin wrapper around the OpenAI-compatible chat completions API.

The wrapper exists so scripts don't have to import or configure ``openai``
directly; it also makes it easy to swap in a fake client in tests.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GenerationParams:
    temperature: float = 0.6
    top_p: float = 0.95
    max_tokens: int = 8192
    seed: int | None = None
    stop: list[str] | None = None


class OpenAIChatClient:
    """Chat completions client backed by an OpenAI-compatible endpoint.

    Works against the public OpenAI API, local vLLM (``--port 8000``), or
    any other server that implements ``/v1/chat/completions``.
    """

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 600.0,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - import error path
            raise ImportError(
                "The `openai` package is required. Install with: pip install openai"
            ) from e

        self.model = model
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key or "EMPTY",
            timeout=timeout,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        params: GenerationParams,
    ) -> str:
        """Run a single chat completion and return the assistant text."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "max_tokens": params.max_tokens,
        }
        if params.seed is not None:
            kwargs["seed"] = params.seed
        if params.stop:
            kwargs["stop"] = params.stop

        resp = self.client.chat.completions.create(**kwargs)
        if not resp.choices:
            raise RuntimeError("Empty `choices` in chat completion response.")
        msg = resp.choices[0].message
        content = getattr(msg, "content", None) or ""
        return content
