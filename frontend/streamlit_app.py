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
    # No re-ordenamos por x_col (Lap_Distance) para mantener la secuencia temporal real.
    x_arr = lap_df[x_col].values
    y_arr = lap_df[y_col].values

    if len(x_arr) < 2:
        return x_arr.tolist(), y_arr.tolist()

    # Detectar saltos en el eje X (distancia o GPS)
    # Si Lap_Distance salta de 4000 a 0, o viceversa, es un salto de vuelta o error.
    # Usamos un umbral basado en el rango total si es posible, o un valor fijo razonable.
    x_range = np.ptp(x_arr) if len(x_arr) > 0 else 0
    threshold = max(x_range * 0.05, 50.0) # 5% del circuito o 50m

    xs, ys = [], []
    for i in range(len(x_arr)):
        if i > 0:
            # Si hay un salto brusco hacia adelante o atrás en X, romper la línea
            if abs(x_arr[i] - x_arr[i-1]) > threshold:
                xs.append(None)
                ys.append(None)
        
        xv = float(x_arr[i])
        yv = float(y_arr[i])
        xs.append(xv if not np.isnan(xv) else None)
        ys.append(yv if not np.isnan(yv) else None)
    
    return xs, ys


def _build_lap_figures(lap_df):
    """Construye todos los objetos Figure para una vuelta dada."""
    line_style = dict(width=1)
    colors = ['cyan', 'magenta', 'lime', 'orange']
    wheels = ['FL', 'FR', 'RL', 'RR']
    x_col = 'Lap_Distance'

    figs = {}

    # ── General ──────────────────────────────────────────────────────────────
    fig_speed = go.Figure()
    xs, ys = _lap_xy(lap_df, x_col, 'Ground_Speed')
    fig_speed.add_trace(go.Scatter(x=xs, y=ys, name="Velocidad (km/h)", line=line_style, connectgaps=False))
    fig_speed.update_layout(height=300, template="plotly_dark", xaxis_title="Distancia (m)", margin=dict(l=0, r=0, t=30, b=0))
    figs['speed'] = fig_speed

    fig_ctrl = go.Figure()
    for col, label in [('Throttle_Pos', 'Acelerador (%)'), ('Brake_Pos', 'Freno (%)')]:
        if col in lap_df.columns:
            xs, ys = _lap_xy(lap_df, x_col, col)
            ys_pct = [v * 100 if v is not None else None for v in ys]
            fig_ctrl.add_trace(go.Scatter(x=xs, y=ys_pct, name=label, line=line_style, connectgaps=False))
    fig_ctrl.update_layout(height=300, template="plotly_dark", xaxis_title="Distancia (m)", margin=dict(l=0, r=0, t=30, b=0))
    figs['controls'] = fig_ctrl

    fig_steer = go.Figure()
    xs, ys = _lap_xy(lap_df, x_col, 'Steering_Wheel_Position')
    fig_steer.add_trace(go.Scatter(x=xs, y=ys, name="Dirección", line=line_style, connectgaps=False))
    fig_steer.update_layout(height=300, template="plotly_dark", title="Volante", xaxis_title="Distancia (m)", margin=dict(l=0, r=0, t=30, b=0))
    figs['steer'] = fig_steer

    # ── Motor ─────────────────────────────────────────────────────────────────
    fig_rpm = go.Figure()
    xs, ys = _lap_xy(lap_df, x_col, 'Engine_RPM')
    fig_rpm.add_trace(go.Scatter(x=xs, y=ys, name="RPM", line=line_style, connectgaps=False))
    fig_rpm.update_layout(height=300, template="plotly_dark", xaxis_title="Distancia (m)", margin=dict(l=0, r=0, t=30, b=0))
    figs['rpm'] = fig_rpm

    fig_gear = go.Figure()
    xs, ys = _lap_xy(lap_df, x_col, 'Gear')
    fig_gear.add_trace(go.Scatter(x=xs, y=ys, name="Marcha", line=line_style, connectgaps=False))
    fig_gear.update_layout(height=250, template="plotly_dark", xaxis_title="Distancia (m)", margin=dict(l=0, r=0, t=30, b=0))
    figs['gear'] = fig_gear

    # ── Suspensión ────────────────────────────────────────────────────────────
    fig_susp = go.Figure()
    for i, w in enumerate(wheels):
        col = f'Susp_Pos_{w}'
        if col in lap_df.columns:
            xs, ys = _lap_xy(lap_df, x_col, col)
            fig_susp.add_trace(go.Scatter(x=xs, y=ys, name=f"Susp {w}", line=dict(color=colors[i], width=1), connectgaps=False))
    fig_susp.update_layout(height=400, template="plotly_dark", xaxis_title="Distancia (m)", margin=dict(l=0, r=0, t=30, b=0))
    figs['susp_pos'] = fig_susp

    fig_rh = go.Figure()
    for i, w in enumerate(wheels):
        col = f'Ride_Height_{w}'
        if col in lap_df.columns:
            xs, ys = _lap_xy(lap_df, x_col, col)
            ys_mm = [v * 1000 if v is not None else None for v in ys]
            fig_rh.add_trace(go.Scatter(x=xs, y=ys_mm, name=f"RH {w}", line=dict(color=colors[i], width=1), connectgaps=False))
    fig_rh.update_layout(height=400, template="plotly_dark", yaxis_title="mm", xaxis_title="Distancia (m)", margin=dict(l=0, r=0, t=30, b=0))
    figs['ride_height'] = fig_rh

    # ── Neumáticos ────────────────────────────────────────────────────────────
    fig_brk = go.Figure()
    for i, w in enumerate(wheels):
        col = f'Brake_Temp_{w}'
        if col in lap_df.columns:
            xs, ys = _lap_xy(lap_df, x_col, col)
            fig_brk.add_trace(go.Scatter(x=xs, y=ys, name=f"Brake Temp {w}", line=dict(color=colors[i], width=1), connectgaps=False))
    fig_brk.update_layout(height=400, template="plotly_dark", yaxis_title="°C", xaxis_title="Distancia (m)", margin=dict(l=0, r=0, t=30, b=0))
    figs['brake_temp'] = fig_brk

    fig_pres = go.Figure()
    for i, w in enumerate(wheels):
        col = f'Tyre_Pressure_{w}'
        if col in lap_df.columns:
            xs, ys = _lap_xy(lap_df, x_col, col)
            fig_pres.add_trace(go.Scatter(x=xs, y=ys, name=f"Tyre Pres {w}", line=dict(color=colors[i], width=1), connectgaps=False))
    fig_pres.update_layout(height=400, template="plotly_dark", yaxis_title="kPa", xaxis_title="Distancia (m)", margin=dict(l=0, r=0, t=30, b=0))
    figs['tyre_pres'] = fig_pres

    # ── Aero ──────────────────────────────────────────────────────────────────
    fig_aero = go.Figure()
    for col, label in [('Front_Downforce', 'Front DF'), ('Rear_Downforce', 'Rear DF')]:
        if col in lap_df.columns:
            xs, ys = _lap_xy(lap_df, x_col, col)
            fig_aero.add_trace(go.Scatter(x=xs, y=ys, name=label, line=line_style, connectgaps=False))
    fig_aero.update_layout(height=400, template="plotly_dark", xaxis_title="Distancia (m)", margin=dict(l=0, r=0, t=30, b=0))
    figs['aero'] = fig_aero

    # ── Circuito (GPS) ────────────────────────────────────────────────────────
    if 'GPS_Longitude' in lap_df.columns and 'GPS_Latitude' in lap_df.columns:
        # Para el mapa GPS usamos los datos tal cual (ya suavizados en el parser)
        # Insertamos None donde hay saltos grandes en longitud
        xs, ys = _lap_xy(lap_df, 'GPS_Longitude', 'GPS_Latitude')
        fig_map = go.Figure()
        fig_map.add_trace(go.Scatter(x=xs, y=ys, mode='lines', line=dict(color='yellow', width=1.5), connectgaps=False))
        fig_map.update_layout(
            height=600, template="plotly_dark",
            yaxis=dict(scaleanchor="x", scaleratio=1),
            margin=dict(l=0, r=0, t=30, b=0)
        )
        figs['map'] = fig_map

    return figs


