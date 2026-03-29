"""E2E tests for the FastAPI backend. Requires a running server (see conftest.py)."""
import pytest


@pytest.mark.asyncio
async def test_models_endpoint_reachable(async_client):
    r = await async_client.get("/models")
    assert r.status_code == 200
    body = r.json()
    assert "models" in body
    assert isinstance(body["models"], list)


@pytest.mark.asyncio
async def test_sessions_endpoint_reachable(async_client):
    r = await async_client.get("/sessions")
    assert r.status_code == 200
    body = r.json()
    assert "sessions" in body
    assert isinstance(body["sessions"], list)


@pytest.mark.asyncio
async def test_cleanup_endpoint(async_client):
    r = await async_client.post("/cleanup")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_analyze_missing_files_returns_422(async_client):
    """Sending no files should return 422 Unprocessable Entity."""
    r = await async_client.post("/analyze")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_analyze_wrong_format_returns_error(async_client):
    """Sending a plain-text file as telemetry should return 400 or 500."""
    r = await async_client.post(
        "/analyze",
        files={
            "telemetry_file": ("bad.txt", b"not a real file", "text/plain"),
            "svm_file": ("car.svm", b"[GENERAL]\nFuelSetting=50\n", "text/plain"),
        },
    )
    assert r.status_code in (400, 500)
