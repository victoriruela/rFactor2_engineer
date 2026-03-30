import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import numpy as np
import scipy.io
import os
import json as _json
import shutil
import tempfile
import time
import uuid
import re

import hashlib
import math
import plotly.graph_objects as go

FIXED_PARAMS_FILE = "app/core/fixed_params.json"

# ─────────────────────────────────────────────────────────────────────────────
# PIP (Picture-in-Picture) State Management for 3D Cockpit Replay
# ─────────────────────────────────────────────────────────────────────────────
PIP_STATE_MINI = "mini"
PIP_STATE_HIDDEN = "hidden"
PIP_STATE_MAP_REPLACE = "map_replace"
PIP_STATE_FULLSCREEN = "fullscreen"
PIP_VALID_STATES = {PIP_STATE_MINI, PIP_STATE_HIDDEN, PIP_STATE_MAP_REPLACE, PIP_STATE_FULLSCREEN}
PIP_DEFAULT_STATE = PIP_STATE_MINI


def pip_get_state(session_state):
    """Return the current PIP state from session_state, defaulting to mini."""
    state = session_state.get("pip_state", PIP_DEFAULT_STATE)
    if state not in PIP_VALID_STATES:
        return PIP_DEFAULT_STATE
    return state


def pip_get_previous_state(session_state):
    """Return the previous visible PIP state (used when exiting fullscreen)."""
    prev = session_state.get("pip_previous_state", PIP_STATE_MINI)
    if prev not in PIP_VALID_STATES or prev == PIP_STATE_HIDDEN:
        return PIP_STATE_MINI
    return prev


def pip_transition(session_state, target_state):
    """Transition to a new PIP state, tracking the previous visible state.

    Returns the new current state.
    """
    if target_state not in PIP_VALID_STATES:
        return pip_get_state(session_state)

    current = pip_get_state(session_state)

    # Track previous visible state for restoring from hidden/fullscreen
    if current not in (PIP_STATE_HIDDEN, PIP_STATE_FULLSCREEN):
        session_state["pip_previous_state"] = current

    session_state["pip_state"] = target_state
    return target_state


def pip_restore_from_hidden(session_state):
    """Restore from hidden to the previous visible state."""
    prev = pip_get_previous_state(session_state)
    session_state["pip_state"] = prev
    return prev


def pip_restore_from_fullscreen(session_state):
    """Restore from fullscreen to the previous visible state."""
    prev = pip_get_previous_state(session_state)
    session_state["pip_state"] = prev
    return prev


def pip_css():
    """Return CSS for all PIP states, injected via st.markdown(unsafe_allow_html=True)."""
    return """
<style>
/* ── PIP Container Base ─────────────────────────────────────────────── */
.pip-container {
    transition: all 0.3s ease-in-out;
    z-index: 1000;
    background: #111;
    border-radius: 6px;
    overflow: hidden;
}
.pip-container iframe {
    width: 100% !important;
    height: 100% !important;
    border: none;
}

/* ── Mini PIP (default): floating bottom-right of telemetry area ──── */
.pip-mini {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 320px;
    height: 200px;
    border: 1px solid #444;
    box-shadow: 0 4px 20px rgba(0,0,0,0.6);
}

/* ── Hidden: collapsed to a small restore button ──────────────────── */
.pip-hidden {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 44px;
    height: 44px;
    border: 1px solid #444;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
}
.pip-hidden iframe {
    display: none;
}

/* ── Replace Map: takes over the map container area ───────────────── */
.pip-map-replace {
    position: relative;
    width: 100%;
    height: 300px;
    border: 1px solid #333;
}

/* Hide the 2D map when cockpit replaces it */
.pip-map-replace-active #map-container {
    display: none !important;
}

/* ── Fullscreen: modal overlay ────────────────────────────────────── */
.pip-fullscreen-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0,0,0,0.85);
    z-index: 9998;
    display: flex;
    align-items: center;
    justify-content: center;
}
.pip-fullscreen {
    position: relative;
    width: 95vw;
    height: 90vh;
    border: 1px solid #555;
    border-radius: 8px;
    z-index: 9999;
}

/* ── PIP Control Buttons ──────────────────────────────────────────── */
.pip-controls {
    position: absolute;
    top: 4px;
    right: 4px;
    display: flex;
    gap: 4px;
    z-index: 10001;
}
.pip-btn {
    background: rgba(0,0,0,0.7);
    color: #ccc;
    border: 1px solid #555;
    border-radius: 4px;
    width: 28px;
    height: 28px;
    font-size: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s;
}
.pip-btn:hover {
    background: rgba(60,60,60,0.9);
    color: #fff;
}

/* ── Restore button (shown in hidden state) ───────────────────────── */
.pip-restore-btn {
    background: rgba(30,30,30,0.9);
    color: #ccc;
    border: 1px solid #555;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    font-size: 20px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    position: fixed;
    bottom: 22px;
    right: 22px;
    z-index: 1001;
    transition: background 0.2s;
}
.pip-restore-btn:hover {
    background: rgba(60,60,60,0.9);
    color: #fff;
}
</style>
"""


def pip_render_cockpit_container(state, cockpit_html_func=None):
    """Render the PIP container with appropriate CSS class and control buttons.

    Args:
        state: One of the PIP_STATE_* constants.
        cockpit_html_func: Optional callable that returns the cockpit HTML string.
            If None, a placeholder is rendered.

    Returns:
        The full HTML string for the PIP container.
    """
    cockpit_content = ""
    if cockpit_html_func is not None:
        cockpit_content = cockpit_html_func()
    else:
        cockpit_content = (
            '<div style="width:100%;height:100%;display:flex;'
            'align-items:center;justify-content:center;color:#666;'
            'font-family:sans-serif;font-size:14px;">'
            '3D Cockpit (loading...)</div>'
        )

    if state == PIP_STATE_HIDDEN:
        # Only show restore button, cockpit iframe is paused but not destroyed
        return (
            '<button class="pip-restore-btn" '
            'onclick="window.parent.postMessage({type:\'pip_transition\','
            'state:\'restore_hidden\'},\'*\')" '
            'title="Restore cockpit">&#x1F3A5;</button>'
            f'<div style="display:none;">{cockpit_content}</div>'
        )

    if state == PIP_STATE_FULLSCREEN:
        return (
            '<div class="pip-fullscreen-backdrop">'
            '<div class="pip-container pip-fullscreen">'
            '<div class="pip-controls">'
            '<button class="pip-btn" '
            'onclick="window.parent.postMessage({type:\'pip_transition\','
            'state:\'restore_fullscreen\'},\'*\')" '
            'title="Exit fullscreen">&#x2715;</button>'
            '</div>'
            f'{cockpit_content}'
            '</div></div>'
        )

    if state == PIP_STATE_MAP_REPLACE:
        return (
            '<div class="pip-container pip-map-replace">'
            '<div class="pip-controls">'
            '<button class="pip-btn" '
            'onclick="window.parent.postMessage({type:\'pip_transition\','
            'state:\'mini\'},\'*\')" '
            'title="Shrink to mini">&darr;</button>'
            '<button class="pip-btn" '
            'onclick="window.parent.postMessage({type:\'pip_transition\','
            'state:\'fullscreen\'},\'*\')" '
            'title="Fullscreen">&#x26F6;</button>'
            '<button class="pip-btn" '
            'onclick="window.parent.postMessage({type:\'pip_transition\','
            'state:\'hidden\'},\'*\')" '
            'title="Hide">&minus;</button>'
            '</div>'
            f'{cockpit_content}'
            '</div>'
        )

    # Default: PIP_STATE_MINI
    return (
        '<div class="pip-container pip-mini">'
        '<div class="pip-controls">'
        '<button class="pip-btn" '
        'onclick="window.parent.postMessage({type:\'pip_transition\','
        'state:\'map_replace\'},\'*\')" '
        'title="Replace map">&uarr;</button>'
        '<button class="pip-btn" '
        'onclick="window.parent.postMessage({type:\'pip_transition\','
        'state:\'fullscreen\'},\'*\')" '
        'title="Fullscreen">&#x26F6;</button>'
        '<button class="pip-btn" '
        'onclick="window.parent.postMessage({type:\'pip_transition\','
        'state:\'hidden\'},\'*\')" '
        'title="Hide">&minus;</button>'
        '</div>'
        f'{cockpit_content}'
        '</div>'
    )


def pip_js_listener():
    """Return JS snippet that listens for pip_transition postMessages
    and triggers Streamlit reruns with the new state.

    This must be injected into the parent page (via st.components.html).
    """
    return """
<script>
window.addEventListener('message', function(event) {
    if (event.data && event.data.type === 'pip_transition') {
        var state = event.data.state;
        // Use Streamlit's setComponentValue or URL hack to trigger rerun
        var url = new URL(window.location);
        url.searchParams.set('pip_action', state);
        window.location.replace(url.toString());
    }
});
</script>
"""
API_BASE_URL = os.environ.get("RF2_API_URL", "http://localhost:8000")
BROWSER_API_BASE_URL = os.environ.get("RF2_BROWSER_API_BASE_URL", "/api")
UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024
ANALYSIS_REQUEST_TIMEOUT = (10, 1800)
TEMP_UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "rfactor2_engineer_uploads")
CLIENT_SESSION_COOKIE = "rf2_session_id"
CLIENT_SESSION_QUERY_PARAM = "rf2sid"
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
MAT_PREVIEW_MAX_MB = int(os.environ.get("RF2_FRONTEND_MAX_PREVIEW_MAT_MB", "800"))


def _ensure_temp_upload_root():
    os.makedirs(TEMP_UPLOAD_ROOT, exist_ok=True)
    return TEMP_UPLOAD_ROOT


def _cleanup_temp_session_files():
    temp_dir = st.session_state.pop('temp_upload_dir', None)
    for key in ('telemetry_temp_path', 'svm_temp_path', 'tele_name', 'svm_name', 'selected_session_id'):
        st.session_state.pop(key, None)

    if temp_dir and os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


def _cleanup_orphaned_temp_dirs(max_age_hours=24):
    """Remove temp session directories older than max_age_hours.
    Called once on app startup to prevent disk space buildup.
    """
    if not os.path.isdir(TEMP_UPLOAD_ROOT):
        return
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    for entry in os.listdir(TEMP_UPLOAD_ROOT):
        entry_path = os.path.join(TEMP_UPLOAD_ROOT, entry)
        if os.path.isdir(entry_path):
            try:
                mtime = os.path.getmtime(entry_path)
                if mtime < cutoff:
                    shutil.rmtree(entry_path, ignore_errors=True)
            except OSError:
                pass


def _write_uploaded_file_in_chunks(uploaded_file, target_path, chunk_size=UPLOAD_CHUNK_SIZE):
    uploaded_file.seek(0)
    with open(target_path, 'wb') as temp_file:
        while True:
            chunk = uploaded_file.read(chunk_size)
            if not chunk:
                break
            temp_file.write(chunk)
    uploaded_file.seek(0)


def _persist_uploaded_session(telemetry_file, svm_file):
    temp_root = _ensure_temp_upload_root()
    session_dir = tempfile.mkdtemp(prefix=f"rf2-session-{uuid.uuid4()}-", dir=temp_root)

    tele_name = os.path.basename(telemetry_file.name)
    svm_name = os.path.basename(svm_file.name)
    tele_path = os.path.join(session_dir, tele_name)
    svm_path = os.path.join(session_dir, svm_name)

    _write_uploaded_file_in_chunks(telemetry_file, tele_path)
    _write_uploaded_file_in_chunks(svm_file, svm_path)

    return {
        "temp_upload_dir": session_dir,
        "telemetry_temp_path": tele_path,
        "svm_temp_path": svm_path,
        "tele_name": tele_name,
        "svm_name": svm_name,
    }


def _is_streamlit_mocked() -> bool:
        return st.__class__.__module__.startswith("unittest.mock")


# ─────────────────────────────────────────────────────────────────────────────
# Track selection helpers (pure functions — no Streamlit dependency)
# ─────────────────────────────────────────────────────────────────────────────


def compute_track_centroid(track_json):
    """Return (mean_lat, mean_lon) from a track JSON, or None if empty."""
    waypoints = track_json.get("points", track_json.get("waypoints", []))
    if not waypoints:
        return None
    lats = [w["lat"] for w in waypoints if "lat" in w]
    lons = [w["lon"] for w in waypoints if "lon" in w]
    if not lats or not lons:
        return None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def find_best_track_match(telemetry_lat, telemetry_lon, known_tracks, threshold=0.01):
    """Find the closest known track to a GPS centroid (within *threshold* degrees).

    *known_tracks* is a list of dicts with at least ``centroid_lat`` and ``centroid_lon``.
    Returns the best match dict, or ``None`` if nothing is close enough.
    """
    if not known_tracks:
        return None
    best = None
    best_dist = float("inf")
    for track in known_tracks:
        dlat = track["centroid_lat"] - telemetry_lat
        dlon = track["centroid_lon"] - telemetry_lon
        dist = math.sqrt(dlat ** 2 + dlon ** 2)
        if dist < best_dist:
            best_dist = dist
            best = track
    if best_dist <= threshold:
        return best
    return None


def build_track_preview_data(track_json):
    """Return (xs, ys) lists for a 2D top-down preview of the track.

    Prefers ``x``/``y`` fields; falls back to ``lon``/``lat`` if absent.
    """
    waypoints = track_json.get("points", track_json.get("waypoints", []))
    if not waypoints:
        return [], []
    if "x" in waypoints[0]:
        xs = [w["x"] for w in waypoints]
        ys = [w["y"] for w in waypoints]
    elif "lon" in waypoints[0]:
        xs = [w["lon"] for w in waypoints]
        ys = [w["lat"] for w in waypoints]
    else:
        return [], []
    return xs, ys


