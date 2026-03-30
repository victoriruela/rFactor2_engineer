"""Embedded Plotly telemetry view renderer for Streamlit."""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components


def plot_all_laps_interactive(all_lap_figs, laps, lap_options, fastest_lap):
    """Render all laps in one HTML/JS component with client-side lap switching."""
    if not all_lap_figs:
        st.warning("No hay datos de telemetría.")
        return

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

            sidebar.querySelectorAll('.lap-btn').forEach(b => {{
                b.classList.toggle('active', parseInt(b.dataset.lap) === lap);
            }});

            if (lapData.map && mapChart) {{
                const mc = computeMapColors(lapData.map.brake || [], lapData.map.throttle || []);
                const ai = mc.reduce((a, c, i) => {{ if (c !== null) a.push(i); return a; }}, []);
                Plotly.react(mapChart, [
                    {{ x: lapData.map.lon, y: lapData.map.lat, mode: 'lines', line: {{ color: '#444', width: 1.5 }}, hoverinfo: 'skip' }},
                    {{ x: ai.map(i => lapData.map.raw_lon[i]), y: ai.map(i => lapData.map.raw_lat[i]), mode: 'markers', marker: {{ color: ai.map(i => mc[i]), size: 4, opacity: 0.9 }}, hoverinfo: 'skip' }},
                    {{ x: [lapData.map.raw_lon ? lapData.map.raw_lon[0] : lapData.map.lon[0]], y: [lapData.map.raw_lat ? lapData.map.raw_lat[0] : lapData.map.lat[0]], mode: 'markers', marker: {{ color: 'white', size: 12, symbol: 'x', line: {{ color: '#ff0', width: 2 }} }}, name: 'Coche' }}
                ], mapChart.layout, {{ displayModeBar: false, staticPlot: true }});
            }}

            rebuildMapIndex();

            const newMaxDist = lapData.max_dist;
            charts.forEach(c => {{
                const chData = lapData.channels[c.id];
                if (!chData) return;
                const traces = chData.map(ch => ({{ x: ch.x, y: ch.y, name: ch.name, mode: 'lines', line: {{ width: 1.5 }}, connectgaps: false }}));
                const newLayout = Object.assign({{}}, c.el.layout, {{ xaxis: Object.assign({{}}, c.el.layout.xaxis, {{ range: [0, newMaxDist] }}) }});
                Plotly.react(c.el, traces, newLayout, {{ displayModeBar: false, staticPlot: true }});
            }});

            drawAllRedLines();
        }}

        function showTab(tabId, tabEl) {{
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            tabEl.classList.add('active');
            requestAnimationFrame(() => {{
                const tab = document.getElementById(tabId);
                tab.querySelectorAll('.chart-wrapper > div:first-child').forEach(c => {{ if (c.data) Plotly.Plots.resize(c); }});
                drawAllRedLines();
            }});
        }}

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

        function computeMapColors(brake, throttle) {{
            return brake.map(function(b, i) {{
                var t = (throttle[i] || 0) / 100;
                var bn = (b || 0) / 100;
                var combined = Math.max(bn, t);
                if (combined < 0.05) return null;
                var total = bn + t;
                var bFrac = total > 0 ? bn / total : 0;
                var tFrac = 1 - bFrac;
                var targetR = Math.round(bFrac * 255);
                var targetB = Math.round(tFrac * 255);
                var r  = Math.round(255 + combined * (targetR - 255));
                var g  = Math.round(255 + combined * (0 - 255));
                var bl = Math.round(255 + combined * (targetB - 255));
                return 'rgb(' + r + ',' + g + ',' + bl + ')';
            }});
        }}

        if (lapData.map) {{
            const mapTrace = {{ x: lapData.map.lon, y: lapData.map.lat, mode: 'lines', line: {{ color: '#444', width: 1.5 }}, hoverinfo: 'skip' }};
            const mapColors = computeMapColors(lapData.map.brake || [], lapData.map.throttle || []);
            const activeIdx = mapColors.reduce(function(a, c, i) {{ if (c !== null) a.push(i); return a; }}, []);
            const colorTrace = {{
                x: activeIdx.map(function(i) {{ return lapData.map.raw_lon ? lapData.map.raw_lon[i] : lapData.map.lon[i]; }}),
                y: activeIdx.map(function(i) {{ return lapData.map.raw_lat ? lapData.map.raw_lat[i] : lapData.map.lat[i]; }}),
                mode: 'markers', marker: {{ color: activeIdx.map(function(i) {{ return mapColors[i]; }}), size: 4, opacity: 0.9 }}, hoverinfo: 'skip'
            }};
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

        const chartIds = ['speed', 'controls', 'steer', 'rpm', 'gear', 'susp_pos', 'ride_height', 'brake_temp', 'tyre_pres', 'aero'];
        const chartTitles = {{ speed: 'Velocidad', controls: 'Controles', steer: 'Dirección', rpm: 'RPM', gear: 'Marcha', susp_pos: 'Posición Suspensión', ride_height: 'Altura al Suelo', brake_temp: 'Temp. Frenos', tyre_pres: 'Presión Neumáticos', aero: 'Aerodinámica' }};

        const plotPromises = [];
        chartIds.forEach(id => {{
            const container = document.getElementById('chart-' + id);
            const wrapper = document.getElementById('wrap-' + id);
            if (!container || !wrapper || !lapData.channels[id]) return;

            const canvas = wrapper.querySelector('canvas.red-line');
            const traces = lapData.channels[id].map(ch => ({{ x: ch.x, y: ch.y, name: ch.name, mode: 'lines', line: {{ width: 1.5 }}, connectgaps: false }}));
            const chartHeight = (id === 'gear') ? 250 : 320;
            const p = Plotly.newPlot(container, traces, {{ ...commonLayout, height: chartHeight, title: {{ text: chartTitles[id] || id.toUpperCase(), font: {{ size: 13 }} }} }}, {{ displayModeBar: false, staticPlot: true }});
            plotPromises.push(p);
            charts.push({{ el: container, id: id, wrapper: wrapper, canvas: canvas }});

            wrapper.addEventListener('mousedown', function(e) {{ isDragging = true; syncFromEvent(e, container); }});
            wrapper.addEventListener('mousemove', function(e) {{ if (isDragging) syncFromEvent(e, container); }});
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
                Plotly.restyle(mapChart, {{ x: [[posLon]], y: [[posLat]] }}, [2]);
            }}
        }}

        function updateSidebarPosition() {{
            const sidebar = document.getElementById('lap-sidebar');
            if (!sidebar) return;
            try {{
                const iframeRect = window.frameElement ? window.frameElement.getBoundingClientRect() : null;
                if (iframeRect) {{
                    const scrolledAbove = Math.max(0, -iframeRect.top);
                    const viewportH = window.parent.innerHeight || window.innerHeight;
                    const sidebarH = sidebar.offsetHeight;
                    const visibleTop = scrolledAbove;
                    const visibleBottom = scrolledAbove + viewportH;
                    const visibleH = visibleBottom - visibleTop;
                    let targetY = visibleTop + Math.max(0, (visibleH - sidebarH) / 2);
                    const containerH = sidebar.parentElement ? sidebar.parentElement.offsetHeight : 0;
                    targetY = Math.min(targetY, Math.max(0, containerH - sidebarH));
                    targetY = Math.max(0, targetY);
                    sidebar.style.transform = 'translateY(' + targetY + 'px)';
                }}
            }} catch(e) {{}}
        }}

        try {{
            window.parent.addEventListener('scroll', updateSidebarPosition, true);
            let el = window.frameElement;
            while (el) {{
                el = el.parentElement;
                if (el) el.addEventListener('scroll', updateSidebarPosition, true);
            }}
        }} catch(e) {{}}
        setInterval(updateSidebarPosition, 100);
    </script>
    """

    st.markdown(
        """
    <style>
        .stHtml iframe, .element-container iframe { width: 100% !important; }
        div[data-testid="stIFrame"] iframe { width: 100% !important; }
    </style>
    """,
        unsafe_allow_html=True,
    )
    components.html(html_code, height=total_height, scrolling=False)
