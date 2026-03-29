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
import uuid
import re

FIXED_PARAMS_FILE = "app/core/fixed_params.json"
API_BASE_URL = os.environ.get("RF2_API_URL", "http://localhost:8000")
BROWSER_API_BASE_URL = os.environ.get("RF2_BROWSER_API_BASE_URL", "/api")
UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024
ANALYSIS_REQUEST_TIMEOUT = (10, 1800)
TEMP_UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "rfactor2_engineer_uploads")
CLIENT_SESSION_COOKIE = "rf2_session_id"
CLIENT_SESSION_QUERY_PARAM = "rf2sid"
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
MAT_PREVIEW_MAX_MB = int(os.environ.get("RF2_FRONTEND_MAX_PREVIEW_MAT_MB", "120"))


def _ensure_temp_upload_root():
    os.makedirs(TEMP_UPLOAD_ROOT, exist_ok=True)
    return TEMP_UPLOAD_ROOT


def _cleanup_temp_session_files():
    temp_dir = st.session_state.pop('temp_upload_dir', None)
    for key in ('telemetry_temp_path', 'svm_temp_path', 'tele_name', 'svm_name', 'selected_session_id'):
        st.session_state.pop(key, None)

    if temp_dir and os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


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
        session_dir = tempfile.mkdtemp(prefix=f"rf2-session-{uuid.uuid4()}-", dir=temp_root)

        tele_name = session_entry["telemetry"]
        svm_name = session_entry["svm"]
        tele_path = os.path.join(session_dir, tele_name)
        svm_path = os.path.join(session_dir, svm_name)

        session_id = session_entry["id"]
        _download_session_file(f"{API_BASE_URL}/sessions/{session_id}/file/{tele_name}", tele_path)
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

st.set_page_config(page_title="rFactor2 Engineer", layout="wide")

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


@st.cache_resource(show_spinner=False)
def precompute_all_laps(df, laps):
    """
    Pre-genera los datos de todas las vueltas y los devuelve.
    Se cachea como recurso para que no se re-calcule al interactuar con la UI.
    """
    all_data = {}
    progress_container = st.empty()
    total_laps = len(laps)
    for i, lap in enumerate(laps):
        lap_df = df[df['Lap_Number'] == lap].copy()
        all_data[lap] = _build_lap_data(lap_df)
        with progress_container.container():
            st.progress((i + 1) / total_laps, text=f"Procesando Vuelta {lap} de {laps[-1]}...")

    progress_container.empty()
    return all_data


def plot_all_laps_interactive(all_lap_figs, laps, lap_options, fastest_lap):
    """Renderiza la telemetría interactiva de TODAS las vueltas en un solo componente HTML/JS.
    El cambio de vuelta se gestiona enteramente en el cliente (JavaScript), sin roundtrip al servidor."""
    if not all_lap_figs:
        st.warning("No hay datos de telemetría.")
        return

    import json
    # Convertir claves int a string para JSON
    all_data_json = json.dumps({str(k): v for k, v in all_lap_figs.items() if v})
    laps_json = json.dumps([int(l) for l in laps])
    lap_labels_json = json.dumps(lap_options)
    fastest_lap_js = int(fastest_lap) if fastest_lap else "null"

    total_height = 1300

    html_code = f"""
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
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
        #map-container {{ width: 100%; margin-bottom: 15px; border: 1px solid #333; }}
    </style>

    <div class="telemetry-container">
        <div class="lap-sidebar" id="lap-sidebar"></div>
        <div class="charts-area">
            <div id="map-container"></div>

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
        let currentLap = laps[0];
        let lapData = allLapData[String(currentLap)];

        const charts = [];
        let mapChart = null;
        let isDragging = false;
        let pendingX = null;
        let rafId = null;
        let lastX = 0;

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
            labels = [s.get("display_name", s["id"]) for s in available_sessions]
            selected_label = st.selectbox("Selecciona sesión subida", labels)

            if st.button("Cargar sesión"):
                selected_entry = next(
                    (s for s in available_sessions if s.get("display_name", s["id"]) == selected_label),
                    None,
                )
                if selected_entry is not None:
                    _cleanup_temp_session_files()
                    st.session_state['selected_session_id'] = selected_entry["id"]
                    st.session_state['selected_session_name'] = selected_entry.get("display_name", selected_entry["id"])
                    try:
                        st.session_state.update(_load_session_locally(selected_entry))
                        st.success("Sesión cargada correctamente")
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
        # puede faltar tras un rerun. Reintentar descarga local desde la sesión backend.
        if (
            (not tele_path or not os.path.exists(tele_path))
            or (not svm_path or not os.path.exists(svm_path))
        ):
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
                # 2. Pre-generar gráficos (cacheado como recurso)
                # La clave del cache es el hash del contenido del archivo y la lista de vueltas
                all_lap_figs = precompute_all_laps(df_local, tuple(laps))

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

                main_tab_tele, main_tab_setup, main_tab_ai = st.tabs(
                    ["📊 Telemetría", "🔧 Setup", "🤖 Análisis AI"]
                )

                with main_tab_tele:
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

                    plot_all_laps_interactive(all_lap_figs, laps, lap_options, fastest_lap)

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
                        "Ollama (local)": "ollama",
                        "Jimmy API": "jimmy",
                    }
                    provider_label = st.selectbox("Proveedor LLM", list(provider_options.keys()))
                    sel_provider = provider_options[provider_label]

                    sel_model = None
                    if sel_provider == "ollama":
                        try:
                            models_resp = requests.get(f"{API_BASE_URL}/models", headers=_api_headers(), timeout=2)
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