def compute_file_sha256(data: bytes) -> str:
    """Return the hex SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def _safe_cookie_value(cookie_name):
        try:
                ctx = getattr(st, "context", None)
                cookies = getattr(ctx, "cookies", None) if ctx is not None else None
                if cookies is None:
                        return None
                value = cookies.get(cookie_name)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                return None
        except Exception:
                return None


def _is_valid_session_id(value):
    return isinstance(value, str) and bool(SESSION_ID_PATTERN.fullmatch(value.strip()))


def _ensure_client_session_id():
    existing = st.session_state.get("client_session_id")
    if _is_valid_session_id(existing):
        return existing

    try:
        qp_value = st.query_params.get(CLIENT_SESSION_QUERY_PARAM)
        if isinstance(qp_value, list):
            qp_value = qp_value[0] if qp_value else None
    except Exception:
        qp_value = None
    if _is_valid_session_id(qp_value):
        st.session_state["client_session_id"] = qp_value.strip()
        return qp_value.strip()

    cookie_value = _safe_cookie_value(CLIENT_SESSION_COOKIE)
    if _is_valid_session_id(cookie_value):
        st.session_state["client_session_id"] = cookie_value
        try:
            st.query_params[CLIENT_SESSION_QUERY_PARAM] = cookie_value
        except Exception:
            pass
        return cookie_value

    generated = uuid.uuid4().hex
    st.session_state["client_session_id"] = generated
    try:
        st.query_params[CLIENT_SESSION_QUERY_PARAM] = generated
    except Exception:
        pass

    if _is_streamlit_mocked():
        return generated

    # Best effort: persist in cookie without forcing a full-page reload.
    components.html(
            f"""
            <script>
                document.cookie = "{CLIENT_SESSION_COOKIE}={generated}; path=/; max-age=31536000; SameSite=Lax";
            </script>
            """,
            height=0,
    )
    return generated


def _api_headers():
    session_id = st.session_state.get("client_session_id")
    return {"X-Client-Session-Id": session_id} if _is_valid_session_id(session_id) else {}


def _render_chunked_uploader():
    raw_session_id = st.session_state.get("client_session_id", "")
    session_id = raw_session_id.strip() if isinstance(raw_session_id, str) else ""
    html = f"""
        <div style='font-family:sans-serif;'>
            <input id='rf2_files' type='file' multiple accept='.mat,.csv,.svm' />
            <button id='rf2_upload_btn' style='margin-top:6px;'>Subir en chunks (16 MB)</button>
            <pre id='rf2_upload_status' style='white-space:pre-wrap;font-size:12px;max-height:120px;overflow:auto;'></pre>
        </div>
        <script>
            const apiBase = { _json.dumps(BROWSER_API_BASE_URL) };
            const sessionId = { _json.dumps(session_id) };
            const sessionIdPattern = /^[A-Za-z0-9_-]{{8,128}}$/;
            const chunkSize = {UPLOAD_CHUNK_SIZE};
            const statusEl = document.getElementById('rf2_upload_status');

            function log(msg) {{
                statusEl.textContent += msg + "\\n";
                statusEl.scrollTop = statusEl.scrollHeight;
            }}

            async function uploadChunkWithRetry(url, options, maxRetries = 3) {{
                let lastError = null;
                for (let attempt = 1; attempt <= maxRetries; attempt += 1) {{
                    try {{
                        const response = await fetch(url, options);
                        if (response.ok) {{
                            return response;
                        }}
                        throw new Error(`status ${{response.status}}`);
                    }} catch (err) {{
                        lastError = err;
                        if (attempt < maxRetries) {{
                            await new Promise((resolve) => setTimeout(resolve, 500 * attempt));
                        }}
                    }}
                }}
                throw new Error(`chunk failed after retries: ${{lastError?.message || 'unknown error'}}`);
            }}

            async function uploadOne(file) {{
                if (!sessionIdPattern.test(sessionId)) {{
                    throw new Error('session id invalido o ausente; recarga la pagina');
                }}
                log(`Inicializando ${{file.name}}...`);
                const initResp = await fetch(`${{apiBase}}/uploads/init`, {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'X-Client-Session-Id': sessionId,
                    }},
                    body: JSON.stringify({{ filename: file.name }}),
                    credentials: 'include',
                }});
                if (!initResp.ok) throw new Error(`init failed (${{initResp.status}})`);
                const initData = await initResp.json();

                let chunkIndex = 0;
                for (let offset = 0; offset < file.size; offset += chunkSize) {{
                    const chunk = file.slice(offset, Math.min(offset + chunkSize, file.size));
                    const chunkResp = await uploadChunkWithRetry(`${{apiBase}}/uploads/${{initData.upload_id}}/chunk?chunk_index=${{chunkIndex}}`, {{
                        method: 'PUT',
                        headers: {{
                            'Content-Type': 'application/octet-stream',
                            'X-Client-Session-Id': sessionId,
                        }},
                        body: chunk,
                        credentials: 'include',
                    }});
                    chunkIndex += 1;
                      log(`${{file.name}}: chunk ${{chunkIndex}} enviado`);
                }}

                const completeResp = await fetch(`${{apiBase}}/uploads/${{initData.upload_id}}/complete`, {{
                    method: 'POST',
                    headers: {{ 'X-Client-Session-Id': sessionId }},
                    credentials: 'include',
                }});
                if (!completeResp.ok) throw new Error(`complete failed (${{completeResp.status}})`);
                log(`${{file.name}}: completado`);
            }}

            document.getElementById('rf2_upload_btn').addEventListener('click', async () => {{
                statusEl.textContent = '';
                const files = Array.from(document.getElementById('rf2_files').files || []);
                if (!files.length) {{
                    log('Selecciona archivos primero.');
                    return;
                }}
                try {{
                    for (const file of files) {{
                        await uploadOne(file);
                    }}
                    log('Subida completada. Recargando para listar sesiones...');
                    // Persist session ID in a cookie so it survives the full page reload.
                    // The iframe cannot navigate window.parent (cross-origin security),
                    // but it CAN set cookies on the same domain.
                    document.cookie = "{CLIENT_SESSION_COOKIE}=" + sessionId + "; path=/; max-age=31536000; SameSite=Lax";
                    window.parent.location.reload();
                }} catch (err) {{
                    log(`Error: ${{err.message}}`);
                }}
            }});
        </script>
        """
    components.html(html, height=190, scrolling=False)


def _render_track_upload_dropzone():
        """Render the AIW/MAS drop zone for the Pista 3D tab."""
        api_base = _json.dumps(BROWSER_API_BASE_URL)
        html = f"""
        <style>
            #track-drop-zone {{
                border: 2px dashed #555;
                border-radius: 10px;
                padding: 40px 20px;
                text-align: center;
                color: #aaa;
                font-family: sans-serif;
                font-size: 15px;
                transition: border-color 0.2s, background 0.2s;
                cursor: pointer;
                position: relative;
            }}
            #track-drop-zone.dragover {{
                border-color: #4CAF50;
                background: rgba(76, 175, 80, 0.08);
                color: #4CAF50;
            }}
            #track-drop-zone.processing {{
                border-color: #FF9800;
                color: #FF9800;
            }}
            #track-drop-zone.success {{
                border-color: #4CAF50;
                background: rgba(76, 175, 80, 0.05);
                color: #4CAF50;
            }}
            #track-drop-zone.error {{
                border-color: #f44336;
                color: #f44336;
            }}
            #track-file-input {{
                display: none;
            }}
            #track-result {{
                margin-top: 12px;
                font-family: sans-serif;
                font-size: 13px;
                color: #ccc;
                min-height: 20px;
            }}
            #track-result .track-name {{
                font-weight: bold;
                font-size: 16px;
                color: #4CAF50;
            }}
            #track-result .track-points {{
                color: #aaa;
                margin-top: 4px;
            }}
        </style>

        <div id="track-drop-zone" onclick="document.getElementById('track-file-input').click()">
            Arrastra un archivo .aiw o .mas aqui, o haz clic para seleccionar
            <br><small style="color:#666">Drop .aiw or .mas file here</small>
        </div>
        <input id="track-file-input" type="file" accept=".aiw,.mas" />
        <div id="track-result"></div>

        <script>
        (function() {{
            // ── Inlined AIW Parser ──
            function parseAIW(aiwText) {{
                const waypointRe = /pos\\s*=\\s*\\(\\s*(-?[\\d.]+)\\s*,\\s*(-?[\\d.]+)\\s*,\\s*(-?[\\d.]+)\\s*\\)/gi;
                const trackNameRe = /^\\s*trackName\\s*=\\s*(.+)/im;
                const nameMatch = trackNameRe.exec(aiwText);
                const trackName = nameMatch ? nameMatch[1].trim() : "Unknown";
                const points = [];
                let m;
                while ((m = waypointRe.exec(aiwText)) !== null) {{
                    points.push({{
                        x: parseFloat(m[1]),
                        y: parseFloat(m[2]),
                        z: parseFloat(m[3]),
                    }});
                }}
                return {{
                    track_name: trackName,
                    points: points,
                    point_count: points.length,
                }};
            }}

            // ── Inlined MAS Extractor ──
            function extractAIWFromMAS(arrayBuffer) {{
                const bytes = new Uint8Array(arrayBuffer);
                const textDecoder = new TextDecoder("utf-8", {{ fatal: false }});
                const fullText = textDecoder.decode(bytes);
                const aiwMarkers = ["[Waypoint]", "pos=(", "trackName="];
                let aiwStart = -1;
                for (const marker of aiwMarkers) {{
                    const idx = fullText.indexOf(marker);
                    if (idx !== -1 && (aiwStart === -1 || idx < aiwStart)) {{
                        aiwStart = idx;
                    }}
                }}
                if (aiwStart === -1) {{
                    throw new Error("No se encontraron datos AIW dentro del archivo MAS");
                }}
                let searchStart = Math.max(0, aiwStart - 512);
                const headerPatterns = ["[Header]", "[Main]", "trackName"];
                for (const hp of headerPatterns) {{
                    const idx = fullText.indexOf(hp, searchStart);
                    if (idx !== -1 && idx < aiwStart) {{
                        aiwStart = idx;
                        break;
                    }}
                }}
                let aiwEnd = fullText.length;
                for (let i = aiwStart + 100; i < fullText.length - 4; i++) {{
                    const ch = fullText.charCodeAt(i);
                    if (ch === 0 && fullText.charCodeAt(i + 1) === 0 &&
                        fullText.charCodeAt(i + 2) === 0 && fullText.charCodeAt(i + 3) === 0) {{
                        aiwEnd = i;
                        break;
                    }}
                }}
                const aiwText = fullText.substring(aiwStart, aiwEnd);
                if (!aiwText.includes("pos=") && !aiwText.includes("pos =")) {{
                    throw new Error("Los datos extraidos no contienen waypoints AIW validos");
                }}
                return aiwText;
            }}

            // ── Drop Zone Logic ──
            const dropZone = document.getElementById('track-drop-zone');
            const fileInput = document.getElementById('track-file-input');
            const resultDiv = document.getElementById('track-result');
            const apiBase = {api_base};

            function setStatus(cls, msg) {{
                dropZone.className = cls ? cls : '';
                if (msg) dropZone.innerHTML = msg;
            }}

            function showResult(trackData) {{
                resultDiv.innerHTML =
                    '<div class="track-name">' + trackData.track_name + '</div>' +
                    '<div class="track-points">' + trackData.point_count + ' waypoints cargados</div>';
            }}

            function showError(msg) {{
                resultDiv.innerHTML = '<span style="color:#f44336">' + msg + '</span>';
            }}

            async function processFile(file) {{
                setStatus('processing',
                    'Procesando ' + file.name + '...<br><small>Processing...</small>');
                resultDiv.innerHTML = '';

                try {{
                    let aiwText;
                    const ext = file.name.split('.').pop().toLowerCase();

                    if (ext === 'aiw') {{
                        aiwText = await file.text();
                    }} else if (ext === 'mas') {{
                        const buf = await file.arrayBuffer();
                        aiwText = extractAIWFromMAS(buf);
                    }} else {{
                        throw new Error('Formato no soportado: .' + ext);
                    }}

                    // Parse client-side
                    const trackData = parseAIW(aiwText);

                    if (trackData.point_count === 0) {{
                        throw new Error('No se encontraron waypoints en el archivo');
                    }}

                    // Post to backend for server-side validation
                    try {{
                        const resp = await fetch(apiBase + '/tracks/parse-aiw-text', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ aiw_text: aiwText }}),
                            credentials: 'include',
                        }});
                        if (resp.ok) {{
                            const serverData = await resp.json();
                            trackData.track_name = serverData.track_name;
                            trackData.point_count = serverData.point_count;
                            trackData.points = serverData.points;
                        }}
                    }} catch (e) {{
                        // Server unavailable; use client-side result
                    }}

                    // Send to Streamlit parent
                    window.parent.postMessage({{
                        type: 'track_data',
                        track_name: trackData.track_name,
                        point_count: trackData.point_count,
                        points: trackData.points,
                    }}, '*');

                    setStatus('success',
                        'Arrastra un archivo .aiw o .mas aqui, o haz clic para seleccionar' +
                        '<br><small>Drop .aiw or .mas file here</small>');
                    showResult(trackData);

                }} catch (err) {{
                    setStatus('error',
                        'Arrastra un archivo .aiw o .mas aqui, o haz clic para seleccionar' +
                        '<br><small>Drop .aiw or .mas file here</small>');
                    showError('Error: ' + err.message);
                }}
            }}

            // Drag events
            dropZone.addEventListener('dragover', function(e) {{
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('dragover');
            }});
            dropZone.addEventListener('dragleave', function(e) {{
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('dragover');
            }});
            dropZone.addEventListener('drop', function(e) {{
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) processFile(files[0]);
            }});

            // File input change
            fileInput.addEventListener('change', function() {{
                if (fileInput.files.length > 0) {{
                    processFile(fileInput.files[0]);
                }}
            }});
        }})();
        </script>
        """
        components.html(html, height=250, scrolling=False)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_backend_sessions():
        try:
                response = requests.get(f"{API_BASE_URL}/sessions", headers=_api_headers(), timeout=20)
                if response.status_code == 200:
                        return response.json().get("sessions", [])
        except Exception:
                pass
        return []


def _download_session_file(url, target_path):
        with requests.get(url, headers=_api_headers(), stream=True, timeout=120) as response:
                if response.status_code != 200:
                        raise RuntimeError(f"Download failed ({response.status_code})")
                with open(target_path, "wb") as output:
                        for chunk in response.iter_content(chunk_size=UPLOAD_CHUNK_SIZE):
                                if chunk:
                                        output.write(chunk)


def _load_session_locally(session_entry):
        temp_root = _ensure_temp_upload_root()
        # Use deterministic path based on session_id so we can reuse cached files
        session_id = session_entry["id"]
        session_dir = os.path.join(temp_root, f"rf2-session-{session_id}")
        os.makedirs(session_dir, exist_ok=True)

        tele_name = session_entry["telemetry"]
        svm_name = session_entry["svm"]
        tele_path = os.path.join(session_dir, tele_name)
        svm_path = os.path.join(session_dir, svm_name)

        # Only download if files don't already exist (reuse cache across restarts)
        if not os.path.exists(tele_path) or os.path.getsize(tele_path) == 0:
            _download_session_file(f"{API_BASE_URL}/sessions/{session_id}/file/{tele_name}", tele_path)
        if not os.path.exists(svm_path) or os.path.getsize(svm_path) == 0:
            _download_session_file(f"{API_BASE_URL}/sessions/{session_id}/file/{svm_name}", svm_path)

        return {
                "temp_upload_dir": session_dir,
                "telemetry_temp_path": tele_path,
                "svm_temp_path": svm_path,
                "tele_name": tele_name,
                "svm_name": svm_name,
                "selected_session_id": session_id,
                "selected_session_name": session_entry.get("display_name", session_id),
        }


def _post_analysis_for_session(session_id, data_form):
        return requests.post(
                f"{API_BASE_URL}/analyze_session",
                data={"session_id": session_id, **data_form},
                headers=_api_headers(),
        timeout=ANALYSIS_REQUEST_TIMEOUT,
        )


def _post_analysis_with_local_files(data_form):
    tele_path = st.session_state.get("telemetry_temp_path")
    svm_path = st.session_state.get("svm_temp_path")
    tele_name = st.session_state.get("tele_name") or os.path.basename(tele_path or "telemetry")
    svm_name = st.session_state.get("svm_name") or os.path.basename(svm_path or "setup.svm")

    if not tele_path or not svm_path or not os.path.exists(tele_path) or not os.path.exists(svm_path):
        raise FileNotFoundError("Local temporary upload files are missing")

    with open(tele_path, "rb") as telemetry_file, open(svm_path, "rb") as svm_file:
        files = {
            "telemetry_file": (tele_name, telemetry_file),
            "svm_file": (svm_name, svm_file),
        }
        return requests.post(
            f"{API_BASE_URL}/analyze",
            data=data_form,
            files=files,
            headers=_api_headers(),
            timeout=ANALYSIS_REQUEST_TIMEOUT,
        )

def load_fixed_params():
    """Carga los parámetros fijados desde el archivo JSON."""
    if os.path.exists(FIXED_PARAMS_FILE):
        try:
            with open(FIXED_PARAMS_FILE, 'r', encoding='utf-8') as f:
                return set(_json.load(f))
        except Exception:
            pass
    return set()

def save_fixed_params(params_set):
    """Guarda los parámetros fijados en el archivo JSON."""
    try:
        os.makedirs(os.path.dirname(FIXED_PARAMS_FILE), exist_ok=True)
        with open(FIXED_PARAMS_FILE, 'w', encoding='utf-8') as f:
            _json.dump(list(params_set), f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f"Error al guardar parámetros: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# Track selection UI
# ─────────────────────────────────────────────────────────────────────────────

TRACKS_DIR = os.path.join(os.path.dirname(__file__), "..", "tracks")


@st.cache_resource(show_spinner=False)
def _fetch_track_list():
    """Fetch available tracks from the backend ``GET /tracks/list`` endpoint.

    Each entry has at least ``name`` and ``content_sha256``.
    Also scans the local ``tracks/`` directory for pre-hosted JSON files.
    """
    remote_tracks = []
    try:
        resp = requests.get(
            f"{API_BASE_URL}/tracks/list", headers=_api_headers(), timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            remote_tracks = data if isinstance(data, list) else data.get("tracks", [])
    except Exception:
        pass

    # Scan local tracks/ directory
    local_tracks = []
    if os.path.isdir(TRACKS_DIR):
        for fname in sorted(os.listdir(TRACKS_DIR)):
            if fname.endswith(".json"):
                fpath = os.path.join(TRACKS_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        track_data = _json.load(f)
                    local_tracks.append({
                        "name": track_data.get("name", fname.replace(".json", "")),
                        "content_sha256": compute_file_sha256(
                            open(fpath, "rb").read()
                        ),
                        "_local_path": fpath,
                        "_track_json": track_data,
                    })
                except Exception:
                    pass

    # Merge: prefer local entries (they have _track_json, no download needed)
    # Dedup by name since hash computation differs between API and local
    seen_names = set()
    merged = []
    for lt in local_tracks:
        name = lt.get("name", "")
        if name not in seen_names:
            merged.append(lt)
            seen_names.add(name)
    for rt in remote_tracks:
        name = rt.get("name", "")
        if name not in seen_names:
            merged.append(rt)
            seen_names.add(name)
    return merged


def _download_track_json(track_entry):
    """Download a track's JSON from the backend, or return local data."""
    if "_track_json" in track_entry:
        return track_entry["_track_json"]
    sha = track_entry.get("content_sha256", "")
    if not sha:
        return None
    try:
        resp = requests.get(
            f"{API_BASE_URL}/tracks/{sha}/download",
            headers=_api_headers(),
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _render_track_preview(track_json):
    """Display a 2D top-down Plotly scatter preview of the track."""
    xs, ys = build_track_preview_data(track_json)
    if not xs:
        st.caption("No hay datos de trazado disponibles para previsualizar.")
        return
    fig = go.Figure()
    # Close the loop for a nicer outline
    xs_closed = list(xs) + [xs[0]]
    ys_closed = list(ys) + [ys[0]]
    fig.add_trace(go.Scatter(
        x=xs_closed, y=ys_closed,
        mode="lines",
        line=dict(color="#1f77b4", width=2),
        showlegend=False,
    ))
    fig.update_layout(
        template="plotly_dark",
        height=300,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        title=dict(
            text=track_json.get("name", "Pista"),
            font=dict(size=14),
        ),
    )
    st.plotly_chart(fig, use_container_width=True)


def _upload_track_to_community(file_bytes, track_json):
    """Upload a parsed track JSON to community storage via ``POST /tracks/upload``."""
    sha = compute_file_sha256(file_bytes)
    try:
        resp = requests.post(
            f"{API_BASE_URL}/tracks/upload",
            json={"sha256_source": sha, "track_json": track_json},
            headers=_api_headers(),
            timeout=15,
        )
        if resp.status_code in (200, 201):
            # Bust the track list cache so the new track appears immediately
            _fetch_track_list.clear()
            return True
        return False
    except Exception:
        return False


def _auto_match_track(df, known_tracks):
    """Try to auto-match telemetry GPS centroid to a known track.

    Returns the matched track entry or None.
    """
    if "GPS_Latitude" not in df.columns or "GPS_Longitude" not in df.columns:
        return None
    mean_lat = float(df["GPS_Latitude"].dropna().mean())
    mean_lon = float(df["GPS_Longitude"].dropna().mean())
    if np.isnan(mean_lat) or np.isnan(mean_lon):
        return None

    # Build centroid list from known tracks (download JSON only when needed)
    enriched = []
    for t in known_tracks:
        if "centroid_lat" in t and "centroid_lon" in t:
            enriched.append(t)
        else:
            tj = _download_track_json(t)
            if tj:
                centroid = compute_track_centroid(tj)
                if centroid:
                    entry = dict(t)
                    entry["centroid_lat"] = centroid[0]
                    entry["centroid_lon"] = centroid[1]
                    entry["_track_json"] = tj
                    enriched.append(entry)

    return find_best_track_match(mean_lat, mean_lon, enriched)


def _render_track_selection_ui(df=None):
    """Render the track selection dropdown, upload flow, and preview.

    *df* is the telemetry DataFrame (may be ``None`` if no telemetry loaded).
    """
    st.header("Seleccion de Pista para Replay 3D")

    # ── 1. Track dropdown ─────────────────────────────────────────────────
    available_tracks = _fetch_track_list()
    track_names = ["(ninguna)"] + [t.get("name", "???") for t in available_tracks]

    # Auto-match attempt
    auto_index = 0
    if df is not None and available_tracks:
        matched = _auto_match_track(df, available_tracks)
        if matched:
            try:
                auto_index = track_names.index(matched["name"])
                st.info(
                    f"Pista auto-detectada por GPS: **{matched['name']}**. "
                    "Puedes cambiarla en el desplegable."
                )
            except ValueError:
                pass

    selected_name = st.selectbox(
        "Pista disponible",
        track_names,
        index=auto_index,
        key="track_selector",
    )

    # Load selected track
    loaded_track_json = None
    if selected_name != "(ninguna)":
        entry = next(
            (t for t in available_tracks if t.get("name") == selected_name),
            None,
        )
        if entry:
            loaded_track_json = _download_track_json(entry)
            if loaded_track_json:
                st.session_state["loaded_track_json"] = loaded_track_json

    # ── 2. AIW/MAS upload (browser-side, via drop zone below) ──────────────
    st.subheader("Subir archivo de pista (.aiw / .mas)")
    st.caption(
        "Arrastra un archivo .aiw o .mas en la zona de abajo. "
        "Los .mas se extraen automáticamente en el navegador."
    )

    # ── 3. Track preview ──────────────────────────────────────────────────
    final_track = loaded_track_json or st.session_state.get("loaded_track_json")
    if final_track:
        _render_track_preview(final_track)
        st.caption(
            f"Waypoints: {len(final_track.get('points', []))} | "
            f"Nombre: {final_track.get('name', 'Desconocido')}"
        )
    else:
        st.info(
            "Selecciona una pista del desplegable o sube un archivo AIW "
            "para previsualizar el trazado."
        )


st.set_page_config(page_title="rFactor2 Engineer", layout="wide")

# Cleanup orphaned temp directories on startup (prevents disk space buildup)
_cleanup_orphaned_temp_dirs(max_age_hours=24)

st.title("🏎️ rFactor2 Engineer")
st.subheader("Análisis de Telemetría y Setup mediante IA")

# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def get_mat_dataframe(file_path):
    """Carga el .mat y devuelve un DataFrame ordenado por tiempo."""
    try:
        mat = scipy.io.loadmat(file_path, struct_as_record=False, squeeze_me=True)
        channels = {}
        for k in mat.keys():
            if not k.startswith('__') and hasattr(mat[k], 'Value'):
                val = mat[k].Value
                if isinstance(val, np.ndarray) and val.ndim > 0:
                    channels[k] = val
                else:
                    # Si es un escalar, convertir a array del mismo tamaño que los demás
                    channels[k] = val

        df = pd.DataFrame(channels)

        # Asegurar que los escalares se expandan
        if not df.empty:
            max_len = len(df)
            for col in df.columns:
                if not isinstance(channels[col], np.ndarray) or channels[col].ndim == 0:
                    df[col] = np.full(max_len, channels[col])

        sort_col = 'Session_Elapsed_Time' if 'Session_Elapsed_Time' in df.columns else df.columns[0]
        df = df.sort_values(by=sort_col).reset_index(drop=True)

        # Filtrar vueltas incompletas
        df = _filter_incomplete_laps_frontend(df)

        return df
    except Exception as e:
        st.error(f"Error procesando .mat: {e}")
        return None


def _filter_incomplete_laps_frontend(df):
    """Filtra vueltas incompletas del DataFrame (out-laps, in-laps)."""
    lap_col = None
    for c in df.columns:
        if 'lap' in c.lower() and 'number' in c.lower():
            lap_col = c
            break
    if lap_col is None and 'Lap_Number' in df.columns:
        lap_col = 'Lap_Number'
    if lap_col is None:
        return df

    dist_col = None
    for c in df.columns:
        if 'distance' in c.lower() and 'lap' in c.lower():
            dist_col = c
            break
    if dist_col is None:
        for c in df.columns:
            if 'distance' in c.lower():
                dist_col = c
                break

    laps = sorted([l for l in df[lap_col].unique() if l > 0])
    if len(laps) <= 1:
        return df[df[lap_col] > 0] if 0 in df[lap_col].values else df

    if dist_col is not None:
        lap_distances = {}
        for lap in laps:
            d = df.loc[df[lap_col] == lap, dist_col].dropna()
            lap_distances[lap] = (d.max() - d.min()) if not d.empty else 0

        # Usar el percentil 95 de las distancias para evitar que vueltas incompletas influyan mucho
        if lap_distances:
            target_dist = np.percentile(list(lap_distances.values()), 95)
            # Solo consideramos completas las vueltas que cubren al menos el 98% de la distancia objetivo
            complete_laps = [l for l, d in lap_distances.items() if d >= target_dist * 0.98]
        else:
            complete_laps = []
    else:
        lap_samples = {lap: len(df[df[lap_col] == lap]) for lap in laps}
        if lap_samples:
            target_samples = np.percentile(list(lap_samples.values()), 95)
            complete_laps = [l for l, s in lap_samples.items() if s >= target_samples * 0.95]
        else:
            complete_laps = []

    if not complete_laps:
        complete_laps = laps

    # Filtrar por duración anómala (vueltas extremadamente lentas como out-laps o errores)
    time_col = 'Session_Elapsed_Time' if 'Session_Elapsed_Time' in df.columns else None
    if time_col and len(complete_laps) > 1:
        lap_durations = {}
        for lap in complete_laps:
            t = df.loc[df[lap_col] == lap, time_col].dropna()
            lap_durations[lap] = (t.max() - t.min()) if not t.empty else 0

        # Filtramos solo si hay una mediana clara (más de 2 vueltas completas)
        if len(complete_laps) > 2:
            middle_laps = complete_laps[1:-1]
            median_dur = np.median([lap_durations[l] for l in middle_laps if lap_durations[l] > 0])
            if median_dur > 0:
                # Permitimos hasta un 50% de margen para no filtrar vueltas lentas legítimas (p.ej. lluvia o errores leves)
                complete_laps = [l for l in complete_laps if lap_durations[l] <= median_dur * 1.50]

    if not complete_laps:
        complete_laps = laps

    return df[df[lap_col].isin(complete_laps)].reset_index(drop=True)


def _lap_xy(lap_df, x_col, y_col):
    """
    Extrae x e y de un DataFrame de vuelta, insertando None donde hay
    discontinuidades en x_col o si el tiempo retrocede (lo cual no debería pasar).
    """
    if x_col not in lap_df.columns or y_col not in lap_df.columns:
        return [], []

    # IMPORTANTE: Los datos ya vienen ordenados por Session_Elapsed_Time desde get_mat_dataframe.
    x_arr = lap_df[x_col].values
    y_arr = lap_df[y_col].values

    if len(x_arr) < 2:
        return x_arr.tolist(), y_arr.tolist()

    # Detectar saltos en el eje X
    # Para Lap_Distance, un salto de >100m en 1 paso temporal es sospechoso.
    # O un salto atrás significativo (>10m).
    xs, ys = [], []
    for i in range(len(x_arr)):
        if i > 0:
            diff = x_arr[i] - x_arr[i-1]
            # Si hay un salto brusco hacia adelante (>200m) o un salto atrás (>10m)
            # en la distancia de la vuelta, rompemos la línea.
            if x_col == 'Lap_Distance':
                if diff < -10.0 or diff > 200.0:
                    xs.append(None)
                    ys.append(None)
            else:
                # Para GPS (Lon/Lat), usamos un umbral dinámico basado en el rango
                x_range = np.ptp(x_arr) if len(x_arr) > 0 else 0
                threshold = max(x_range * 0.05, 0.001)
                if abs(diff) > threshold:
                    xs.append(None)
                    ys.append(None)

        xv = float(x_arr[i])
        yv = float(y_arr[i])
        xs.append(xv if not np.isnan(xv) else None)
        ys.append(yv if not np.isnan(yv) else None)

    return xs, ys


def _build_lap_data(lap_df):
    """Extrae los datos crudos necesarios para la telemetría interactiva."""
    x_col = 'Lap_Distance'
    if x_col not in lap_df.columns:
        return None

    # Datos básicos del mapa y distancia
    data = {
        'max_dist': float(lap_df[x_col].max()),
        'channels': {}
    }

    # Definir qué canales queremos extraer para los gráficos
    # Formato: { 'id_del_grafico': [ ('canal_y', 'Nombre visible'), ... ] }
    chart_configs = {
        'speed': [('Ground_Speed', 'Velocidad (km/h)')],
        'controls': [('Throttle_Pos', 'Acelerador (%)'), ('Brake_Pos', 'Freno (%)')],
        'steer': [('Steering_Wheel_Position', 'Dirección')],
        'rpm': [('Engine_RPM', 'RPM')],
        'gear': [('Gear', 'Marcha')],
        'susp_pos': [(f'Susp_Pos_{w}', f'Susp {w}') for w in ['FL', 'FR', 'RL', 'RR']],
        'ride_height': [(f'Ride_Height_{w}', f'RH {w}') for w in ['FL', 'FR', 'RL', 'RR']],
        'brake_temp': [(f'Brake_Temp_{w}', f'Brake Temp {w}') for w in ['FL', 'FR', 'RL', 'RR']],
        'tyre_pres': [(f'Tyre_Pressure_{w}', f'Tyre Pres {w}') for w in ['FL', 'FR', 'RL', 'RR']],
        'aero': [('Front_Downforce', 'Front DF'), ('Rear_Downforce', 'Rear DF')]
    }

    # Extraer datos para cada canal
    for chart_id, configs in chart_configs.items():
        data['channels'][chart_id] = []
        for col, label in configs:
            if col in lap_df.columns:
                xs, ys = _lap_xy(lap_df, x_col, col)
                # Normalización de unidades si es necesario
                if 'Pos' in col:
                    ys = [v * 100 if v is not None else None for v in ys]
                if 'Height' in col:
                    ys = [v * 1000 if v is not None else None for v in ys]

                data['channels'][chart_id].append({
                    'name': label,
                    'x': xs,
                    'y': ys
                })

    # Datos del mapa (GPS)
    if 'GPS_Longitude' in lap_df.columns and 'GPS_Latitude' in lap_df.columns:
        m_xs, m_ys = _lap_xy(lap_df, 'GPS_Longitude', 'GPS_Latitude')
        # También necesitamos la distancia asociada a cada punto GPS para sincronizar
        dist_arr = lap_df[x_col].values.tolist()

        # Arrays sin breaks de discontinuidad, alineados con dist_arr (mismo índice)
        # para usarlos en el coloreado por freno/acelerador del mapa
        raw_lon = [float(v) if not np.isnan(float(v)) else None
                   for v in lap_df['GPS_Longitude'].values]
        raw_lat = [float(v) if not np.isnan(float(v)) else None
                   for v in lap_df['GPS_Latitude'].values]

        # Freno y acelerador en escala 0-100 (los valores raw de MoTeC son 0-1)
        def _to_pct(col_name):
            if col_name not in lap_df.columns:
                return [0.0] * len(dist_arr)
            out = []
            for v in lap_df[col_name].values:
                try:
                    fv = float(v)
                    out.append(0.0 if np.isnan(fv) else min(100.0, max(0.0, fv * 100.0)))
                except (TypeError, ValueError):
                    out.append(0.0)
            return out

        brake = _to_pct('Brake_Pos')
        throttle = _to_pct('Throttle_Pos')

        # Downsample the per-point arrays to at most MAP_MAX_POINTS so that
        # the colour-marker trace (one SVG node per active point) doesn't
        # produce thousands of DOM nodes and cause hover lag.
        # The smooth outline trace (lon/lat via _lap_xy) is cheap as a
        # polyline and keeps full resolution.
        MAP_MAX_POINTS = 1500
        n_raw = len(dist_arr)
        if n_raw > MAP_MAX_POINTS:
            stride = n_raw // MAP_MAX_POINTS
            raw_lon   = raw_lon[::stride]
            raw_lat   = raw_lat[::stride]
            brake     = brake[::stride]
            throttle  = throttle[::stride]
            dist_arr  = dist_arr[::stride]

        data['map'] = {
            'lon': m_xs,
            'lat': m_ys,
            'dist': dist_arr,
            'raw_lon': raw_lon,
            'raw_lat': raw_lat,
            'brake': brake,
            'throttle': throttle,
        }

    return data


def _build_cockpit_data(lap_df):
    """Extract telemetry arrays for the 3D cockpit replay component.

    Returns a dict of equal-length lists keyed by channel name,
    or None if the required Lap_Distance column is missing.
    """
    x_col = 'Lap_Distance'
    if x_col not in lap_df.columns:
        return None

    n = len(lap_df)

    def _safe_col(col_name, scale=1.0):
        """Extract a column as a plain list, replacing NaN with 0.0."""
        if col_name not in lap_df.columns:
            return [0.0] * n
        out = []
        for v in lap_df[col_name].values:
            try:
                fv = float(v)
                out.append(0.0 if np.isnan(fv) else fv * scale)
            except (TypeError, ValueError):
                out.append(0.0)
        return out

    # Compute average ride height from the four wheel channels
    rh_cols = [f'Ride_Height_{w}' for w in ['FL', 'FR', 'RL', 'RR']]
    available_rh = [c for c in rh_cols if c in lap_df.columns]
    if available_rh:
        rh_avg = lap_df[available_rh].mean(axis=1)
        ride_height_avg = []
        for v in rh_avg.values:
            try:
                fv = float(v)
                ride_height_avg.append(0.0 if np.isnan(fv) else fv)
            except (TypeError, ValueError):
                ride_height_avg.append(0.0)
    else:
        ride_height_avg = [0.0] * n

    # Gear as integers
    gear_raw = _safe_col('Gear')
    gear = [int(round(v)) for v in gear_raw]

    result = {
        'lap_distance': _safe_col(x_col),
        'speed': _safe_col('Ground_Speed'),
        'throttle': _safe_col('Throttle_Pos'),
        'brake': _safe_col('Brake_Pos'),
        'gear': gear,
        'rpm': _safe_col('Engine_RPM'),
        'body_pitch': _safe_col('Body_Pitch'),
        'body_roll': _safe_col('Body_Roll'),
        'g_force_lat': _safe_col('G_Force_Lat'),
        'g_force_long': _safe_col('G_Force_Long'),
        'ride_height_avg': ride_height_avg,
        'steering': _safe_col('Steering_Wheel_Position'),
    }

    # Sort all arrays by lap_distance (binary search in JS requires monotonic order)
    ld = result['lap_distance']
    sort_idx = sorted(range(len(ld)), key=lambda i: ld[i])
    for key in result:
        arr = result[key]
        result[key] = [arr[i] for i in sort_idx]

    return result


def render_3d_cockpit(lap_data, track_json):
    """Return an HTML string containing a self-contained Three.js cockpit replay.

    Parameters
    ----------
    lap_data : dict or None
        Output of ``_build_cockpit_data()``.  May be ``None`` (track-only mode).
    track_json : dict or None
        Track geometry ``{name, source, points: [{x, y, z, width_left, width_right}]}``.
        If ``None`` the component shows a placeholder message.

    The HTML is designed to be embedded via ``st.components.html(html, height=…)``.
    """
    import json as _j

    if track_json is None:
        return "<div style='padding:40px;font-family:sans-serif;color:#888;text-align:center;'>No track data loaded</div>"

    track_js = _j.dumps(track_json)
    telem_js = _j.dumps(lap_data) if lap_data else "null"

    # ── Inline Three.js cockpit HTML ──────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#111; overflow:hidden; font-family:monospace; }}
  #c {{ display:block; width:100%; height:100%; }}
  #hud {{
    position:absolute; top:8px; left:12px; color:#0f0;
    font-size:13px; line-height:1.5; pointer-events:none;
    text-shadow:0 0 4px rgba(0,255,0,0.5);
  }}
  #controls {{
    position:absolute; bottom:8px; left:12px; right:12px;
    display:flex; align-items:center; gap:8px;
    color:#ccc; font-size:12px;
  }}
  #controls button {{
    background:#333; color:#eee; border:1px solid #555;
    padding:4px 10px; cursor:pointer; border-radius:3px;
    font-family:monospace;
  }}
  #controls button:hover {{ background:#555; }}
  #scrub {{
    flex:1; accent-color:#0f0; cursor:pointer;
  }}
  #controls select {{
    background:#333; color:#eee; border:1px solid #555;
    padding:2px 6px; border-radius:3px; font-family:monospace;
  }}
  #dist-label {{ min-width:90px; text-align:right; }}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="pip-btns" style="position:absolute;top:4px;right:4px;z-index:100;display:flex;gap:3px;">
  <button onclick="pipCmd('')" title="Mini" style="font-size:11px;padding:2px 5px;cursor:pointer;background:#333;color:#ccc;border:1px solid #666;border-radius:3px;">🎥</button>
  <button onclick="pipCmd('pip-map')" title="Replace map" style="font-size:11px;padding:2px 5px;cursor:pointer;background:#333;color:#ccc;border:1px solid #666;border-radius:3px;">⬆</button>
  <button onclick="pipCmd('pip-full')" title="Fullscreen" style="font-size:11px;padding:2px 5px;cursor:pointer;background:#333;color:#ccc;border:1px solid #666;border-radius:3px;">⛶</button>
  <button onclick="pipCmd('pip-hidden')" title="Hide" style="font-size:11px;padding:2px 5px;cursor:pointer;background:#333;color:#ccc;border:1px solid #666;border-radius:3px;">✕</button>
