"""
Integration test configuration.

Requires ollama running locally with llama3.2 (any tag) loaded.
All tests in this package are skipped automatically if Ollama is unavailable.

Run explicitly with:
    pytest -m integration -v
"""
import os
import requests
import pytest

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
REQUIRED_MODEL_BASE = "llama3.2"


def _get_llama32_tag() -> str | None:
    """Returns the best available llama3.2 model tag, preferring ':latest' over small variants."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        if r.status_code != 200:
            return None
        models = [m["name"] for m in r.json().get("models", [])]
        candidates = [m for m in models if m.startswith(REQUIRED_MODEL_BASE)]
        if not candidates:
            return None
        # Prefer 'latest' tag; deprioritize explicit small-parameter tags (1b, 0.5b, etc.)
        for tag in candidates:
            if tag.endswith(":latest"):
                return tag
        # Fall back to largest available (heuristic: no parameter count in tag)
        non_small = [t for t in candidates if not any(s in t for s in [":1b", ":0.5b", ":3b-mini"])]
        return non_small[0] if non_small else candidates[-1]
    except Exception:
        return None


@pytest.fixture(scope="session", autouse=True)
def require_ollama():
    tag = _get_llama32_tag()
    if tag is None:
        pytest.skip(
            f"Ollama not available or no '{REQUIRED_MODEL_BASE}' model loaded at {OLLAMA_BASE_URL}. "
            f"Run: ollama pull {REQUIRED_MODEL_BASE}:latest"
        )


@pytest.fixture(scope="session")
def llm_model_tag() -> str:
    """The resolved llama3.2 tag available on this machine (e.g. 'llama3.2:latest')."""
    return _get_llama32_tag()
