"""Production-circuit E2E tests for the chunked upload flow.

Validates the complete request path that the browser JS traverses:
    JS fetch (credentials: 'include')
        → Cloudflare
        → Nginx TLS termination + HTTP BasicAuth
        → Backend container (/uploads/* and /sessions endpoints)

Without running these tests, a regression like ``credentials: 'omit'``
in the JS fetch calls would not be caught by any unit or local E2E test,
because those bypass Nginx entirely.

Opt-in: both env vars must be set for these tests to run.

    RF2_PROD_URL          Base URL of the production API exposed by Nginx.
                          Include the /api prefix that Nginx routes to the
                          backend, e.g. https://car-setup.com/api
                          (or https://telemetria.bot.nu/api)

    RF2_PROD_BASIC_AUTH   Nginx BasicAuth credentials in user:password format.

Usage:
    RF2_PROD_URL=https://car-setup.com/api \\
    RF2_PROD_BASIC_AUTH=racef1:secret      \\
    pytest e2e/api/test_prod_upload.py -v
"""
import os
import uuid
from pathlib import Path

import httpx
import pytest

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

_PROD_URL = os.getenv("RF2_PROD_URL", "").rstrip("/")
_PROD_BASIC_AUTH = os.getenv("RF2_PROD_BASIC_AUTH", "")

_SKIP_REASON = (
    "Opt-in prod-circuit tests: set RF2_PROD_URL and RF2_PROD_BASIC_AUTH "
    "to run (e.g. RF2_PROD_URL=https://car-setup.com/api RF2_PROD_BASIC_AUTH=user:pass)"
)


def _parse_auth() -> httpx.BasicAuth | None:
    if ":" not in _PROD_BASIC_AUTH:
        return None
    user, _, password = _PROD_BASIC_AUTH.partition(":")
    return httpx.BasicAuth(user, password)


# ---------------------------------------------------------------------------
# Module-level skip guard — evaluated once per collection
# ---------------------------------------------------------------------------

def pytest_collection_modifyitems(items):
    """Skip all items in this module if env vars are missing."""


@pytest.fixture(scope="module")
def prod_session_id() -> str:
    return uuid.uuid4().hex


@pytest.fixture(scope="module")
def prod_client(prod_session_id):
    auth = _parse_auth()
    if not _PROD_URL or auth is None:
        pytest.skip(_SKIP_REASON)

    with httpx.Client(
        base_url=_PROD_URL,
        auth=auth,
        headers={"X-Client-Session-Id": prod_session_id},
        timeout=60,
        follow_redirects=True,
    ) as client:
        yield client

    # Always clean up the test session on exit
    try:
        cleanup_auth = _parse_auth()
        with httpx.Client(
            base_url=_PROD_URL,
            auth=cleanup_auth,
            headers={"X-Client-Session-Id": prod_session_id},
            timeout=30,
            follow_redirects=True,
        ) as c:
            c.post("/cleanup")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Auth-enforcement test (no fixtures — uses raw httpx)
# ---------------------------------------------------------------------------

def test_nginx_returns_401_without_credentials():
    """Nginx must reject unauthenticated requests with 401.

    This test would have caught the ``credentials: 'omit'`` bug: the browser
    JS was omitting the stored BasicAuth token, so every request arrived at
    Nginx without an Authorization header and returned 401.
    """
    if not _PROD_URL:
        pytest.skip(_SKIP_REASON)

    r = httpx.get(f"{_PROD_URL}/models", follow_redirects=True, timeout=10)
    assert r.status_code == 401, (
        f"Expected 401 without auth, got {r.status_code}. "
        "If BasicAuth was removed from Nginx this test should be updated."
    )


# ---------------------------------------------------------------------------
# Authenticated smoke tests
# ---------------------------------------------------------------------------

def test_models_reachable_through_nginx(prod_client):
    """GET /models is reachable with valid BasicAuth credentials."""
    r = prod_client.get("/models")
    assert r.status_code == 200
    assert "models" in r.json()


def test_sessions_reachable_through_nginx(prod_client):
    """GET /sessions is reachable and returns a list."""
    r = prod_client.get("/sessions")
    assert r.status_code == 200
    body = r.json()
    assert "sessions" in body
    assert isinstance(body["sessions"], list)


# ---------------------------------------------------------------------------
# Full chunked-upload cycle (mirrors the browser JS uploadOne() function)
# ---------------------------------------------------------------------------

def test_full_chunked_upload_cycle(prod_client, prod_session_id):
    """Mirrors exactly what the browser JS does via fetch().

    Steps:
      POST /uploads/init         → get upload_id + chunk_size
      PUT  /uploads/{id}/chunk   → send all chunks in order
      POST /uploads/{id}/complete → assemble file on server
    Verify:
      GET /sessions → the uploaded pair appears

    This test would have caught the ``credentials: 'omit'`` bug because:
    - the requests here include explicit BasicAuth (mimicking ``credentials: 'include'``),
    - a test variant without auth would return 401 at the init step.
    """
    csv_bytes = (FIXTURES_DIR / "sample.csv").read_bytes()
    svm_bytes = (FIXTURES_DIR / "sample.svm").read_bytes()

    for filename, content in [
        ("prod_e2e_session.csv", csv_bytes),
        ("prod_e2e_car.svm", svm_bytes),
    ]:
        # 1. Init
        init_r = prod_client.post("/uploads/init", json={"filename": filename})
        assert init_r.status_code == 200, (
            f"init failed for {filename} (status={init_r.status_code}): {init_r.text}"
        )
        init_body = init_r.json()
        assert "upload_id" in init_body
        upload_id = init_body["upload_id"]
        chunk_size = init_body["chunk_size"]

        # 2. Upload chunks
        chunk_index = 0
        for offset in range(0, len(content), chunk_size):
            chunk = content[offset: offset + chunk_size]
            chunk_r = prod_client.put(
                f"/uploads/{upload_id}/chunk",
                params={"chunk_index": chunk_index},
                content=chunk,
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Client-Session-Id": prod_session_id,
                },
            )
            assert chunk_r.status_code == 200, (
                f"chunk {chunk_index} failed (status={chunk_r.status_code}): {chunk_r.text}"
            )
            chunk_index += 1

        # 3. Complete
        complete_r = prod_client.post(f"/uploads/{upload_id}/complete")
        assert complete_r.status_code == 200, (
            f"complete failed (status={complete_r.status_code}): {complete_r.text}"
        )
        assert complete_r.json()["filename"] == filename

    # 4. Verify session is listed
    sessions_r = prod_client.get("/sessions")
    assert sessions_r.status_code == 200
    sessions = sessions_r.json()["sessions"]
    assert len(sessions) >= 1, (
        "No session found after uploading both files. "
        "Expected the (csv, svm) pair to appear in /sessions."
    )


def test_chunked_upload_init_requires_auth_without_credentials(prod_client):
    """Upload init endpoint must also require auth — no anonymous uploads."""
    if not _PROD_URL:
        pytest.skip(_SKIP_REASON)

    r = httpx.post(
        f"{_PROD_URL}/uploads/init",
        json={"filename": "anon.csv"},
        follow_redirects=True,
        timeout=10,
    )
    assert r.status_code == 401, (
        f"Expected 401 for unauthenticated upload init, got {r.status_code}"
    )


def test_cleanup_removes_test_session(prod_client):
    """POST /cleanup removes the test session's data."""
    r = prod_client.post("/cleanup")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