</div>
<div id="hud">
  <div id="hud-speed">--- km/h</div>
  <div id="hud-gear">N</div>
  <div id="hud-rpm">---- RPM</div>
  <div id="hud-dist">0 m</div>
</div>
<div id="controls">
  <button id="btn-play">&#9654;</button>
  <select id="speed-sel">
    <option value="0.5">0.5x</option>
    <option value="1" selected>1x</option>
    <option value="2">2x</option>
    <option value="4">4x</option>
  </select>
  <input id="scrub" type="range" min="0" max="1000" value="0" step="1"/>
  <span id="dist-label">0 m</span>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
// PIP state command — sends to parent to change CSS class on #cockpit-pip
function pipCmd(cls) {{
  window.parent.postMessage({{type: 'pipState', cls: cls}}, '*');
  // Also trigger resize after transition
  setTimeout(function() {{ window.dispatchEvent(new Event('resize')); }}, 350);
}}
</script>
<script>

// ─── Data injection ──────────────────────────────────────────────────
window.TRACK_DATA  = {track_js};
window.TELEMETRY_DATA = {telem_js};

const TRACK  = window.TRACK_DATA;
const TELEM  = window.TELEMETRY_DATA;

// ─── Scene setup ─────────────────────────────────────────────────────
const canvas = document.getElementById('c');
window.cockpitCanvas = canvas;
const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true }});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(canvas.clientWidth, canvas.clientHeight);

