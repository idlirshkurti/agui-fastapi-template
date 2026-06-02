from __future__ import annotations

import os


def get_tavily_api_key() -> str:
    """Return the Tavily API key from the environment.

    Raises
    ------
    ValueError
        If ``TAVILY_API_KEY`` is not set, with a message that points the
        developer to the right place to fix it.
    """
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "TAVILY_API_KEY is not set. "
            "Add it to your environment or to a .env file. "
            "See .env.example for reference."
        )
    return key
