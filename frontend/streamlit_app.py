import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import scipy.io
import io
import os
import json as _json

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
        max_dist = max(lap_distances.values()) if lap_distances else 0
        complete_laps = [l for l, d in lap_distances.items() if d >= max_dist * 1.0]
    else:
        lap_samples = {lap: len(df[df[lap_col] == lap]) for lap in laps}
        max_samples = max(lap_samples.values()) if lap_samples else 0
        complete_laps = [l for l, s in lap_samples.items() if s >= max_samples * 1.0]

    if not complete_laps:
        complete_laps = laps

    # Filtrar por duración anómala
    time_col = 'Session_Elapsed_Time' if 'Session_Elapsed_Time' in df.columns else None
    if time_col and len(complete_laps) > 2:
        lap_durations = {}
        for lap in complete_laps:
            t = df.loc[df[lap_col] == lap, time_col].dropna()
            lap_durations[lap] = (t.max() - t.min()) if not t.empty else 0
        middle_laps = complete_laps[1:-1] if len(complete_laps) > 2 else complete_laps
        median_dur = np.median([lap_durations[l] for l in middle_laps if lap_durations[l] > 0])
        if median_dur > 0:
            complete_laps = [l for l in complete_laps if lap_durations[l] <= median_dur * 1.10]

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
                Plotly.react(mapChart, [
                    {{ x: lapData.map.lon, y: lapData.map.lat, mode: 'lines', line: {{ color: '#666', width: 2 }}, hoverinfo: 'skip' }},
                    {{ x: [lapData.map.lon[0]], y: [lapData.map.lat[0]], mode: 'markers', marker: {{ color: 'red', size: 12, symbol: 'x' }}, name: 'Coche' }}
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
                Plotly.restyle(mapChart, {{
                    x: [[lapData.map.lon[idx]]],
                    y: [[lapData.map.lat[idx]]]
                }}, [1]);
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
            current_section = line[line.index('[') + 1:line.index(']')]
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
                    setup_data = parse_svm_content(svm_to_send)
                    # Cargar mapping para nombres amigables
                    _mapping_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "core", "param_mapping.json")
                    _mapping = {"sections": {}, "parameters": {}}
                    if os.path.exists(_mapping_path):
                        try:
                            with open(_mapping_path, 'r', encoding='utf-8') as _mf:
                                _mapping = _json.load(_mf)
                        except Exception:
                            pass

                    def _clean_svm_value(val):
                        val_str = str(val)
                        if "//" in val_str:
                            parts = val_str.split("//", 1)
                            if len(parts) > 1:
                                return parts[1].strip()
                        return val_str.strip()

                    for section, params in setup_data.items():
                        if section.upper() in ("BASIC", "LEFTFENDER", "RIGHTFENDER"):
                            continue
                        friendly_section = _mapping.get("sections", {}).get(section, section)
                        with st.expander(f"🔩 {friendly_section}"):
                            rows = []
                            for k, v in params.items():
                                if k.startswith("Gear") and "Setting" in k:
                                    continue
                                friendly_param = _mapping.get("parameters", {}).get(k, k)
                                rows.append({
                                    "Parámetro": friendly_param,
                                    "Valor": _clean_svm_value(v)
                                })
                            if rows:
                                df_setup = pd.DataFrame(rows)
                                st.table(df_setup.set_index("Parámetro"))
                            else:
                                st.caption("No hay parámetros configurados en esta sección.")

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
                            data_form = {}
                            if sel_model:
                                data_form["model"] = sel_model
                            response = requests.post(
                                "http://localhost:8000/analyze",
                                files=files, data=data_form
                            )
                            if response.status_code == 200:
                                data = response.json()
                                # Guardar datos en session_state para re-análisis
                                st.session_state['ai_analysis_data'] = data
                                st.session_state['ai_telemetry_summary'] = data.get('telemetry_summary_sent', '')
                                st.session_state['ai_circuit_name'] = tele_name.split('-')[-2].strip() if '-' in tele_name else "Desconocido"
                                st.session_state['ai_model'] = sel_model
                                # Parsear setup_data del .svm para re-análisis
                                st.session_state['ai_setup_data'] = parse_svm_content(svm_to_send)
                            else:
                                st.error("Error en el análisis.")

                    # Mostrar resultados (persistentes en session_state)
                    if 'ai_analysis_data' in st.session_state:
                        data = st.session_state['ai_analysis_data']

                        # ── Análisis del Ingeniero de Conducción ──
                        st.subheader("🏁 Análisis del Ingeniero de Conducción")
                        st.info(data['driving_analysis'])

                        # ── Razonamiento del Ingeniero Jefe ──
                        if data.get('chief_reasoning'):
                            st.subheader("🧠 Razonamiento del Ingeniero Jefe")
                            st.warning(data['chief_reasoning'])

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
                                with st.expander(f"🔩 {s_name} ({len(changed_items)} cambios)", expanded=bool(changed_items)):
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
                                    else:
                                        st.caption("No se recomiendan cambios en esta sección.")

                                    # Botón de re-consulta al ingeniero jefe
                                    if s_key and st.button(f"🔄 Re-consultar al Ingeniero Jefe", key=f"reanalyze_{s_key}_{sec_idx}"):
                                        with st.spinner(f"El Ingeniero Jefe está re-analizando {s_name}…"):
                                            try:
                                                reanalyze_resp = requests.post(
                                                    "http://localhost:8000/reanalyze_section",
                                                    json={
                                                        "section_key": s_key,
                                                        "telemetry_summary": st.session_state.get('ai_telemetry_summary', ''),
                                                        "setup_data": st.session_state.get('ai_setup_data', {}),
                                                        "previous_full_setup": data.get('full_setup', {}),
                                                        "circuit_name": st.session_state.get('ai_circuit_name', 'Desconocido'),
                                                        "model": st.session_state.get('ai_model')
                                                    },
                                                    timeout=120
                                                )
                                                if reanalyze_resp.status_code == 200:
                                                    reanalyze_data = reanalyze_resp.json()
                                                    # Merge inteligente: solo actualizar parámetros que cambian
                                                    updated_secs = reanalyze_data.get('updated_sections', [])
                                                    current_sections = data['full_setup']['sections']
                                                    for upd_sec in updated_secs:
                                                        upd_key = upd_sec.get('section_key', '')
                                                        # Construir mapa de nuevos items por param_key
                                                        new_items_map = {}
                                                        for it in upd_sec.get('items', []):
                                                            pk = it.get('param_key', it.get('parameter', ''))
                                                            new_items_map[pk] = it
                                                        for i, cs in enumerate(current_sections):
                                                            if cs.get('section_key', '') == upd_key:
                                                                # Merge: mantener items existentes, actualizar solo los que cambian
                                                                merged_items = []
                                                                for existing_it in cs.get('items', []):
                                                                    epk = existing_it.get('param_key', existing_it.get('parameter', ''))
                                                                    if epk in new_items_map:
                                                                        new_it = new_items_map[epk]
                                                                        # Marcar como re-consultado con 🚀
                                                                        new_it['reanalyzed'] = True
                                                                        merged_items.append(new_it)
                                                                        del new_items_map[epk]
                                                                    else:
                                                                        # Mantener el item existente sin cambios
                                                                        merged_items.append(existing_it)
                                                                # Añadir items nuevos que no existían antes
                                                                for remaining in new_items_map.values():
                                                                    remaining['reanalyzed'] = True
                                                                    merged_items.append(remaining)
                                                                cs['items'] = merged_items
                                                                break
                                                    st.session_state['ai_analysis_data'] = data
                                                    if reanalyze_data.get('chief_reasoning'):
                                                        st.success(f"**Nuevo razonamiento del Ingeniero Jefe:** {reanalyze_data['chief_reasoning']}")
                                                    st.rerun()
                                                else:
                                                    st.error("Error en el re-análisis.")
                                            except Exception as e:
                                                st.error(f"Error: {e}")
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