const scene  = new THREE.Scene();
scene.background = new THREE.Color(0x222233);
scene.fog = new THREE.Fog(0x222233, 500, 3000);

const camera = new THREE.PerspectiveCamera(75, canvas.clientWidth / canvas.clientHeight, 0.5, 3000);
scene.add(camera);

// Lighting
const amb = new THREE.AmbientLight(0xffffff, 0.6);
scene.add(amb);
const dir = new THREE.DirectionalLight(0xffffff, 0.8);
dir.position.set(100, 200, 50);
scene.add(dir);

// ─── Track spline ────────────────────────────────────────────────────
const pts = TRACK.points || [];
console.log('[3D] THREE version:', THREE.REVISION);
console.log('[3D] CatmullRomCurve3 exists:', typeof THREE.CatmullRomCurve3);
console.log('[3D] Track points:', pts.length);
console.log('[3D] First point:', JSON.stringify(pts[0]));
console.log('[3D] TELEM:', TELEM ? Object.keys(TELEM) : 'null');
if (TELEM) console.log('[3D] TELEM lap_distance len:', TELEM.lap_distance ? TELEM.lap_distance.length : 0);
// Track data: x=east, y=north, z=elevation. Three.js: x=east, y=UP, z=north.
// Procedural Z cleanup (Gemini signal decomposition approach):
// 1. Slope clamp (kill monoliths)
// 2. Low-pass filter (extract smooth road profile)
// 3. Scale residual (keep subtle bumps, kill jitter)
const trackSource = TRACK.source || '';
const trustZ = (trackSource === 'aiw' || trackSource === 'tumrt');
let cleanZ = pts.map(p => p.z || 0);
const minZraw = Math.min(...cleanZ);
cleanZ = cleanZ.map(z => z - minZraw); // normalize to 0

// Step 1: Slope clamp — if Z jumps > threshold between consecutive points, clamp
const slopeThreshold = trustZ ? 2.0 : 0.5; // meters
for (let i = 1; i < cleanZ.length; i++) {{
  const delta = cleanZ[i] - cleanZ[i-1];
  if (Math.abs(delta) > slopeThreshold) {{
    cleanZ[i] = cleanZ[i-1] + Math.sign(delta) * slopeThreshold;
  }}
}}

// Step 2: Low-pass filter (moving average, window=21 points) to get Z_smooth
const smoothWindow = 21;
const halfW = Math.floor(smoothWindow / 2);
const zSmooth = cleanZ.map((_, i) => {{
  let sum = 0, count = 0;
  for (let j = Math.max(0, i - halfW); j <= Math.min(cleanZ.length - 1, i + halfW); j++) {{
    sum += cleanZ[j]; count++;
  }}
  return sum / count;
}});

// Step 3: Residual with gain — keep subtle bumps
const bumpGain = trustZ ? 0.3 : 0.0; // OpenF1: no bumps (too noisy); AIW: subtle bumps
const finalZ = zSmooth.map((smooth, i) => smooth + (cleanZ[i] - smooth) * bumpGain);

// Step 4: Scale check — if total Z span is unreasonable for the track, compress
const xSpan = Math.max(...pts.map(p=>p.x)) - Math.min(...pts.map(p=>p.x));
const ySpan = Math.max(...pts.map(p=>p.y)) - Math.min(...pts.map(p=>p.y));
const trackHSpan = Math.max(xSpan, ySpan);
const finalZSpan = Math.max(...finalZ) - Math.min(...finalZ);
const maxReasonableZ = trackHSpan * 0.04; // 4% is steep (e.g. Bathurst)
const globalScale = (finalZSpan > maxReasonableZ && finalZSpan > 0) ? (maxReasonableZ / finalZSpan) : 1.0;

console.log('[3D] Z cleanup: source=', trackSource, 'trustZ=', trustZ, 'rawSpan=', (Math.max(...pts.map(p=>p.z||0)) - Math.min(...pts.map(p=>p.z||0))).toFixed(1), 'cleanSpan=', finalZSpan.toFixed(1), 'globalScale=', globalScale.toFixed(3));
const splinePoints = pts.map((p, i) => new THREE.Vector3(p.x, finalZ[i] * globalScale, p.y));
console.log('[3D] Spline point 0:', splinePoints[0]);
console.log('[3D] Spline point mid:', splinePoints[Math.floor(splinePoints.length/2)]);
const curve = new THREE.CatmullRomCurve3(splinePoints, false, 'catmullrom', 0.5);
console.log('[3D] Curve total length:', curve.getLength());

// ─── Track road mesh ─────────────────────────────────────────────────
const SPLINE_DIVISIONS = Math.max(pts.length * 4, 500);
const sampledPts = curve.getSpacedPoints(SPLINE_DIVISIONS);
const sampledTangents = [];
for (let i = 0; i <= SPLINE_DIVISIONS; i++) {{
  sampledTangents.push(curve.getTangentAt(i / SPLINE_DIVISIONS));
}}

// Interpolate width_left / width_right along sampled points
function lerpWidth(arr, idx) {{
  // arr = pts array, idx = index in SPLINE_DIVISIONS range
  const t = idx / SPLINE_DIVISIONS;
  const fi = t * (pts.length - 1);
  const lo = Math.floor(fi);
  const hi = Math.min(lo + 1, pts.length - 1);
  const frac = fi - lo;
  const wl = (pts[lo].width_left  || 5) * (1 - frac) + (pts[hi].width_left  || 5) * frac;
  const wr = (pts[lo].width_right || 5) * (1 - frac) + (pts[hi].width_right || 5) * frac;
  return {{ wl, wr }};
}}

// Build road ribbon geometry
const roadVerts = [];
const roadUVs   = [];
const roadIdx   = [];
const UP = new THREE.Vector3(0, 1, 0);
const _perp = new THREE.Vector3();

const _flatTan = new THREE.Vector3();
for (let i = 0; i <= SPLINE_DIVISIONS; i++) {{
  const p = sampledPts[i];
  const t = sampledTangents[i];
  // Project tangent onto XZ plane to get horizontal perpendicular (no vertical artifacts)
  _flatTan.set(t.x, 0, t.z).normalize();
  _perp.crossVectors(_flatTan, UP).normalize();
  const {{ wl, wr }} = lerpWidth(pts, i);

  // left edge (keep same Y as road surface)
  roadVerts.push(p.x - _perp.x * wl, p.y, p.z - _perp.z * wl);
  // right edge
  roadVerts.push(p.x + _perp.x * wr, p.y, p.z + _perp.z * wr);

  const v = i / SPLINE_DIVISIONS;
  roadUVs.push(0, v);
  roadUVs.push(1, v);
}}

for (let i = 0; i < SPLINE_DIVISIONS; i++) {{
  const a = i * 2, b = i * 2 + 1, c = (i + 1) * 2, d = (i + 1) * 2 + 1;
  roadIdx.push(a, c, b);
  roadIdx.push(b, c, d);
}}

const roadGeo = new THREE.BufferGeometry();
roadGeo.setAttribute('position', new THREE.Float32BufferAttribute(roadVerts, 3));
roadGeo.setAttribute('uv', new THREE.Float32BufferAttribute(roadUVs, 2));
roadGeo.setIndex(roadIdx);
roadGeo.computeVertexNormals();

console.log('[3D] Road verts:', roadVerts.length / 3, 'tris:', roadIdx.length / 3);
const roadMat = new THREE.MeshLambertMaterial({{ color: 0x666666, side: THREE.DoubleSide }});
const roadMesh = new THREE.Mesh(roadGeo, roadMat);
scene.add(roadMesh);
console.log('[3D] Road mesh added to scene. BBox:', JSON.stringify(new THREE.Box3().setFromObject(roadMesh)));

// Kerb edges (thin lighter strips)
function buildKerbStrip(side) {{
  const verts = [];
  const idx   = [];
  const kerbW = 0.5; // meters

  for (let i = 0; i <= SPLINE_DIVISIONS; i++) {{
    const p = sampledPts[i];
    const t = sampledTangents[i];
    _flatTan.set(t.x, 0, t.z).normalize();
    _perp.crossVectors(_flatTan, UP).normalize();
    const {{ wl, wr }} = lerpWidth(pts, i);
    const w = side === 'left' ? wl : wr;
    const sign = side === 'left' ? -1 : 1;
    const outerW = w + kerbW;

    verts.push(
      p.x + sign * _perp.x * w,       p.y + 0.01, p.z + sign * _perp.z * w,
      p.x + sign * _perp.x * outerW,  p.y + 0.01, p.z + sign * _perp.z * outerW
    );
  }}
  for (let i = 0; i < SPLINE_DIVISIONS; i++) {{
    const a = i * 2, b = i * 2 + 1, c = (i + 1) * 2, d = (i + 1) * 2 + 1;
    idx.push(a, c, b);
    idx.push(b, c, d);
  }}
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  const mat = new THREE.MeshLambertMaterial({{ color: 0xcc2222, side: THREE.DoubleSide }});
  return new THREE.Mesh(geo, mat);
}}
scene.add(buildKerbStrip('left'));
scene.add(buildKerbStrip('right'));

// Ground plane
const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(5000, 5000),
  new THREE.MeshLambertMaterial({{ color: 0x2a3a2a }})
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.1;
scene.add(ground);

// ─── Telemetry helpers ───────────────────────────────────────────────
const totalLength = curve.getLength();
// Use curve length as maxDist — telemetry lap_distance may be in different units or incomplete
// If telemetry maxDist is reasonably close to curve length (within 10x), use it; otherwise use curve length
const telemMaxDist = TELEM ? TELEM.lap_distance[TELEM.lap_distance.length - 1] : 0;
let maxDist;
if (telemMaxDist > totalLength * 0.5 && telemMaxDist < totalLength * 2.0) {{
  maxDist = telemMaxDist; // telemetry and curve agree roughly
}} else if (telemMaxDist > 0 && telemMaxDist < totalLength * 0.01) {{
  // Telemetry is probably in km — convert
  maxDist = telemMaxDist * 1000;
  if (TELEM) TELEM.lap_distance = TELEM.lap_distance.map(d => d * 1000);
  console.log('[3D] Converted lap_distance from km to m');
}} else {{
  maxDist = totalLength;
}}
console.log('[3D] maxDist:', maxDist, 'totalLength:', totalLength, 'telemRaw:', telemMaxDist);

function telemAt(arr, dist) {{
  if (!TELEM || !arr || arr.length === 0) return 0;
  const ld = TELEM.lap_distance;
  // binary search
  let lo = 0, hi = ld.length - 1;
  while (lo < hi) {{
    const mid = (lo + hi) >> 1;
    if (ld[mid] < dist) lo = mid + 1; else hi = mid;
  }}
  if (lo === 0) return arr[0];
  if (lo >= ld.length) return arr[ld.length - 1];
  const t = (dist - ld[lo - 1]) / (ld[lo] - ld[lo - 1] || 1);
  return arr[lo - 1] + (arr[lo] - arr[lo - 1]) * t;
}}

// ─── Camera system ───────────────────────────────────────────────────
const COCKPIT_HEIGHT = 1.5;
let currentPitch = 0;
let currentRoll  = 0;
let currentHeave = 0;

