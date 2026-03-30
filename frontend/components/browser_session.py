"""Tiny Streamlit component used to persist a client session ID in browser sessionStorage."""

from __future__ import annotations

import os
from typing import Optional

import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "browser_session")
_component_func = components.declare_component("browser_session_bridge", path=_COMPONENT_DIR)


def sync_browser_session_id(
    storage_key: str,
    candidate_session_id: Optional[str],
    reset_counter: int = 0,
    key: Optional[str] = None,
) -> Optional[str]:
    """Return the session id persisted in browser sessionStorage for this tab.

    When no value exists yet, the component stores ``candidate_session_id``.
    ``reset_counter`` forces the browser-side value to be cleared and recreated.
    """
    return _component_func(
        storage_key=storage_key,
        candidate_session_id=candidate_session_id or "",
        reset_counter=int(reset_counter),
        key=key,
        default=None,
    )
