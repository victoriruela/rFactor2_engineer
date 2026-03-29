"""E2E tests for the FastAPI backend. Requires a running server (see conftest.py)."""
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


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


@pytest.mark.asyncio
async def test_analyze_happy_path_returns_structured_payload(async_client):
    """Valid fixture files should return a complete analysis payload."""
    telemetry_bytes = (FIXTURES_DIR / "sample.csv").read_bytes()
    svm_bytes = (FIXTURES_DIR / "sample.svm").read_bytes()

    r = await async_client.post(
        "/analyze",
        files={
            "telemetry_file": ("session.csv", telemetry_bytes, "text/csv"),
            "svm_file": ("car.svm", svm_bytes, "text/plain"),
        },
    )

    assert r.status_code == 200
    body = r.json()
    for key in (
        "circuit_data",
        "issues_on_map",
        "driving_analysis",
        "setup_analysis",
        "full_setup",
        "session_stats",
        "laps_data",
        "llm_provider",
        "llm_model",
    ):
        assert key in body

    assert isinstance(body["circuit_data"].get("x"), list)
    assert isinstance(body["circuit_data"].get("y"), list)
    assert len(body["circuit_data"]["x"]) > 0
    assert len(body["laps_data"]) >= 1
    assert body["llm_provider"] in ("ollama", "jimmy")
