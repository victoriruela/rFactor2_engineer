"""E2E API test configuration. Requires a running backend at RF2_API_URL (default: http://localhost:8000)."""
import os

import httpx
import pytest

BASE_URL = os.getenv("RF2_API_URL", "http://localhost:8000")


def _server_reachable() -> bool:
    try:
        httpx.get(f"{BASE_URL}/models", timeout=3)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def skip_if_offline():
    if not _server_reachable():
        pytest.skip(f"Backend not reachable at {BASE_URL} — skipping E2E API tests")


@pytest.fixture
async def async_client():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        yield c