@st.cache_resource(show_spinner=False)
def precompute_all_laps(df, laps):
    """
    Pre-genera los objetos Figure de todas las vueltas y los devuelve.
    Se cachea como recurso para que no se re-calcule al interactuar con la UI.
    """
    all_figs = {}
    progress_container = st.empty()
    total_laps = len(laps)
    for i, lap in enumerate(laps):
        lap_df = df[df['Lap_Number'] == lap].copy()
        # Mantenemos el orden temporal original (ya viene ordenado por Session_Elapsed_Time)
        # NO ordenar por Lap_Distance aquí, dejar que _lap_xy maneje la secuencia.
        all_figs[lap] = _build_lap_figures(lap_df)
        with progress_container.container():
            st.progress((i + 1) / total_laps, text=f"Procesando Vuelta {lap} de {laps[-1]}...")
    
    progress_container.empty()
    return all_figs


def plot_telemetry_charts(figs):
    """Renderiza los gráficos pre-generados de una vuelta."""
    if not figs:
        st.warning("No hay datos para esta vuelta.")
        return

    tabs = st.tabs(["General", "Motor", "Suspensión", "Neumáticos", "Aerodinámica", "Circuito"])

    with tabs[0]:
        st.subheader("Velocidad")
        st.plotly_chart(figs['speed'], use_container_width=True)
        st.subheader("Controles (Acelerador y Freno)")
        st.plotly_chart(figs['controls'], use_container_width=True)
        st.plotly_chart(figs['steer'], use_container_width=True)

    with tabs[1]:
        st.subheader("Motor y Transmisión")
        st.plotly_chart(figs['rpm'], use_container_width=True)
        st.plotly_chart(figs['gear'], use_container_width=True)

    with tabs[2]:
        st.subheader("Posición de Suspensión")
        st.plotly_chart(figs['susp_pos'], use_container_width=True)
        st.subheader("Ride Heights")
        st.plotly_chart(figs['ride_height'], use_container_width=True)

    with tabs[3]:
        st.subheader("Temperaturas de Frenos")
        st.plotly_chart(figs['brake_temp'], use_container_width=True)
        st.subheader("Presiones de Neumáticos")
        st.plotly_chart(figs['tyre_pres'], use_container_width=True)

    with tabs[4]:
        st.subheader("Downforce")
        st.plotly_chart(figs['aero'], use_container_width=True)

    with tabs[5]:
        st.subheader("Trazado GPS")
        if 'map' in figs:
            st.plotly_chart(figs['map'], use_container_width=True)


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
                            # Renderizar gráficos para esta vuelta (ya están precomputeados)
                            plot_telemetry_charts(all_lap_figs.get(lap, {}))

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
