"""Bidirectional Streamlit component for chunked file upload to the backend API.

The component renders a drag-and-drop file picker that splits the selected file
into fixed-size chunks (received from props) and uploads them one-by-one to::

    POST  <browser_api_base_url>/uploads/init
    PUT   <browser_api_base_url>/uploads/<id>/chunk?chunk_index=N
    POST  <browser_api_base_url>/uploads/<id>/complete

Each chunk is at most ``chunk_size`` bytes, so even very large files stay within
Cloudflare's 100 MB per-request limit.

When all chunks have been delivered the component returns a dict::

    {"filename": str, "upload_id": str, "bytes_received": int}

until the user selects a new file, after which a new upload cycle starts.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "chunked_uploader")
_component_func = components.declare_component("chunked_file_uploader", path=_COMPONENT_DIR)


def chunked_uploader(
    label: str,
    browser_api_base_url: str,
    client_session_id: str,
    chunk_size: int,
    file_types: Optional[List[str]] = None,
    height: int = 120,
    key: Optional[str] = None,
    help_text: Optional[str] = None,
) -> Optional[Dict]:
    """Render a chunked-upload file picker and return the upload result.

    Parameters
    ----------
    label:
        Text shown inside the drop zone (e.g. "Archivo de telemetría (.mat/.csv)").
    browser_api_base_url:
        Base URL for the backend API as seen by the *browser* (e.g. "/api" in
        production or "http://localhost:8000" locally).
    client_session_id:
        The current client session ID, forwarded as ``X-Client-Session-Id``.
    chunk_size:
        Maximum bytes per chunk.  Should match ``UPLOAD_CHUNK_SIZE`` in config.
    file_types:
        List of accepted extensions without the leading dot, e.g. ``["mat", "csv"]``.
    height:
        Height in pixels for the component iframe.
    key:
        Streamlit component key (keeps value stable across reruns).
    help_text:
        Small secondary text shown below the title inside the drop zone.

    Returns
    -------
    dict or None
        ``{"filename": str, "upload_id": str, "bytes_received": int}`` when an
        upload is complete, ``None`` when the picker is idle.
    """
    return _component_func(
        label=label,
        browser_api_base_url=browser_api_base_url,
        client_session_id=client_session_id,
        chunk_size=chunk_size,
        file_types=file_types or [],
        height=height,
        help_text=help_text,
        key=key,
        default=None,
    )
