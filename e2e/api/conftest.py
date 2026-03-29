"""E2E API test configuration. Requires a running backend at RF2_API_URL (default: http://localhost:8000)."""
import os

import httpx
import pytest

_ENV_BASE_URL = os.getenv("RF2_API_URL")


def _base_url_candidates() -> list[str]:
    if _ENV_BASE_URL:
        return [_ENV_BASE_URL]
    return [
        "http://localhost:8000",
        "http://host.docker.internal:8000",
    ]


def _resolve_base_url() -> str | None:
    for candidate in _base_url_candidates():
        try:
            r = httpx.get(f"{candidate}/models", timeout=3)
            if r.status_code == 200:
                return candidate
        except Exception:
            continue
    return None


def _server_reachable() -> bool:
    return _resolve_base_url() is not None


@pytest.fixture(scope="session", autouse=True)
def skip_if_offline():
    if not _server_reachable():
        pytest.skip("Backend not reachable at localhost:8000 nor host.docker.internal:8000 — skipping E2E API tests")


@pytest.fixture(scope="session")
def base_url() -> str:
    resolved = _resolve_base_url()
    return resolved or (_ENV_BASE_URL or "http://localhost:8000")


@pytest.fixture
async def async_client(base_url):
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as c:
        yield c