function updateCamera(dist) {{
  const t = Math.max(0, Math.min(1, dist / totalLength));
  const pos = curve.getPointAt(t);
  const tan = curve.getTangentAt(t);

  // Base camera position (cockpit height above road)
  camera.position.set(pos.x, pos.y + COCKPIT_HEIGHT, pos.z);

  if (!window._camLogged) {{
    console.log('[3D] Camera pos:', pos.x.toFixed(1), pos.y.toFixed(1), pos.z.toFixed(1), 'tan:', tan.x.toFixed(2), tan.y.toFixed(2), tan.z.toFixed(2));
    window._camLogged = true;
  }}
  // Look direction
  const lookTarget = new THREE.Vector3(
    pos.x + tan.x * 10,
    pos.y + COCKPIT_HEIGHT + tan.y * 10,
    pos.z + tan.z * 10
  );
  camera.lookAt(lookTarget);

  if (TELEM) {{
    // Target physics offsets
    const targetPitch = telemAt(TELEM.body_pitch, dist)
                      + telemAt(TELEM.g_force_long, dist) * -0.02;
    const targetRoll  = telemAt(TELEM.body_roll, dist)
                      + telemAt(TELEM.g_force_lat, dist) * 0.03;
    const targetHeave = telemAt(TELEM.ride_height_avg, dist);

    // Smooth with lerp
    currentPitch = currentPitch + (targetPitch - currentPitch) * 0.1;
    currentRoll  = currentRoll  + (targetRoll  - currentRoll)  * 0.1;
    currentHeave = currentHeave + (targetHeave - currentHeave) * 0.1;

    camera.rotation.x += currentPitch;
    camera.rotation.z += currentRoll;
    camera.position.y += currentHeave;
  }}
}}

// ─── HUD ─────────────────────────────────────────────────────────────
const hudSpeed = document.getElementById('hud-speed');
const hudGear  = document.getElementById('hud-gear');
const hudRpm   = document.getElementById('hud-rpm');
const hudDist  = document.getElementById('hud-dist');

function updateHUD(dist) {{
  if (TELEM) {{
    const spd = telemAt(TELEM.speed, dist);
    const gear = Math.round(telemAt(TELEM.gear, dist));
    const rpm  = Math.round(telemAt(TELEM.rpm, dist));
    hudSpeed.textContent = spd.toFixed(0) + ' km/h';
    hudGear.textContent  = gear <= 0 ? 'N' : gear.toString();
    hudRpm.textContent   = rpm + ' RPM';
  }} else {{
    hudSpeed.textContent = '--- km/h';
    hudGear.textContent  = '-';
    hudRpm.textContent   = '---- RPM';
  }}
  hudDist.textContent = Math.round(dist) + ' m';
}}

// ─── Playback system ─────────────────────────────────────────────────
let playing = false;
let currentDist = 0;
let playbackSpeed = 1.0;
let lastTime = 0;

const btnPlay  = document.getElementById('btn-play');
const scrub    = document.getElementById('scrub');
const speedSel = document.getElementById('speed-sel');
const distLbl  = document.getElementById('dist-label');

btnPlay.addEventListener('click', () => {{
  playing = !playing;
  btnPlay.innerHTML = playing ? '&#9646;&#9646;' : '&#9654;';
  if (playing) lastTime = performance.now();
  console.log('[3D] Play toggled:', playing, 'maxDist:', maxDist, 'currentDist:', currentDist);
}});

speedSel.addEventListener('change', () => {{
  playbackSpeed = parseFloat(speedSel.value);
}});

scrub.addEventListener('input', () => {{
  currentDist = (parseFloat(scrub.value) / 1000) * maxDist;
  updateCamera(currentDist);
  updateHUD(currentDist);
  // T6: emit position to parent for 2D chart sync
  if (!window._syncInProgress) {{
    window.parent.postMessage({{type: 'cockpitSync', lapDistance: currentDist}}, '*');
  }}
}});

// External API for T6 sync
window.setCockpitPosition = function(lapDistance) {{
  window._syncInProgress = true;
  currentDist = Math.max(0, Math.min(lapDistance, maxDist));
  scrub.value = Math.round((currentDist / maxDist) * 1000);
  distLbl.textContent = Math.round(currentDist) + ' m';
  updateCamera(currentDist);
  updateHUD(currentDist);
  window._syncInProgress = false;
}};

// T6: Listen for sync messages from 2D charts (via parent postMessage)
window.addEventListener('message', function(evt) {{
  if (evt.data && evt.data.type === 'chartSync' && typeof evt.data.lapDistance === 'number') {{
    window.setCockpitPosition(evt.data.lapDistance);
  }}
}});

// ─── Animation loop ──────────────────────────────────────────────────
function animate(time) {{
  requestAnimationFrame(animate);

  if (playing) {{
    const dt = Math.min((time - lastTime) / 1000, 0.1); // cap at 100ms to prevent jumps
    lastTime = time;

    // Advance based on speed at current position (or fixed rate)
    let advance;
    if (TELEM) {{
      const spd = telemAt(TELEM.speed, currentDist); // km/h
      advance = (spd / 3.6) * dt * playbackSpeed;    // m/s * s * multiplier
    }} else {{
      advance = 50 * dt * playbackSpeed; // 50 m/s default
    }}
    currentDist += advance;
    if (!window._advLogged) {{
      console.log('[3D] Frame: dt=', dt.toFixed(3), 'spd=', TELEM ? telemAt(TELEM.speed, currentDist) : 'N/A', 'advance=', advance.toFixed(2), 'currentDist=', currentDist.toFixed(1));
      window._advLogged = true;
    }}
    if (currentDist >= maxDist) {{
      currentDist = 0; // loop
    }}

    scrub.value = Math.round((currentDist / maxDist) * 1000);
    distLbl.textContent = Math.round(currentDist) + ' m';
    // T6: emit position to parent for 2D chart sync during playback
    window.parent.postMessage({{type: 'cockpitSync', lapDistance: currentDist}}, '*');
  }}

  updateCamera(currentDist);
  updateHUD(currentDist);
  renderer.render(scene, camera);
}}

// ─── Resize handling ─────────────────────────────────────────────────
function onResize() {{
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (canvas.width !== w || canvas.height !== h) {{
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }}
}}
window.addEventListener('resize', onResize);
onResize();

// Start
updateCamera(0);
renderer.render(scene, camera);
console.log('[3D] Initial render done. Scene children:', scene.children.length);
console.log('[3D] Renderer size:', renderer.domElement.width, 'x', renderer.domElement.height);
requestAnimationFrame(animate);

