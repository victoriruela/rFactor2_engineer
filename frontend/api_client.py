"""Frontend HTTP client helpers for backend API calls."""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests


def headers_for_session(session_id: Optional[str]) -> Dict[str, str]:
    if isinstance(session_id, str) and session_id.strip():
        return {"X-Client-Session-Id": session_id.strip()}
    return {}


def post_cleanup(api_base_url: str, session_id: Optional[str], timeout: int = 10) -> None:
    requests.post(f"{api_base_url}/cleanup", headers=headers_for_session(session_id), timeout=timeout)


def post_cleanup_all(api_base_url: str, timeout: int = 15) -> None:
    requests.post(f"{api_base_url}/cleanup_all", timeout=timeout)


def get_sessions(api_base_url: str, session_id: Optional[str], timeout: int = 20) -> Dict[str, Any]:
    return requests.get(f"{api_base_url}/sessions", headers=headers_for_session(session_id), timeout=timeout).json()


def get_models(
    api_base_url: str,
    session_id: Optional[str],
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 5,
):
    return requests.get(
        f"{api_base_url}/models",
        headers=headers_for_session(session_id),
        params=params or {},
        timeout=timeout,
    )


def post_analyze_with_files(
    api_base_url: str,
    session_id: Optional[str],
    data_form: Dict[str, Any],
    files: Dict[str, Any],
    timeout,
):
    return requests.post(
        f"{api_base_url}/analyze",
        data=data_form,
        files=files,
        headers=headers_for_session(session_id),
        timeout=timeout,
    )


def download_session_file(
    api_base_url: str,
    session_id: str,
    filename: str,
    target_path: str,
    chunk_bytes: int = 4 * 1024 * 1024,
    timeout: int = 300,
) -> None:
    """Download a stored session file from the backend and save it locally.

    Uses streaming to avoid loading the full file into memory at once.
    The file is downloaded from ``GET /sessions/{session_id}/file/{filename}``.
    """
    url = f"{api_base_url}/sessions/{session_id}/file/{filename}"
    with requests.get(url, headers=headers_for_session(session_id), stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with open(target_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_bytes):
                if chunk:
                    f.write(chunk)
