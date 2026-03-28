import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import scipy.io
import io

st.set_page_config(page_title="rFactor2 Engineer", layout="wide")

st.title("🏎️ rFactor2 Engineer")
st.subheader("Análisis de Telemetría y Setup mediante IA")

# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def get_mat_dataframe(file_bytes):
    """Carga el .mat y devuelve un DataFrame ordenado por tiempo."""
    try:
        tele_io = io.BytesIO(file_bytes)
        mat = scipy.io.loadmat(tele_io, struct_as_record=False, squeeze_me=True)
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
        return df
    except Exception as e:
        st.error(f"Error procesando .mat: {e}")
        return None


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
    # O un salto atrás (>0).
    xs, ys = [], []
    for i in range(len(x_arr)):
        if i > 0:
            diff = x_arr[i] - x_arr[i-1]
            # Si hay un salto brusco hacia adelante (>200m) o CUALQUIER salto atrás
            # en la distancia de la vuelta, rompemos la línea.
            if x_col == 'Lap_Distance':
                if diff < -1.0 or diff > 200.0:
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
                if 'Pos' in col: ys = [v * 100 if v is not None else None for v in ys]
                if 'Height' in col: ys = [v * 1000 if v is not None else None for v in ys]
                
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
        data['map'] = {
            'lon': m_xs,
            'lat': m_ys,
            'dist': dist_arr
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


def plot_interactive_telemetry(lap_data):
    """Renderiza la telemetría interactiva usando un componente HTML/JS con Plotly.js."""
    if not lap_data:
        st.warning("No hay datos para esta vuelta.")
        return

    import json
    data_json = json.dumps(lap_data)
    
    # Altura total estimada para evitar scroll interno molesto
    # Mapa (200) + 3 gráficos por pestaña (~350 cada uno) + Tabs
    total_height = 1300 

    html_code = f"""
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <style>
        body {{ margin: 0; background: #111; }}
        .telemetry-container {{ background-color: #111; color: white; font-family: sans-serif; width: 100%; box-sizing: border-box; }}
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

    <script>
        const lapData = {data_json};
        const charts = []; // {{el, id, wrapper, canvas}}
        let mapChart = null;
        let isDragging = false;
        let pendingX = null;
        let rafId = null;
        let lastX = 0;

        // Tab switching - simple display toggle + resize visible charts
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
        if (lapData.map) {{
            const n = lapData.map.dist.length;
            mapDistIndices = Array.from({{length: n}}, (_, i) => i);
            mapDistIndices.sort((a, b) => lapData.map.dist[a] - lapData.map.dist[b]);
            mapDistSorted = mapDistIndices.map(i => lapData.map.dist[i]);
        }}

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
            margin: {{ l: 60, r: 20, t: 35, b: 40 }},
            xaxis: {{ title: "Distancia (m)", range: [0, lapData.max_dist], fixedrange: true, gridcolor: '#333' }},
            yaxis: {{ gridcolor: '#333', autorange: true, fixedrange: true }},
            showlegend: true,
            legend: {{ orientation: "h", y: 1.12, x: 1, xanchor: 'right' }},
            hovermode: false,
            dragmode: false
        }};

        // Map
        if (lapData.map) {{
            const mapTrace = {{
                x: lapData.map.lon, y: lapData.map.lat,
                mode: 'lines', line: {{ color: '#666', width: 2 }}, hoverinfo: 'skip'
            }};
            const posTrace = {{
                x: [lapData.map.lon[0]], y: [lapData.map.lat[0]],
                mode: 'markers', marker: {{ color: 'red', size: 12, symbol: 'x' }}, name: 'Coche'
            }};
            mapChart = document.getElementById('map-container');
            Plotly.newPlot(mapChart, [mapTrace, posTrace], {{
                template: "plotly_dark",
                paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
                height: 250,
                xaxis: {{ visible: false, fixedrange: true }},
                yaxis: {{ visible: false, scaleanchor: "x", scaleratio: 1, fixedrange: true }},
                margin: {{ l: 10, r: 10, t: 10, b: 10 }},
                showlegend: false, dragmode: false
            }}, {{ displayModeBar: false, staticPlot: true }});
        }}

        // Charts - use staticPlot:true for instant rendering, no WebGL issues
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

            // Drag events on the wrapper (canvas is pointer-events:none)
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

        // Wait for all plots then resize ALL (temporarily show hidden tabs)
        Promise.all(plotPromises).then(() => {{
            resizeAllCharts();
            // Also resize after a short delay to catch late iframe width changes
            setTimeout(resizeAllCharts, 100);
            setTimeout(resizeAllCharts, 500);
        }});

        // Use ResizeObserver to catch any container width changes (e.g. when switching laps)
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

        // Draw red line on canvas overlay - extremely fast, no Plotly calls
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
            // Draw red lines on canvas overlays (instant, no Plotly overhead)
            drawAllRedLines();

            // Update map marker
            if (mapChart && lapData.map && mapDistSorted) {{
                const idx = findClosestMapIdx(x);
                Plotly.restyle(mapChart, {{
                    x: [[lapData.map.lon[idx]]],
                    y: [[lapData.map.lat[idx]]]
                }}, [1]);
            }}
        }}
    </script>
    """
    import streamlit.components.v1 as components
    # Forzar que el iframe ocupe todo el ancho disponible
    st.markdown("""
    <style>
        iframe[title="streamlit_app.plot_interactive_telemetry"] { width: 100% !important; }
        .stHtml iframe, .element-container iframe { width: 100% !important; }
        div[data-testid="stIFrame"] iframe { width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)
    components.html(html_code, height=total_height, scrolling=False)


def parse_svm_content(file_bytes):
    setup = {}
    try:
        content = file_bytes.decode('utf-16')
    except Exception:
        content = file_bytes.decode('utf-8', errors='ignore')

    current_section = None
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('//'): continue
        if '[' in line and ']' in line:
            current_section = line[1:-1]
            setup[current_section] = {}
        elif '=' in line and current_section:
            k, v = line.split('=', 1)
            setup[current_section][k.strip()] = v.strip()
    return setup


# ─────────────────────────────────────────────────────────────────────────────
# Barra lateral
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Carga de Datos")
    data_source = st.radio("Fuente de datos", ["Subir archivos", "Sesiones anteriores"])

    tele_to_send = None
    svm_to_send = None
    tele_name = None
    svm_name = None

    if data_source == "Subir archivos":
        uploaded_files = st.file_uploader(
            "Sube archivos .mat y .svm", type=["mat", "svm", "csv"],
            accept_multiple_files=True
        )
        if uploaded_files:
            sessions = {}
            for f in uploaded_files:
                base_name = f.name.rsplit('.', 1)[0]
                ext = f.name.rsplit('.', 1)[1].lower()
                if base_name not in sessions:
                    sessions[base_name] = {}
                sessions[base_name][ext] = f

            valid_sessions = [
                name for name, files in sessions.items()
                if ("mat" in files or "csv" in files) and "svm" in files
            ]
            if valid_sessions:
                selected_session = st.selectbox("Selecciona sesión subida", valid_sessions)
                ext_found = "mat" if "mat" in sessions[selected_session] else "csv"
                tele_obj = sessions[selected_session][ext_found]
                svm_obj = sessions[selected_session]["svm"]
                tele_to_send = tele_obj.getvalue()
                svm_to_send = svm_obj.getvalue()
                tele_name = tele_obj.name
                svm_name = svm_obj.name
                st.success(f"Sesión '{selected_session}' cargada.")
    else:
        try:
            sessions_resp = requests.get("http://localhost:8000/sessions", timeout=5)
            if sessions_resp.status_code == 200:
                past_sessions = sessions_resp.json().get("sessions", [])
                if past_sessions:
                    session_options = {
                        f"{s['display_name']} ({s['id'][:8]})": s for s in past_sessions
                    }
                    selected_label = st.selectbox("Selecciona sesión guardada", list(session_options.keys()))
                    selected_s = session_options[selected_label]
                    sid = selected_s['id']
                    t_name = selected_s['telemetry']
                    s_name = selected_s['svm']
                    t_resp = requests.get(f"http://localhost:8000/sessions/{sid}/file/{t_name}")
                    s_resp = requests.get(f"http://localhost:8000/sessions/{sid}/file/{s_name}")
                    if t_resp.status_code == 200 and s_resp.status_code == 200:
                        tele_to_send = t_resp.content
                        svm_to_send = s_resp.content
                        tele_name = t_name
                        svm_name = s_name
                        st.success(f"Sesión '{selected_label}' cargada desde el servidor.")
                    else:
                        st.error("Error al descargar archivos de la sesión.")
                else:
                    st.info("No hay sesiones guardadas en el servidor.")
            else:
                st.error("Error al obtener sesiones del servidor.")
        except Exception as e:
            st.error(f"Error de conexión con el backend: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Contenido principal
# ─────────────────────────────────────────────────────────────────────────────
if tele_to_send and svm_to_send:
    if tele_name.endswith('.mat'):
        # 1. Cargar DataFrame (cacheado)
        df_local = get_mat_dataframe(tele_to_send)

        if df_local is not None and 'Lap_Number' in df_local.columns:
            laps = sorted([int(l) for l in df_local['Lap_Number'].unique() if l > 0])
            
            if laps:
                # 2. Pre-generar gráficos (cacheado como recurso)
                # La clave del cache es el hash del contenido del archivo y la lista de vueltas
                all_lap_figs = precompute_all_laps(df_local, tuple(laps))

                main_tab_tele, main_tab_setup, main_tab_ai = st.tabs(
                    ["📊 Telemetría", "🔧 Setup", "🤖 Análisis AI"]
                )

                with main_tab_tele:
                    st.caption(f"Selecciona una vuelta para ver los gráficos pre-cargados.")
                    
                    # Usar st.tabs para las vueltas garantiza que todos los gráficos se pinten en el DOM
                    # y el cambio entre ellos sea instantáneo (manejado por el navegador).
                    lap_tab_labels = [f"Vuelta {l}" for l in laps]
                    lap_tabs = st.tabs(lap_tab_labels)

                    for i, lap in enumerate(laps):
                        with lap_tabs[i]:
                            # Renderizar telemetría interactiva (JS)
                            plot_interactive_telemetry(all_lap_figs.get(lap))

                with main_tab_setup:
                    st.header("Configuración del Coche (.svm)")
                    setup_data = parse_svm_content(svm_to_send)
                    for section, params in setup_data.items():
                        with st.expander(f"Sección: {section}"):
                            st.table(pd.DataFrame(list(params.items()), columns=["Parámetro", "Valor"]))

                with main_tab_ai:
                    st.header("Análisis de Ingeniero Virtual")
                    try:
                        models_resp = requests.get("http://localhost:8000/models", timeout=2)
                        available_models = (
                            models_resp.json().get("models", [])
                            if models_resp.status_code == 200 else []
                        )
                    except Exception:
                        available_models = []

                    sel_model = st.selectbox("Modelo LLM", available_models) if available_models else None
                    analyze_button = st.button("🚀 Iniciar Análisis con IA")

                    if analyze_button:
                        with st.spinner("Analizando con IA…"):
                            files = {
                                "telemetry_file": (tele_name, tele_to_send),
                                "svm_file": (svm_name, svm_to_send),
                            }
                            data_form = {"model": sel_model} if sel_model else {}
                            response = requests.post(
                                "http://localhost:8000/analyze",
                                files=files, data=data_form
                            )
                            if response.status_code == 200:
                                data = response.json()
                                st.subheader("Resumen de Análisis")
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.info(data['driving_analysis'])
                                with col2:
                                    st.warning(data['setup_analysis'])
                                st.subheader("Mapa de Problemas")
                                track_fig = go.Figure()
                                track_fig.add_trace(go.Scatter(
                                    x=data['circuit_data']['x'],
                                    y=data['circuit_data']['y'],
                                    mode='lines', name='Circuito'
                                ))
                                st.plotly_chart(track_fig, use_container_width=True)
                            else:
                                st.error("Error en el análisis.")
            else:
                st.warning("No se encontraron vueltas completas.")
        else:
            st.error("No se encontró canal 'Lap_Number' en el .mat")
    else:
        st.info("La visualización detallada actualmente solo soporta archivos .mat.")
        if st.button("Analizar con IA"):
            with st.spinner("Analizando con IA…"):
                files = {
                    "telemetry_file": (tele_name, tele_to_send),
                    "svm_file": (svm_name, svm_to_send),
                }
                response = requests.post("http://localhost:8000/analyze", files=files)
                if response.status_code == 200:
                    data = response.json()
                    st.success("Análisis completado")
                    st.write(data['driving_analysis'])
                else:
                    st.error("Error en el análisis.")
else:
    st.info("👋 Sube tus archivos o elige una sesión anterior en la barra lateral para comenzar.")