</script>
</body>
</html>"""

    return html


@st.cache_resource(show_spinner=False)
def precompute_all_laps(df, laps):
    """
    Pre-genera los datos de todas las vueltas y los devuelve.
    Se cachea en session_state usando (tele_path, laps) como clave para evitar
    hashear el DataFrame entero en cada rerun (causa principal de lentitud).
    """
    all_data = {}
    for lap in laps:
        lap_df = df[df['Lap_Number'] == lap].copy()
        all_data[lap] = _build_lap_data(lap_df)
    return all_data


def plot_all_laps_interactive(all_lap_figs, laps, lap_options, fastest_lap, track_json=None, cockpit_data=None):
    """Renderiza la telemetría interactiva de TODAS las vueltas en un solo componente HTML/JS.
    El cambio de vuelta se gestiona enteramente en el cliente (JavaScript), sin roundtrip al servidor."""
    if not all_lap_figs:
        st.warning("No hay datos de telemetría.")
        return

    import json
    # Convertir claves int a string para JSON
    all_data_json = json.dumps({str(k): v for k, v in all_lap_figs.items() if v})
    track_json_str = json.dumps(track_json) if track_json else "null"
    cockpit_data_str = json.dumps(cockpit_data) if cockpit_data else "null"
    laps_json = json.dumps([int(l) for l in laps])
    lap_labels_json = json.dumps(lap_options)
    fastest_lap_js = int(fastest_lap) if fastest_lap else "null"

    total_height = 1300

    html_code = f"""
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <style>
        body {{ margin: 0; background: #111; }}
        .telemetry-container {{ background-color: #111; color: white; font-family: sans-serif; width: 100%; box-sizing: border-box; display: flex; align-items: flex-start; }}
        .lap-sidebar {{ width: 90px; min-width: 90px; padding: 5px 5px 5px 0; }}
        .lap-btn {{ display: block; width: 100%; padding: 4px 6px; margin-bottom: 3px; background: #222; border: 1px solid #444; color: #ccc; cursor: pointer; font-size: 0.7rem; text-align: left; border-radius: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .lap-btn:hover {{ background: #333; }}
        .lap-btn.active {{ background: #444; color: white; font-weight: bold; border-color: #888; }}
        .lap-btn.fastest {{ color: #ffa500; }}
        .charts-area {{ flex: 1; min-width: 0; }}
        .tabs {{ display: flex; border-bottom: 1px solid #444; margin-bottom: 10px; }}
        .tab {{ padding: 10px 20px; cursor: pointer; border: 1px solid transparent; color: #ccc; }}
        .tab.active {{ border: 1px solid #444; border-bottom: 1px solid #111; background: #222; font-weight: bold; color: white; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .chart-wrapper {{ position: relative; width: 100%; margin-bottom: 5px; box-sizing: border-box; cursor: grab; }}
        .chart-wrapper:active {{ cursor: grabbing; }}
        .chart-wrapper canvas.red-line {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 10; }}
        #map-container {{ width: 100%; margin-bottom: 15px; border: 1px solid #333; position: relative; }}
        #cockpit-pip {{
            position: absolute; bottom: 4px; right: 4px;
            width: 200px; height: 150px;
            z-index: 50; border: 1px solid #555;
            border-radius: 4px; overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
            background: #1a1a2e;
        }}
        #cockpit-pip canvas {{ width: 100% !important; height: 100% !important; }}
        #cockpit-pip.pip-hidden {{ display: none; }}
        #cockpit-pip.pip-map {{
            position: relative; bottom: auto; right: auto;
            width: 100%; height: 300px; border-radius: 0;
        }}
        #cockpit-pip.pip-full {{
            position: fixed; top: 0; left: 0;
            width: 100vw; height: 100vh;
            z-index: 10000; border: none; border-radius: 0;
        }}
        #cockpit-pip .pip-btns {{
            position: absolute; top: 2px; right: 2px; z-index: 60;
            display: flex; gap: 2px;
        }}
        #cockpit-pip .pip-btns button {{
            font-size: 9px; padding: 1px 4px; cursor: pointer;
            background: rgba(30,30,30,0.8); color: #ccc;
            border: 1px solid #666; border-radius: 2px;
        }}
        #cockpit-pip .pip-btns button:hover {{ background: #555; }}
        #cockpit-pip .pip-hud {{
            position: absolute; top: 2px; left: 4px; z-index: 60;
            font-family: monospace; font-size: 9px; color: #0f0;
            text-shadow: 0 0 3px #000;
        }}
        #cockpit-pip .pip-controls {{
            position: absolute; bottom: 2px; left: 4px; right: 4px;
            z-index: 60; display: flex; align-items: center; gap: 3px;
        }}
        #cockpit-pip .pip-controls button, #cockpit-pip .pip-controls select {{
            font-size: 9px; padding: 1px 3px; background: rgba(30,30,30,0.8);
            color: #ccc; border: 1px solid #666; border-radius: 2px; cursor: pointer;
        }}
        #cockpit-pip .pip-controls input[type=range] {{ flex: 1; height: 8px; }}
    </style>

    <div class="telemetry-container">
        <div class="lap-sidebar" id="lap-sidebar"></div>
        <div class="charts-area">
            <div id="map-container">
                <div id="cockpit-pip">
                    <div class="pip-btns">
                        <button onclick="setPipState('')" title="Mini">🎥</button>
                        <button onclick="setPipState('pip-map')" title="Replace map">⬆</button>
                        <button onclick="setPipState('pip-full')" title="Fullscreen">⛶</button>
                        <button onclick="setPipState('pip-hidden')" title="Hide">✕</button>
                    </div>
                    <div class="pip-hud">
                        <div id="pip-speed">--- km/h</div>
                        <div id="pip-gear">N</div>
                    </div>
                    <canvas id="cockpit-canvas"></canvas>
                    <div class="pip-controls">
                        <button id="pip-play">▶</button>
                        <select id="pip-speed-sel"><option value="0.5">½</option><option value="1" selected>1x</option><option value="2">2x</option><option value="4">4x</option></select>
                        <input type="range" id="pip-scrub" min="0" max="1000" value="0">
                    </div>
                </div>
            </div>

            <div class="tabs">
                <div class="tab active" onclick="showTab('general', this)">General</div>
                <div class="tab" onclick="showTab('motor', this)">Motor</div>
                <div class="tab" onclick="showTab('suspension', this)">Suspensión</div>
                <div class="tab" onclick="showTab('neumaticos', this)">Neumáticos</div>
                <div class="tab" onclick="showTab('aero', this)">Aerodinámica</div>
            </div>

            <div id="general" class="tab-content active">
                <div id="wrap-speed" class="chart-wrapper"><div id="chart-speed"></div><canvas class="red-line"></canvas></div>
                <div id="wrap-controls" class="chart-wrapper"><div id="chart-controls"></div><canvas class="red-line"></canvas></div>
                <div id="wrap-steer" class="chart-wrapper"><div id="chart-steer"></div><canvas class="red-line"></canvas></div>
            </div>
            <div id="motor" class="tab-content">
                <div id="wrap-rpm" class="chart-wrapper"><div id="chart-rpm"></div><canvas class="red-line"></canvas></div>
                <div id="wrap-gear" class="chart-wrapper"><div id="chart-gear"></div><canvas class="red-line"></canvas></div>
            </div>
            <div id="suspension" class="tab-content">
                <div id="wrap-susp_pos" class="chart-wrapper"><div id="chart-susp_pos"></div><canvas class="red-line"></canvas></div>
                <div id="wrap-ride_height" class="chart-wrapper"><div id="chart-ride_height"></div><canvas class="red-line"></canvas></div>
            </div>
            <div id="neumaticos" class="tab-content">
                <div id="wrap-brake_temp" class="chart-wrapper"><div id="chart-brake_temp"></div><canvas class="red-line"></canvas></div>
                <div id="wrap-tyre_pres" class="chart-wrapper"><div id="chart-tyre_pres"></div><canvas class="red-line"></canvas></div>
            </div>
            <div id="aero" class="tab-content">
                <div id="wrap-aero" class="chart-wrapper"><div id="chart-aero"></div><canvas class="red-line"></canvas></div>
            </div>
        </div>
    </div>

    <script>
        const allLapData = {all_data_json};
        const laps = {laps_json};
        const lapLabels = {lap_labels_json};
        const fastestLap = {fastest_lap_js};

        // 3D Cockpit data
        const COCKPIT_TRACK = {track_json_str};
        const COCKPIT_TELEM = {cockpit_data_str};
        let currentLap = laps[0];
        let lapData = allLapData[String(currentLap)];

        const charts = [];
        let mapChart = null;
        let isDragging = false;
        let pendingX = null;
        let rafId = null;
        let lastX = 0;
        let _syncInProgress = false;

        // Build lap sidebar buttons
        const sidebar = document.getElementById('lap-sidebar');
        laps.forEach((lap, i) => {{
            const btn = document.createElement('button');
            btn.className = 'lap-btn' + (i === 0 ? ' active' : '') + (lap === fastestLap ? ' fastest' : '');
            btn.textContent = lapLabels[i];
            btn.dataset.lap = lap;
            btn.addEventListener('click', () => switchLap(lap));
            sidebar.appendChild(btn);
        }});

        function switchLap(lap) {{
            if (lap === currentLap) return;
            currentLap = lap;
            lapData = allLapData[String(lap)];
            lastX = 0;

            // Update sidebar active state
            sidebar.querySelectorAll('.lap-btn').forEach(b => {{
                b.classList.toggle('active', parseInt(b.dataset.lap) === lap);
            }});

            // Update map
            if (lapData.map && mapChart) {{
                const mc = computeMapColors(lapData.map.brake || [], lapData.map.throttle || []);
                const ai = mc.reduce((a, c, i) => {{ if (c !== null) a.push(i); return a; }}, []);
                Plotly.react(mapChart, [
                    {{ x: lapData.map.lon, y: lapData.map.lat, mode: 'lines', line: {{ color: '#444', width: 1.5 }}, hoverinfo: 'skip' }},
                    {{ x: ai.map(i => lapData.map.raw_lon[i]), y: ai.map(i => lapData.map.raw_lat[i]),
                       mode: 'markers', marker: {{ color: ai.map(i => mc[i]), size: 4, opacity: 0.9 }}, hoverinfo: 'skip' }},
                    {{ x: [lapData.map.raw_lon ? lapData.map.raw_lon[0] : lapData.map.lon[0]],
                       y: [lapData.map.raw_lat ? lapData.map.raw_lat[0] : lapData.map.lat[0]],
                       mode: 'markers', marker: {{ color: 'white', size: 12, symbol: 'x', line: {{ color: '#ff0', width: 2 }} }}, name: 'Coche' }}
                ], mapChart.layout, {{ displayModeBar: false, staticPlot: true }});
            }}

            // Rebuild map binary search index
            rebuildMapIndex();

            // Update all charts with new data
            const newMaxDist = lapData.max_dist;
            charts.forEach(c => {{
                const chData = lapData.channels[c.id];
                if (!chData) return;
                const traces = chData.map(ch => ({{
                    x: ch.x, y: ch.y, name: ch.name,
                    mode: 'lines', line: {{ width: 1.5 }}, connectgaps: false
                }}));
                const newLayout = Object.assign({{}}, c.el.layout, {{
                    xaxis: Object.assign({{}}, c.el.layout.xaxis, {{ range: [0, newMaxDist] }})
                }});
                Plotly.react(c.el, traces, newLayout, {{ displayModeBar: false, staticPlot: true }});
            }});

            // Clear red lines
            drawAllRedLines();
        }}

        // Tab switching
        function showTab(tabId, tabEl) {{
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            tabEl.classList.add('active');
            requestAnimationFrame(() => {{
                const tab = document.getElementById(tabId);
                tab.querySelectorAll('.chart-wrapper > div:first-child').forEach(c => {{
                    if (c.data) Plotly.Plots.resize(c);
                }});
                drawAllRedLines();
            }});
        }}

        // Binary search for map position
        let mapDistSorted = null;
        let mapDistIndices = null;

        function rebuildMapIndex() {{
            if (lapData.map) {{
                const n = lapData.map.dist.length;
                mapDistIndices = Array.from({{length: n}}, (_, i) => i);
                mapDistIndices.sort((a, b) => lapData.map.dist[a] - lapData.map.dist[b]);
                mapDistSorted = mapDistIndices.map(i => lapData.map.dist[i]);
            }} else {{
                mapDistSorted = null;
                mapDistIndices = null;
            }}
        }}
        rebuildMapIndex();

        function findClosestMapIdx(x) {{
            let lo = 0, hi = mapDistSorted.length - 1;
            while (lo < hi) {{
                const mid = (lo + hi) >> 1;
                if (mapDistSorted[mid] < x) lo = mid + 1;
                else hi = mid;
            }}
            if (lo > 0 && Math.abs(mapDistSorted[lo-1] - x) < Math.abs(mapDistSorted[lo] - x)) lo--;
            return mapDistIndices[lo];
        }}

        const commonLayout = {{
            template: "plotly_dark",
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            margin: {{ l: 60, r: 20, t: 35, b: 55 }},
            xaxis: {{ title: "Distancia (m)", range: [0, lapData.max_dist], fixedrange: true, gridcolor: '#333' }},
            yaxis: {{ gridcolor: '#333', autorange: true, fixedrange: true }},
            showlegend: true,
            legend: {{ orientation: "h", y: -0.15, x: 0, xanchor: 'left', font: {{ size: 10 }} }},
            hovermode: false,
            dragmode: false
        }};

        // ── Coloreado del mapa por freno (rojo) y acelerador (azul) ──────────
        // Mezcla: brake=100%,throttle=0% → rojo; throttle=100%,brake=0% → azul
        // Ambos al 100% → morado. Gradiente desde blanco (0%) hasta color puro (100%).
        // Los tramos inactivos (coast) no se pintan.
        function computeMapColors(brake, throttle) {{
            return brake.map(function(b, i) {{
                var t = (throttle[i] || 0) / 100;
                var bn = (b || 0) / 100;
                var combined = Math.max(bn, t);
                if (combined < 0.05) return null;          // coast: sin color
                var total = bn + t;
                var bFrac = total > 0 ? bn / total : 0;
                var tFrac = 1 - bFrac;
                // Hue objetivo: mezcla entre rojo (bFrac) y azul (tFrac)
                var targetR = Math.round(bFrac * 255);
                var targetB = Math.round(tFrac * 255);
                // Interpolar desde blanco hasta el hue objetivo con 'combined' como saturación
                var r  = Math.round(255 + combined * (targetR - 255));
                var g  = Math.round(255 + combined * (0      - 255));
                var bl = Math.round(255 + combined * (targetB - 255));
                return 'rgb(' + r + ',' + g + ',' + bl + ')';
            }});
        }}

        // Map
        if (lapData.map) {{
            // Traza 0: línea gris de fondo (contorno del circuito)
            const mapTrace = {{
                x: lapData.map.lon, y: lapData.map.lat,
                mode: 'lines', line: {{ color: '#444', width: 1.5 }}, hoverinfo: 'skip'
            }};
            // Traza 1: marcadores coloreados (freno=rojo, acelerador=azul, mezcla=morado)
            const mapColors = computeMapColors(lapData.map.brake || [], lapData.map.throttle || []);
            const activeIdx = mapColors.reduce(function(a, c, i) {{ if (c !== null) a.push(i); return a; }}, []);
            const colorTrace = {{
                x: activeIdx.map(function(i) {{ return lapData.map.raw_lon ? lapData.map.raw_lon[i] : lapData.map.lon[i]; }}),
                y: activeIdx.map(function(i) {{ return lapData.map.raw_lat ? lapData.map.raw_lat[i] : lapData.map.lat[i]; }}),
                mode: 'markers',
                marker: {{ color: activeIdx.map(function(i) {{ return mapColors[i]; }}), size: 4, opacity: 0.9 }},
                hoverinfo: 'skip'
            }};
            // Traza 2: posición del coche
            const posTrace = {{
                x: [lapData.map.raw_lon ? lapData.map.raw_lon[0] : lapData.map.lon[0]],
                y: [lapData.map.raw_lat ? lapData.map.raw_lat[0] : lapData.map.lat[0]],
                mode: 'markers', marker: {{ color: 'white', size: 12, symbol: 'x', line: {{ color: '#ff0', width: 2 }} }}, name: 'Coche'
            }};
            mapChart = document.getElementById('map-container');
            Plotly.newPlot(mapChart, [mapTrace, colorTrace, posTrace], {{
                template: "plotly_dark",
                paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
                height: 250,
                xaxis: {{ visible: false, fixedrange: true }},
                yaxis: {{ visible: false, scaleanchor: "x", scaleratio: 1, fixedrange: true }},
                margin: {{ l: 10, r: 10, t: 10, b: 10 }},
                showlegend: false, dragmode: false
            }}, {{ displayModeBar: false, staticPlot: true }});
        }}

        // Charts
        const chartIds = [
            'speed', 'controls', 'steer', 'rpm', 'gear',
            'susp_pos', 'ride_height', 'brake_temp', 'tyre_pres', 'aero'
        ];
        const chartTitles = {{
            speed: 'Velocidad', controls: 'Controles', steer: 'Dirección',
            rpm: 'RPM', gear: 'Marcha',
            susp_pos: 'Posición Suspensión', ride_height: 'Altura al Suelo',
            brake_temp: 'Temp. Frenos', tyre_pres: 'Presión Neumáticos',
            aero: 'Aerodinámica'
        }};

        const plotPromises = [];

        chartIds.forEach(id => {{
            const container = document.getElementById('chart-' + id);
            const wrapper = document.getElementById('wrap-' + id);
            if (!container || !wrapper || !lapData.channels[id]) return;

            const canvas = wrapper.querySelector('canvas.red-line');
            const traces = lapData.channels[id].map(ch => ({{
                x: ch.x, y: ch.y, name: ch.name,
                mode: 'lines', line: {{ width: 1.5 }}, connectgaps: false
            }}));

            const chartHeight = (id === 'gear') ? 250 : 320;

            const p = Plotly.newPlot(container, traces, {{
                ...commonLayout,
                height: chartHeight,
                title: {{ text: chartTitles[id] || id.toUpperCase(), font: {{ size: 13 }} }}
            }}, {{ displayModeBar: false, staticPlot: true }});

            plotPromises.push(p);
            charts.push({{ el: container, id: id, wrapper: wrapper, canvas: canvas }});

            wrapper.addEventListener('mousedown', function(e) {{
                isDragging = true;
                syncFromEvent(e, container);
            }});
            wrapper.addEventListener('mousemove', function(e) {{
                if (isDragging) syncFromEvent(e, container);
            }});
        }});

        document.addEventListener('mouseup', () => {{ isDragging = false; }});
        document.addEventListener('selectstart', (e) => {{ if (isDragging) e.preventDefault(); }});

        function resizeAllCharts() {{
            const allTabs = document.querySelectorAll('.tab-content');
            allTabs.forEach(t => {{
                if (!t.classList.contains('active')) {{
                    t.style.display = 'block';
                    t.style.visibility = 'hidden';
                    t.style.height = '0';
                    t.style.overflow = 'hidden';
                }}
            }});
            charts.forEach(c => Plotly.Plots.resize(c.el));
            if (mapChart && mapChart.data) Plotly.Plots.resize(mapChart);
            allTabs.forEach(t => {{
                if (!t.classList.contains('active')) {{
                    t.style.display = '';
                    t.style.visibility = '';
                    t.style.height = '';
                    t.style.overflow = '';
                }}
            }});
            drawAllRedLines();
        }}

        Promise.all(plotPromises).then(() => {{
            resizeAllCharts();
            setTimeout(resizeAllCharts, 100);
            setTimeout(resizeAllCharts, 500);
        }});

        const ro = new ResizeObserver(() => {{ resizeAllCharts(); }});
        ro.observe(document.querySelector('.telemetry-container'));

        function syncFromEvent(e, container) {{
            const layout = container._fullLayout;
            if (!layout) return;
            const l = layout.margin.l;
            const plotWidth = layout.width - l - layout.margin.r;
            const containerRect = container.getBoundingClientRect();
            const relX = e.clientX - containerRect.left - l;
            const fraction = relX / plotWidth;
            const xRange = layout.xaxis.range;
            const xVal = xRange[0] + fraction * (xRange[1] - xRange[0]);
            const clampedX = Math.max(0, Math.min(lapData.max_dist, xVal));
            scheduleSync(clampedX);
        }}

        function scheduleSync(x) {{
            pendingX = x;
            if (!rafId) {{
                rafId = requestAnimationFrame(() => {{
                    rafId = null;
                    sync(pendingX);
                }});
            }}
        }}

        function drawRedLine(chart, x) {{
            const canvas = chart.canvas;
            const el = chart.el;
            const layout = el._fullLayout;
            if (!layout || !canvas) return;

            const w = el.offsetWidth;
            const h = el.offsetHeight;
            if (canvas.width !== w || canvas.height !== h) {{
                canvas.width = w;
                canvas.height = h;
            }}

            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, w, h);

            const ml = layout.margin.l;
            const mr = layout.margin.r;
            const mt = layout.margin.t;
            const mb = layout.margin.b;
            const plotWidth = w - ml - mr;
            const xRange = layout.xaxis.range;
            const fraction = (x - xRange[0]) / (xRange[1] - xRange[0]);
            const px = ml + fraction * plotWidth;

            ctx.beginPath();
            ctx.moveTo(px, mt);
            ctx.lineTo(px, h - mb);
            ctx.strokeStyle = 'red';
            ctx.lineWidth = 2;
            ctx.stroke();
        }}

        function drawAllRedLines() {{
            charts.forEach(c => drawRedLine(c, lastX));
        }}

        function sync(x) {{
            lastX = x;
            drawAllRedLines();

            if (mapChart && lapData.map && mapDistSorted) {{
                const idx = findClosestMapIdx(x);
                const posLon = lapData.map.raw_lon ? lapData.map.raw_lon[idx] : lapData.map.lon[idx];
                const posLat = lapData.map.raw_lat ? lapData.map.raw_lat[idx] : lapData.map.lat[idx];
                Plotly.restyle(mapChart, {{
                    x: [[posLon]],
                    y: [[posLat]]
                }}, [2]);
            }}

            // T6: forward position to 3D cockpit iframe(s) via parent
            if (!_syncInProgress) {{
                try {{
                    window.parent.postMessage({{type: 'chartSync', lapDistance: x}}, '*');
                }} catch(e) {{}}
            }}
        }}
        // Keep lap sidebar visible by tracking parent scroll
        function updateSidebarPosition() {{
            const sidebar = document.getElementById('lap-sidebar');
            if (!sidebar) return;
            try {{
                const iframeRect = window.frameElement ? window.frameElement.getBoundingClientRect() : null;
                if (iframeRect) {{
                    const scrolledAbove = Math.max(0, -iframeRect.top);
                    const viewportH = window.parent.innerHeight || window.innerHeight;
                    const sidebarH = sidebar.offsetHeight;
                    // Center the sidebar in the visible portion of the iframe
                    const visibleTop = scrolledAbove;
                    const visibleBottom = scrolledAbove + viewportH;
                    const visibleH = visibleBottom - visibleTop;
                    let targetY = visibleTop + Math.max(0, (visibleH - sidebarH) / 2);
                    // Clamp so sidebar doesn't go below container
                    const containerH = sidebar.parentElement ? sidebar.parentElement.offsetHeight : 0;
                    targetY = Math.min(targetY, Math.max(0, containerH - sidebarH));
                    targetY = Math.max(0, targetY);
                    sidebar.style.transform = 'translateY(' + targetY + 'px)';
                }}
            }} catch(e) {{}}
        }}
        // Listen to parent scroll
        try {{
            window.parent.addEventListener('scroll', updateSidebarPosition, true);
            // Also listen on all scrollable ancestors
            let el = window.frameElement;
            while (el) {{
                el = el.parentElement;
                if (el) el.addEventListener('scroll', updateSidebarPosition, true);
            }}
        }} catch(e) {{}}
        setInterval(updateSidebarPosition, 100);

        // ── 3D Cockpit PIP (embedded in map container) ─────────────────
        function setPipState(cls) {{
            var el = document.getElementById('cockpit-pip');
            if (el) {{ el.className = cls; }}
        }}

        (function initCockpitPIP() {{
            if (!COCKPIT_TRACK || !COCKPIT_TRACK.points || COCKPIT_TRACK.points.length < 3) {{
                var pip = document.getElementById('cockpit-pip');
                if (pip) pip.style.display = 'none';
                return;
            }}
            var pts = COCKPIT_TRACK.points;
            var canvas = document.getElementById('cockpit-canvas');
            if (!canvas || typeof THREE === 'undefined') return;

            var renderer = new THREE.WebGLRenderer({{ canvas: canvas, antialias: true }});
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            renderer.setSize(canvas.clientWidth, canvas.clientHeight);

            var scene = new THREE.Scene();
            scene.background = new THREE.Color(0x222233);
            scene.fog = new THREE.Fog(0x222233, 500, 3000);

            var camera = new THREE.PerspectiveCamera(75, canvas.clientWidth / canvas.clientHeight, 0.5, 5000);
            scene.add(camera);
            scene.add(new THREE.AmbientLight(0xffffff, 0.6));
            var dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
            dirLight.position.set(100, 200, 50);
            scene.add(dirLight);

            // Z cleanup — slope clamp + smooth
            var trustZ = (COCKPIT_TRACK.source === 'aiw' || COCKPIT_TRACK.source === 'tumrt');
            var cleanZ = pts.map(function(p) {{ return p.z || 0; }});
            var minZ = Math.min.apply(null, cleanZ);
            cleanZ = cleanZ.map(function(z) {{ return z - minZ; }});
            var thresh = trustZ ? 2.0 : 0.5;
            for (var i = 1; i < cleanZ.length; i++) {{
                var d = cleanZ[i] - cleanZ[i-1];
                if (Math.abs(d) > thresh) cleanZ[i] = cleanZ[i-1] + (d > 0 ? thresh : -thresh);
            }}
            // Moving average
            var smooth = cleanZ.map(function(_, idx) {{
                var s = 0, c = 0;
                for (var j = Math.max(0, idx-10); j <= Math.min(cleanZ.length-1, idx+10); j++) {{ s += cleanZ[j]; c++; }}
                return s / c;
            }});
            var xSpan = Math.max.apply(null, pts.map(function(p){{return p.x;}})) - Math.min.apply(null, pts.map(function(p){{return p.x;}}));
            var ySpan = Math.max.apply(null, pts.map(function(p){{return p.y;}})) - Math.min.apply(null, pts.map(function(p){{return p.y;}}));
            var zSpan = Math.max.apply(null, smooth) - Math.min.apply(null, smooth);
            var maxZ = Math.max(xSpan, ySpan) * 0.04;
            var gScale = (zSpan > maxZ && zSpan > 0) ? maxZ / zSpan : 1.0;

            var splinePts = pts.map(function(p, i) {{
                return new THREE.Vector3(p.x, smooth[i] * gScale, p.y);
            }});
            var curve = new THREE.CatmullRomCurve3(splinePts, false, 'catmullrom', 0.5);
            var totalLen = curve.getLength();

            // Simple road ribbon
            var DIVS = Math.max(pts.length * 2, 200);
            var roadV = [], roadI = [];
            var UP = new THREE.Vector3(0,1,0), perp = new THREE.Vector3(), ft = new THREE.Vector3();
            for (var i = 0; i <= DIVS; i++) {{
                var t = i / DIVS;
                var sp = curve.getPointAt(t);
                var st2 = curve.getTangentAt(t);
                ft.set(st2.x, 0, st2.z).normalize();
                perp.crossVectors(ft, UP).normalize();
                var fi = t * (pts.length - 1), lo = Math.floor(fi), hi = Math.min(lo+1, pts.length-1), fr = fi - lo;
                var wl = ((pts[lo].width_left||5)*(1-fr) + (pts[hi].width_left||5)*fr);
                var wr = ((pts[lo].width_right||5)*(1-fr) + (pts[hi].width_right||5)*fr);
                roadV.push(sp.x - perp.x*wl, sp.y, sp.z - perp.z*wl);
                roadV.push(sp.x + perp.x*wr, sp.y, sp.z + perp.z*wr);
            }}
            for (var i = 0; i < DIVS; i++) {{
                var a=i*2, b=i*2+1, c=(i+1)*2, dd=(i+1)*2+1;
                roadI.push(a,c,b, b,c,dd);
            }}
            var geo = new THREE.BufferGeometry();
            geo.setAttribute('position', new THREE.Float32BufferAttribute(roadV, 3));
            geo.setIndex(roadI);
            geo.computeVertexNormals();
            scene.add(new THREE.Mesh(geo, new THREE.MeshLambertMaterial({{ color: 0x666666, side: THREE.DoubleSide }})));

            // Ground
            var gnd = new THREE.Mesh(new THREE.PlaneBufferGeometry(10000, 10000),
                new THREE.MeshLambertMaterial({{ color: 0x2a3a20 }}));
            gnd.rotation.x = -Math.PI/2; gnd.position.y = -0.5;
            scene.add(gnd);

            // Telemetry
            var CT = COCKPIT_TELEM;
            var telemMax = CT ? CT.lap_distance[CT.lap_distance.length-1] : 0;
            // Auto-detect km vs m
            if (telemMax > 0 && telemMax < totalLen * 0.01) {{
                CT.lap_distance = CT.lap_distance.map(function(d){{ return d * 1000; }});
                telemMax = CT.lap_distance[CT.lap_distance.length-1];
            }}
            var cockpitMaxDist = (telemMax > totalLen * 0.5 && telemMax < totalLen * 2) ? telemMax : totalLen;

            function telemAt(arr, dist) {{
                if (!CT || !arr || arr.length === 0) return 0;
                var ld = CT.lap_distance;
                var lo2 = 0, hi2 = ld.length - 1;
                while (lo2 < hi2) {{ var mid = (lo2+hi2)>>1; if (ld[mid] < dist) lo2=mid+1; else hi2=mid; }}
                return arr[lo2];
            }}

            // Camera + playback state
            var cockpitDist = 0, cockpitPlaying = false, cockpitSpeed = 1, cockpitLastTime = 0;
            var curPitch = 0, curRoll = 0, curHeave = 0;

            function updateCockpit(dist) {{
                var t = Math.max(0, Math.min(0.999, dist / totalLen));
                var pos = curve.getPointAt(t);
                var tan = curve.getTangentAt(t);
                camera.position.set(pos.x, pos.y + 1.5, pos.z);
                camera.lookAt(pos.x + tan.x*10, pos.y + 1.5 + tan.y*10, pos.z + tan.z*10);
                if (CT) {{
                    var tp = telemAt(CT.body_pitch, dist) + telemAt(CT.g_force_long, dist)*-0.02;
                    var tr = telemAt(CT.body_roll, dist) + telemAt(CT.g_force_lat, dist)*0.03;
                    var th = telemAt(CT.ride_height_avg, dist);
                    curPitch += (tp - curPitch)*0.1; curRoll += (tr - curRoll)*0.1; curHeave += (th - curHeave)*0.1;
                    camera.rotation.x += curPitch; camera.rotation.z += curRoll; camera.position.y += curHeave;
                }}
                // HUD
                var sp = CT ? telemAt(CT.speed, dist) : 0;
                var gr = CT ? telemAt(CT.gear, dist) : 0;
                var sEl = document.getElementById('pip-speed');
                var gEl = document.getElementById('pip-gear');
                if (sEl) sEl.textContent = Math.round(sp) + ' km/h';
                if (gEl) gEl.textContent = gr > 0 ? gr : 'N';
            }}

            // Controls
            var playBtn = document.getElementById('pip-play');
            var scrub = document.getElementById('pip-scrub');
            var speedSel = document.getElementById('pip-speed-sel');
            if (playBtn) playBtn.addEventListener('click', function() {{
                cockpitPlaying = !cockpitPlaying;
                playBtn.textContent = cockpitPlaying ? '⏸' : '▶';
                if (cockpitPlaying) cockpitLastTime = performance.now();
            }});
            if (scrub) scrub.addEventListener('input', function() {{
                cockpitDist = (parseFloat(scrub.value)/1000) * cockpitMaxDist;
                updateCockpit(cockpitDist);
                renderer.render(scene, camera);
                sync(cockpitDist); // sync with 2D charts
            }});
            if (speedSel) speedSel.addEventListener('change', function() {{
                cockpitSpeed = parseFloat(speedSel.value);
            }});

            // Animation loop
            function animateCockpit(time) {{
                requestAnimationFrame(animateCockpit);
                if (cockpitPlaying) {{
                    var dt = Math.min((time - cockpitLastTime)/1000, 0.1);
                    cockpitLastTime = time;
                    var spd = CT ? telemAt(CT.speed, cockpitDist) : 150;
                    cockpitDist += (spd/3.6) * dt * cockpitSpeed;
                    if (cockpitDist >= cockpitMaxDist) cockpitDist = 0;
                    if (scrub) scrub.value = Math.round((cockpitDist/cockpitMaxDist)*1000);
                    sync(cockpitDist); // sync 2D charts while playing
                }}
                updateCockpit(cockpitDist);
                // Resize if needed
                if (canvas.clientWidth !== renderer.domElement.width || canvas.clientHeight !== renderer.domElement.height) {{
                    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
                    camera.aspect = canvas.clientWidth / canvas.clientHeight;
                    camera.updateProjectionMatrix();
                }}
                renderer.render(scene, camera);
            }}

            // Also sync cockpit when 2D charts are hovered (sync calls us)
            window.cockpitSyncFromCharts = function(dist) {{
                cockpitDist = dist;
                if (scrub) scrub.value = Math.round((dist/cockpitMaxDist)*1000);
            }};

            updateCockpit(0);
            requestAnimationFrame(animateCockpit);
        }})();

        // Hook cockpit sync into existing sync() function
        var _origSync = sync;
        sync = function(x) {{
            _origSync(x);
            if (window.cockpitSyncFromCharts) window.cockpitSyncFromCharts(x);
        }};
    </script>
    """
    import streamlit.components.v1 as components
    st.markdown("""
    <style>
        .stHtml iframe, .element-container iframe { width: 100% !important; }
        div[data-testid="stIFrame"] iframe { width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)
    components.html(html_code, height=total_height, scrolling=False)

    # T6: Inject parent-level message relay for bidirectional 3D/2D sync.
    # Both cockpit and charts live in separate iframes. When one posts a
    # message to the parent, this relay forwards it to all sibling iframes.
    st.markdown("""
    <script>
    (function() {
        if (window._t6SyncRelayInstalled) return;
        window._t6SyncRelayInstalled = true;
        window.addEventListener('message', function(evt) {
            if (!evt.data || !evt.data.type) return;
            if (evt.data.type !== 'cockpitSync' && evt.data.type !== 'chartSync') return;
            // Relay to all iframes except the sender
            var iframes = document.querySelectorAll('iframe');
            for (var i = 0; i < iframes.length; i++) {
                try {
                    if (iframes[i].contentWindow !== evt.source) {
                        iframes[i].contentWindow.postMessage(evt.data, '*');
                    }
                } catch(e) {}
            }
        });
    })();
    </script>
    """, unsafe_allow_html=True)


