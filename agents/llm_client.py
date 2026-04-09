"""Thin LLM client for the war-room agents.

Supports Groq (default, free tier), Together AI, OpenRouter, or any
OpenAI-compatible endpoint. The key is loaded from environment variables
— never hard-coded.

Usage:
    client = LLMClient()           # reads GROQ_API_KEY from env
    text   = client.ask(system, user_msg)
"""
from __future__ import annotations

import json
import os
from typing import Optional

# We lazy-import `openai` so the deterministic mode never needs it installed.
_openai = None


def _get_openai():
    global _openai
    if _openai is None:
        try:
            import openai as _mod
            _openai = _mod
        except ImportError:
            raise ImportError(
                "LLM mode requires the `openai` package.\n"
                "  pip install openai\n"
            )
    return _openai


# ── Provider presets ────────────────────────────────────────────
PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "env_key": "TOGETHER_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct",
        "env_key": "OPENROUTER_API_KEY",
    },
}


class LLMClient:
    """Stateless wrapper around an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        provider: str = "groq",
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ):
        openai = _get_openai()
        preset = PROVIDERS.get(provider, PROVIDERS["groq"])
        api_key = os.getenv(preset["env_key"], "")
        if not api_key:
            raise EnvironmentError(
                f"LLM mode requires an API key. Set {preset['env_key']} in your environment.\n"
                f"  Groq (free): https://console.groq.com\n"
                f"  Together:    https://api.together.xyz\n"
            )
        self.client = openai.OpenAI(base_url=preset["base_url"], api_key=api_key)
        self.model = model or preset["model"]
        self.temperature = temperature
        self.max_tokens = max_tokens

    def ask(self, system: str, user: str, max_tokens: Optional[int] = None) -> str:
        """Single chat-completion call. Returns the assistant text."""
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content

    def ask_json(self, system: str, user: str, max_tokens: Optional[int] = None) -> dict:
        """Call the LLM and parse the response as JSON (strips markdown fences)."""
        raw = self.ask(system, user, max_tokens)
        cleaned = raw.strip()
        # Strip ```json ... ``` fences if present.
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {"_raw": raw, "_parse_error": True}
