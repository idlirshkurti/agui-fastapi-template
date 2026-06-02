from __future__ import annotations

import os


def _require_env(name: str, hint: str) -> str:
    """Return the value of *name* from the environment or raise ``ValueError``.

    Parameters
    ----------
    name:
        The environment variable name.
    hint:
        A short human-readable description shown in the error message so
        developers know exactly what to add to their ``.env`` file.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(
            f"{name} is not set. {hint} See .env.example for reference."
        )
    return value


def get_tavily_api_key() -> str:
    """Return the Tavily API key from the environment."""
    return _require_env(
        "TAVILY_API_KEY",
        "Add your Tavily key (https://tavily.com — free tier available).",
    )


def get_openai_api_key() -> str:
    """Return the OpenAI API key used for document embeddings."""
    return _require_env(
        "OPENAI_API_KEY",
        "Add your OpenAI key (https://platform.openai.com/api-keys).",
    )