def parse_svm_content(file_path):
    setup = {}
    # Intentar decodificar con diferentes codificaciones
    content = None

    with open(file_path, 'rb') as file_handle:
        file_bytes = file_handle.read()

    # Heurística para UTF-16 con BOM
    if file_bytes.startswith((b'\xff\xfe', b'\xfe\xff')):
        try:
            content = file_bytes.decode('utf-16')
        except Exception:
            pass

    if content is None:
        try:
            # Intentar UTF-8 primero (es más estricto que latin-1)
            content = file_bytes.decode('utf-8')
        except Exception:
            try:
                # Si falla UTF-8, podría ser latin-1 (común en rF2 por símbolos como °)
                content = file_bytes.decode('latin-1')
            except Exception:
                # Último recurso
                content = file_bytes.decode('utf-8', errors='ignore')

    current_section = None
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        # Detectar sección [SECCION]
        if '[' in line and ']' in line:
            # Ignorar si es un comentario que no parece sección
            if line.startswith('//') and '[' not in line[0:5]: # Heurística simple
                pass
            else:
                try:
                    start = line.index('[') + 1
                    end = line.index(']')
                    current_section = line[start:end].strip()
                    if current_section not in setup:
                        setup[current_section] = {}
                    continue
                except ValueError:
                    continue

        # Detectar parámetros k=v
        if '=' in line and current_section:
            # Limpiar posible comentario al inicio (rFactor2 comenta valores por defecto)
            clean_line = line
            if clean_line.startswith('//'):
                clean_line = clean_line[2:].strip()

            if '=' in clean_line:
                k, v = clean_line.split('=', 1)
                key = k.strip()
                # Si ya existe (p.ej. uno real y uno comentado), preferimos el real (no comentado)
                if key not in setup[current_section] or not line.startswith('//'):
                    setup[current_section][key] = v.strip()
    return setup

