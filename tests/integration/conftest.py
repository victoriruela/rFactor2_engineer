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
import app.core.ai_agents as ai_agents

REQUIRED_MODEL_BASE = "llama3.2"


def _ollama_candidates() -> list[str]:
    env_url = os.getenv("OLLAMA_BASE_URL")
    if env_url:
        return [env_url]
    return [
        "http://localhost:11434",
        "http://host.docker.internal:11434",
    ]


def _resolve_ollama_url_and_tag() -> tuple[str | None, str | None]:
    """Returns the best available llama3.2 model tag, preferring ':latest' over small variants."""
    for base_url in _ollama_candidates():
        try:
            r = requests.get(f"{base_url}/api/tags", timeout=3)
            if r.status_code != 200:
                continue
            models = [m["name"] for m in r.json().get("models", [])]
            candidates = [m for m in models if m.startswith(REQUIRED_MODEL_BASE)]
            if not candidates:
                continue
            for tag in candidates:
                if tag.endswith(":latest"):
                    return base_url, tag
            non_small = [t for t in candidates if not any(s in t for s in [":1b", ":0.5b", ":3b-mini"])]
            return base_url, (non_small[0] if non_small else candidates[-1])
        except Exception:
            continue
    return None, None


@pytest.fixture(scope="session", autouse=True)
def require_ollama():
    base_url, tag = _resolve_ollama_url_and_tag()
    if tag is None:
        pytest.skip(
            f"Ollama not available or no '{REQUIRED_MODEL_BASE}' model loaded. "
            f"Run: ollama pull {REQUIRED_MODEL_BASE}:latest"
        )
    # Ensure the AIAngineer under test calls the resolved Ollama endpoint.
    ai_agents.OLLAMA_BASE_URL = base_url


@pytest.fixture(scope="session")
def ollama_base_url() -> str:
    base_url, _ = _resolve_ollama_url_and_tag()
    return base_url or "http://localhost:11434"


@pytest.fixture(scope="session")
def llm_model_tag() -> str:
    """The resolved llama3.2 tag available on this machine (e.g. 'llama3.2:latest')."""
    _, tag = _resolve_ollama_url_and_tag()
    return tag or f"{REQUIRED_MODEL_BASE}:latest"
