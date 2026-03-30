"""Browser hooks injected via Streamlit components for ephemeral session behavior."""

from __future__ import annotations

import json

import streamlit.components.v1 as components


def inject_cleanup_on_unload(session_id: str, browser_api_base_url: str) -> None:
    components.html(
        f"""
        <script>
            const apiBase = {json.dumps(browser_api_base_url)};
            const sid = {json.dumps(session_id)};
            const onceKey = '__rf2_unload_cleanup_registered';
            if (!window[onceKey]) {{
                window[onceKey] = true;
                window.addEventListener('beforeunload', function () {{
                    fetch(`${{apiBase}}/cleanup`, {{
                        method: 'POST',
                        headers: {{ 'X-Client-Session-Id': sid }},
                        credentials: 'include',
                        keepalive: true,
                    }}).catch(() => {{}});
                }});
            }}
        </script>
        """,
        height=0,
    )