def cleanup_server_data():
    """Llama al endpoint de limpieza del backend."""
    try:
        requests.post(f"{API_BASE_URL}/cleanup", headers=_api_headers(), timeout=10)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Barra lateral
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Carga de Datos")

    _ensure_client_session_id()

    # Estado para controlar si hay una sesión activa y analizada
    is_analyzed = 'ai_analysis_data' in st.session_state

    # Inicializar parámetros fijos si no existen
    if 'fixed_params' not in st.session_state:
        st.session_state['fixed_params'] = load_fixed_params()

    # Para controlar si ya se han cargado archivos pero no analizado
    if 'selected_session_name' not in st.session_state:
        st.session_state['selected_session_name'] = None

    tele_path = None
    svm_path = None
    tele_name = None
    svm_name = None

    # Lógica de visualización de la barra lateral
    if not st.session_state['selected_session_name']:
        # ESTADO 1: Subida chunked directa browser -> API (16 MB por petición)
        st.caption("Subida robusta para Cloudflare: el navegador envía chunks de 16 MB a la API.")
        _render_chunked_uploader()

        available_sessions = _fetch_backend_sessions()
        if available_sessions:
            # Cargar automáticamente la sesión más reciente para evitar pasos manuales
            # y mantener el flujo: subir archivos -> ver telemetría.
            selected_entry = available_sessions[0]
            selected_id = selected_entry["id"]
            tele_path_state = st.session_state.get('telemetry_temp_path')
            svm_path_state = st.session_state.get('svm_temp_path')
            local_files_ready = bool(
                tele_path_state
                and svm_path_state
                and os.path.exists(tele_path_state)
                and os.path.exists(svm_path_state)
            )
            if st.session_state.get('selected_session_id') != selected_id or not local_files_ready:
                _cleanup_temp_session_files()
                st.session_state['selected_session_id'] = selected_id
                st.session_state['selected_session_name'] = selected_entry.get("display_name", selected_id)
                try:
                    st.session_state.update(_load_session_locally(selected_entry))
                    st.success("Sesión cargada automáticamente")
                except Exception as e:
                    st.error(f"No se pudo cargar la sesión localmente: {e}")
        else:
            st.info("No hay sesiones completas en el backend todavía. Sube .mat/.csv + .svm.")
    else:
        # ESTADO 2 o 3: Sesión cargada (con o sin análisis)
        st.info(f"Sesión activa: **{st.session_state['selected_session_name']}**")

        # Botón Nueva sesión (siempre presente si hay algo cargado)
        if st.button("🆕 Nueva sesión", use_container_width=True):
            # 1. Limpiar datos en servidor
            cleanup_server_data()

            # 2. Limpiar estado y recargar
            _cleanup_temp_session_files()
            st.session_state.clear()
            st.rerun()

    # Recuperar datos de la sesión si existen
    if st.session_state.get('selected_session_name'):
        tele_path = st.session_state.get('telemetry_temp_path')
        svm_path = st.session_state.get('svm_temp_path')
        tele_name = st.session_state.get('tele_name')
        svm_name = st.session_state.get('svm_name')

        # Recuperación defensiva: en entornos productivos el directorio temporal
        # puede faltar tras un rerun. Solo se ejecuta si los archivos realmente faltan,
        # evitando llamadas al backend en cada rerun cuando los archivos ya están presentes.
        _files_ok = bool(
            tele_path and os.path.exists(tele_path)
            and svm_path and os.path.exists(svm_path)
        )
        if not _files_ok:
            # Files missing (e.g. after page reload) — re-download but DON'T nuke lap cache
            # The cache key uses filename (not path) so it will still hit after re-download
            selected_id = st.session_state.get('selected_session_id')
            if selected_id:
                try:
                    match = next((s for s in _fetch_backend_sessions() if s.get("id") == selected_id), None)
                    if match:
                        st.session_state.update(_load_session_locally(match))
                        tele_path = st.session_state.get('telemetry_temp_path')
                        svm_path = st.session_state.get('svm_temp_path')
                        tele_name = st.session_state.get('tele_name')
                        svm_name = st.session_state.get('svm_name')
                except Exception as e:
                    st.warning(f"No se pudo recuperar la sesión desde el backend: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Contenido principal
# ─────────────────────────────────────────────────────────────────────────────
if tele_path and svm_path:
    file_size_mb = 0.0
    try:
        file_size_mb = os.path.getsize(tele_path) / (1024 * 1024)
    except Exception:
        file_size_mb = 0.0

    skip_mat_preview = tele_name.endswith('.mat') and file_size_mb > MAT_PREVIEW_MAX_MB
    if skip_mat_preview:
        st.warning(
            f"Archivo .mat grande ({file_size_mb:.1f} MB). "
            "Se omite la vista de telemetría para evitar reinicios del servidor. "
            "Puedes ejecutar el análisis IA igualmente."
        )

    if tele_name.endswith('.mat') and not skip_mat_preview:
        # 1. Cargar DataFrame (cacheado)
        df_local = get_mat_dataframe(tele_path)

        if df_local is not None and 'Lap_Number' in df_local.columns:
            laps = sorted([int(l) for l in df_local['Lap_Number'].unique() if l > 0])

            if laps:
                # 2. Pre-generar gráficos (cacheado en session_state por nombre+vueltas)
                # Use filename (not full path) as cache key to survive temp dir changes
                _cache_key = (os.path.basename(tele_path), tuple(laps))
                if st.session_state.get('_lap_cache_key') != _cache_key:
                    with st.spinner("Procesando telemetría..."):
                        st.session_state['_lap_cache'] = precompute_all_laps(df_local, tuple(laps))
                        st.session_state['_lap_cache_key'] = _cache_key
                all_lap_figs = st.session_state['_lap_cache']

                # Detectar vuelta rápida
                fastest_lap = None
                lap_times = {}
                # Preferir Last_Laptime (más preciso) sobre Session_Elapsed_Time
                has_last_laptime = 'Last_Laptime' in df_local.columns
                for l in laps:
                    lap_df_tmp = df_local[df_local['Lap_Number'] == l]
                    if not lap_df_tmp.empty:
                        if has_last_laptime:
                            lt = lap_df_tmp['Last_Laptime'].iloc[-1]
                            if lt > 0:
                                lap_times[l] = float(lt)
                                continue
                        # Fallback a Session_Elapsed_Time
                        if 'Session_Elapsed_Time' in df_local.columns:
                            lap_times[l] = float(lap_df_tmp['Session_Elapsed_Time'].max() - lap_df_tmp['Session_Elapsed_Time'].min())
                if lap_times:
                    fastest_lap = min(lap_times, key=lap_times.get)

                main_tab_tele, main_tab_setup, main_tab_ai, main_tab_track = st.tabs(
                    ["📊 Telemetría", "🔧 Setup", "🤖 Análisis AI", "🏁 Pista 3D"]
                )

                with main_tab_tele:
                    # Track selector (inline, right here in Telemetría)
                    _all_tracks = _fetch_track_list()
                    if _all_tracks:
                        _track_names = ["(ninguna)"] + [t.get("name", "?") for t in _all_tracks]
                        # Restore selection from query param (survives page reload)
                        _saved_track = st.query_params.get("track")
                        _current_track = st.session_state.get("loaded_track_json")
                        _current_name = _current_track.get("name") if _current_track else (_saved_track or "(ninguna)")
                        _default_idx = _track_names.index(_current_name) if _current_name in _track_names else 0
                        _selected = st.selectbox(
                            "🏁 Pista 3D",
                            _track_names,
                            index=_default_idx,
                            key="inline_track_selector",
                        )
                        if _selected != "(ninguna)":
                            _entry = next((t for t in _all_tracks if t.get("name") == _selected), None)
                            if _entry:
                                _tj = _download_track_json(_entry)
                                if _tj and _tj.get("points"):
                                    st.session_state["loaded_track_json"] = _tj
                                    st.query_params["track"] = _selected
                        elif _selected == "(ninguna)" and "track" in st.query_params:
                            del st.query_params["track"]

                    # Formatear tiempos de vuelta
                    def _fmt_lap_time(seconds):
                        m = int(seconds // 60)
                        s = seconds % 60
                        tenths = int(round((s % 1) * 10))
                        return f"{m}:{int(s):02}:{tenths}00"

                    lap_options = []
                    for l in laps:
                        t_str = ""
                        if l in lap_times:
                            t_val = _fmt_lap_time(lap_times[l])
                            t_str = f" ({t_val})"
                        lap_options.append(f"V{l}{t_str}")

                    # Build cockpit data for the 3D PIP (embedded in the chart component)
                    _track_j = st.session_state.get("loaded_track_json")
                    _cockpit_data = None
                    if _track_j and _track_j.get("points"):
                        _cockpit_lap = fastest_lap if fastest_lap else laps[0]
                        _cockpit_lap_df = df_local[df_local['Lap_Number'] == _cockpit_lap].copy()
                        _cockpit_data = _build_cockpit_data(_cockpit_lap_df)

                    plot_all_laps_interactive(
                        all_lap_figs, laps, lap_options, fastest_lap,
                        track_json=_track_j, cockpit_data=_cockpit_data
                    )

                with main_tab_setup:
                    st.header("Configuración del Coche (.svm)")

                    # Inicializar estado temporal de edición si no existe
                    if 'temp_fixed_params' not in st.session_state:
                        st.session_state['temp_fixed_params'] = st.session_state['fixed_params'].copy()

                    def _clean_svm_value(val):
                        val_str = str(val)
                        if "//" in val_str:
                            parts = val_str.split("//", 1)
                            if len(parts) > 1:
                                return parts[1].strip()
                        return val_str.strip()

                    setup_data = parse_svm_content(svm_path)
                    # Cargar mapping para nombres amigables
                    _mapping_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "core", "param_mapping.json")
                    _mapping = {"sections": {}, "parameters": {}}
                    if os.path.exists(_mapping_path):
                        try:
                            with open(_mapping_path, 'r', encoding='utf-8') as _mf:
                                _mapping = _json.load(_mf)
                        except Exception:
                            pass

                    # Formulario para agrupar cambios y evitar recargas por cada clic
                    with st.form("setup_fixed_params_form", border=False):
                        # Botón para guardar cambios arriba para accesibilidad
                        save_col1, save_col2 = st.columns([1.5, 3.5])
                        with save_col1:
                            submitted = st.form_submit_button("💾 Guardar parámetros fijados", use_container_width=True)
                        with save_col2:
                            st.info("Selecciona los parámetros que quieres fijar para que la IA sepa que no se tienen que modificar y pulsa el botón para guardar todos los cambios.", icon="ℹ️")

                        for section, params in setup_data.items():
                            if section.upper() in ("LEFTFENDER", "RIGHTFENDER"):
                                continue
                            friendly_section = _mapping.get("sections", {}).get(section, section)
                            with st.expander(f"🔩 {friendly_section}"):
                                rows = []
                                for k, v in params.items():
                                    if k.startswith("Gear") and "Setting" in k:
                                        continue
                                    friendly_param = _mapping.get("parameters", {}).get(k, k)
                                    if k in ("VehicleClassSetting", "UpgradeSetting"):
                                        continue

                                    if friendly_param.startswith("Ajuste de Chasis") or k.startswith("ChassisAdj"):
                                        continue

                                    clean_v = _clean_svm_value(v)
                                    if not clean_v:
                                        continue

                                    is_fixed = k in st.session_state['temp_fixed_params']
                                    rows.append({
                                        "Fijar": is_fixed,
                                        "Parámetro": friendly_param,
                                        "Valor": clean_v,
                                        "_internal_key": k
                                    })

                                if rows:
                                    # Guardar filas para referencia al procesar el formulario
                                    st.session_state[f"rows_{section}"] = rows
                                    df_setup = pd.DataFrame(rows)
                                    # editor sin on_change (se procesa al pulsar el botón del form)
                                    st.data_editor(
                                        df_setup,
                                        column_config={
                                            "Fijar": st.column_config.CheckboxColumn(
                                                "Fijar",
                                                help="Si se marca, la IA no cambiará este valor pero lo usará para el análisis",
                                                default=False,
                                            ),
                                            "Parámetro": st.column_config.TextColumn(disabled=True),
                                            "Valor": st.column_config.TextColumn(disabled=True),
                                            "_internal_key": None
                                        },
                                        disabled=["Parámetro", "Valor"],
                                        hide_index=True,
                                        key=f"editor_{section}",
                                    )

                        if submitted:
                            # Procesar todos los editores al enviar el formulario
                            new_fixed = st.session_state['fixed_params'].copy()

                            # Recorrer todas las secciones cargadas
                            for section in setup_data.keys():
                                editor_key = f"editor_{section}"
                                rows_key = f"rows_{section}"
                                if editor_key in st.session_state and rows_key in st.session_state:
                                    changes = st.session_state[editor_key]
                                    rows = st.session_state[rows_key]
                                    edited_rows = changes.get("edited_rows", {})

                                    # Actualizar basándose en los cambios manuales en el editor
                                    for idx_str, change in edited_rows.items():
                                        idx = int(idx_str)
                                        if idx < len(rows):
                                            internal_key = rows[idx]["_internal_key"]
                                            if "Fijar" in change:
                                                if change["Fijar"]:
                                                    new_fixed.add(internal_key)
                                                else:
                                                    new_fixed.discard(internal_key)

                            st.session_state['fixed_params'] = new_fixed
                            st.session_state['temp_fixed_params'] = new_fixed.copy()
                            if save_fixed_params(new_fixed):
                                st.success("¡Parámetros guardados correctamente!")
                                st.rerun()

                        # Si no hay filas en ninguna sección, mostrar mensaje
                        has_any_rows = any(len(params) > 0 for section, params in setup_data.items() if section.upper() not in ("LEFTFENDER", "RIGHTFENDER"))
                        if not has_any_rows:
                            st.caption("No hay parámetros configurados disponibles.")

                with main_tab_ai:
                    st.header("Análisis de Ingeniero Virtual")

                    provider_options = {
                        "Ollama (local/remoto)": "ollama",
                        "Jimmy API": "jimmy",
                    }
                    provider_label = st.selectbox("Proveedor LLM", list(provider_options.keys()))
                    sel_provider = provider_options[provider_label]

                    sel_model = None
                    sel_ollama_url = ""
                    sel_ollama_api_key = ""

                    if sel_provider == "ollama":
                        sel_ollama_url = st.text_input(
                            "URL de Ollama",
                            value="https://ollama.com",
                            help=(
                                "URL del servidor Ollama. Por defecto apunta a Ollama Cloud. "
                                "Bórrala o pon http://localhost:11434 para usar el Ollama local del backend. "
                                "Para un túnel/ngrok pon la URL completa (ej: https://xxx.ngrok.io)."
                            ),
                        )
                        sel_ollama_api_key = st.text_input(
                            "API Key de Ollama (opcional)",
                            value="",
                            type="password",
                            help="Necesaria para Ollama Cloud (obtén tu clave en https://ollama.com/settings/keys).",
                        )

                        # Parámetros para la llamada a /models
                        _models_params = {}
                        if sel_ollama_url.strip():
                            _models_params["ollama_base_url"] = sel_ollama_url.strip()
                        if sel_ollama_api_key.strip():
                            _models_params["ollama_api_key"] = sel_ollama_api_key.strip()

                        try:
                            models_resp = requests.get(
                                f"{API_BASE_URL}/models",
                                headers=_api_headers(),
                                params=_models_params,
                                timeout=5,
                            )
                            available_models = (
                                models_resp.json().get("models", [])
                                if models_resp.status_code == 200 else []
                            )
                        except Exception:
                            available_models = []

                        if available_models:
                            sel_model = st.selectbox("Modelo LLM", available_models)
                        else:
                            st.warning("No se pudieron obtener modelos de Ollama. Se usará el modelo por defecto del backend.")
                    else:
                        sel_model = "llama3.1-8B"
                        st.caption("Modelo Jimmy seleccionado: llama3.1-8B")

                    analyze_button = st.button("🚀 Iniciar Análisis con IA")

                    if analyze_button:
                        # Evita mostrar resultados antiguos si el nuevo análisis falla.
                        st.session_state.pop('ai_analysis_data', None)
                        st.session_state.pop('ai_model', None)
                        with st.spinner("Analizando con IA…"):
                            data_form = {}
                            data_form["provider"] = sel_provider
                            if sel_model:
                                data_form["model"] = sel_model
                            if sel_provider == "ollama" and sel_ollama_url.strip():
                                data_form["ollama_base_url"] = sel_ollama_url.strip()
                            if sel_provider == "ollama" and sel_ollama_api_key.strip():
                                data_form["ollama_api_key"] = sel_ollama_api_key.strip()

                            # Enviar lista de parámetros fijados
                            if 'fixed_params' in st.session_state and st.session_state['fixed_params']:
                                data_form["fixed_params"] = _json.dumps(list(st.session_state['fixed_params']))

                            try:
                                # Re-analiza siempre desde archivos locales para permitir cambiar proveedor/modelo
                                # sin depender de sesiones ya consumidas en el backend.
                                response = _post_analysis_with_local_files(data_form)
                            except FileNotFoundError:
                                response = _post_analysis_for_session(
                                    st.session_state.get("selected_session_id", st.session_state['selected_session_name']),
                                    data_form,
                                )
                            if response.status_code == 200:
                                data = response.json()
                                # Guardar datos en session_state para re-análisis
                                st.session_state['ai_analysis_data'] = data
                                st.session_state['ai_telemetry_summary'] = data.get('telemetry_summary_sent', '')
                                st.session_state['ai_circuit_name'] = tele_name.split('-')[-2].strip() if '-' in tele_name else "Desconocido"
                                backend_provider = data.get("llm_provider") or sel_provider
                                backend_model = data.get("llm_model") or sel_model or "default"
                                st.session_state['ai_model'] = f"{backend_provider} / {backend_model}"
                                # Parsear setup_data del .svm para re-análisis
                                st.session_state['ai_setup_data'] = parse_svm_content(svm_path)
                            else:
                                try:
                                    error_detail = response.json().get("detail")
                                except Exception:
                                    error_detail = None
                                if error_detail:
                                    st.error(f"Error en el análisis ({response.status_code}): {error_detail}")
                                else:
                                    st.error(f"Error en el análisis ({response.status_code}).")

                    # Mostrar resultados (persistentes en session_state)
                    if 'ai_analysis_data' in st.session_state:
                        data = st.session_state['ai_analysis_data']

                        llm_provider_used = data.get("llm_provider", "desconocido")
                        llm_model_used = data.get("llm_model", "desconocido")
                        st.caption(f"Proveedor/modelo usado en backend: {llm_provider_used} / {llm_model_used}")

                        # ── Análisis del Ingeniero de Conducción ──
                        st.subheader("🏁 Análisis del Ingeniero de Conducción")
                        st.info(data['driving_analysis'])

                        # ── Setup Completo Recomendado ──
                        if data.get('full_setup') and data['full_setup'].get('sections'):
                            st.subheader("⚙️ Setup Completo Recomendado por los ingenieros")
                            for sec_idx, section in enumerate(data['full_setup']['sections']):
                                s_name = section.get('name', 'Sección')
                                s_key = section.get('section_key', '')
                                s_items = section.get('items', [])
                                if not s_items:
                                    continue
                                changed_items = [it for it in s_items if str(it.get('current', '')) != str(it.get('new', ''))]
                                if not changed_items:
                                    continue
                                with st.expander(f"🔩 {s_name} ({len(changed_items)} cambios)", expanded=True):
                                    if changed_items:
                                        rows = []
                                        for it in changed_items:
                                            param_name = it.get('parameter', '')
                                            if it.get('reanalyzed'):
                                                param_name = f"🚀 {param_name}"
                                            rows.append({
                                                "Parámetro": param_name,
                                                "Actual": it.get('current', ''),
                                                "Recomendado": it.get('new', ''),
                                                "Motivo": it.get('reason', '')
                                            })
                                        df_ai = pd.DataFrame(rows)
                                        st.table(df_ai.set_index("Parámetro"))

                        # ── Razonamientos y Feedback de los Agentes ──
                        setup_agent_reports = data.get('setup_agent_reports', [])
                        agent_reports = setup_agent_reports or data.get('agent_reports', [])
                        chief_reasoning = data.get('chief_reasoning', '')
                        if agent_reports or chief_reasoning:
                            st.divider()
                            st.subheader("💬 Razonamientos de los Agentes IA")
                            st.info(
                                "ℹ️ Esta sección muestra el **razonamiento interno** de cada agente. "
                                "No es la tabla de cambios del setup — es la explicación técnica "
                                "detrás de las recomendaciones.",
                                icon="🧠"
                            )

                            # Ingeniero Jefe
                            if chief_reasoning:
                                with st.expander("🎯 Ingeniero Jefe — Estrategia global", expanded=True):
                                    st.markdown(f"> {chief_reasoning.replace(chr(10), chr(10) + '> ')}")

                            # Agentes especialistas: only show sections with actual content
                            meaningful_reports = [
                                r for r in (agent_reports or [])
                                if r.get('summary', '').strip() or r.get('items', [])
                            ]
                            if meaningful_reports:
                                for report in meaningful_reports:
                                    sec_friendly = report.get('friendly_name') or report.get('name', '')
                                    sec_summary = report.get('summary', '').strip()
                                    sec_items = report.get('items', [])
                                    label = f"📝 {sec_friendly}"
                                    with st.expander(label, expanded=False):
                                        if sec_summary:
                                            st.markdown(f"> {sec_summary.replace(chr(10), chr(10) + '> ')}")
                                        if sec_items:
                                            st.markdown("---")
                                            for it in sec_items:
                                                param = it.get('parameter', '')
                                                new_val = it.get('new_value', '')
                                                reason = it.get('reason', '')
                                                st.markdown(
                                                    f"**{param}** → `{new_val}`\n\n"
                                                    f"> _{reason}_\n"
                                                )

                with main_tab_track:
                    _render_track_selection_ui(df_local)
                    _render_track_upload_dropzone()
            else:
                st.warning("No se encontraron vueltas completas.")
        else:
            st.error("No se encontró canal 'Lap_Number' en el .mat")
    else:
        if skip_mat_preview:
            st.info("Vista detallada desactivada por tamaño del .mat en este servidor. Usa el análisis IA.")
        else:
            st.info("La visualización detallada actualmente solo soporta archivos .mat.")
        if st.button("Analizar con IA"):
            with st.spinner("Analizando con IA…"):
                try:
                    response = _post_analysis_with_local_files({})
                except FileNotFoundError:
                    response = _post_analysis_for_session(
                        st.session_state.get("selected_session_id", st.session_state['selected_session_name']),
                        {},
                    )
                if response.status_code == 200:
                    data = response.json()
                    st.success("Análisis completado")
                    st.write(data['driving_analysis'])
                else:
                    try:
                        error_detail = response.json().get("detail")
                    except Exception:
                        error_detail = None
                    if error_detail:
                        st.error(f"Error en el análisis ({response.status_code}): {error_detail}")
                    else:
                        st.error(f"Error en el análisis ({response.status_code}).")
else:
    st.info("👋 Sube tus archivos o elige una sesión anterior en la barra lateral para comenzar.")
