import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="rFactor2 Engineer", layout="wide")

st.title("🏎️ rFactor2 Engineer")
st.subheader("Análisis de Telemetría y Setup mediante IA")

# Barra lateral para subir archivos
with st.sidebar:
    st.header("Carga de Datos")
    uploaded_files = st.file_uploader("Sube los archivos .ld y .svm de la sesión", type=["ld", "svm"], accept_multiple_files=True)
    
    selected_session = None
    ld_to_send = None
    svm_to_send = None

    if uploaded_files:
        # Agrupar archivos por nombre base
        sessions = {}
        for f in uploaded_files:
            base_name = f.name.rsplit('.', 1)[0]
            ext = f.name.rsplit('.', 1)[1].lower()
            if base_name not in sessions:
                sessions[base_name] = {}
            sessions[base_name][ext] = f
        
        # Validar sesiones
        valid_sessions = []
        for name, files in sessions.items():
            if "ld" in files and "svm" in files:
                valid_sessions.append(name)
            else:
                missing = []
                if "ld" not in files: missing.append(".ld")
                if "svm" not in files: missing.append(".svm")
                st.error(f"Faltan archivos para la sesión '{name}': {', '.join(missing)}")
        
        if valid_sessions:
            selected_session = st.selectbox("Selecciona la sesión a analizar", valid_sessions)
            if selected_session:
                ld_to_send = sessions[selected_session]["ld"]
                svm_to_send = sessions[selected_session]["svm"]
                st.success(f"Sesión '{selected_session}' lista para analizar.")

    analyze_button = st.button("Analizar Datos", disabled=not (ld_to_send and svm_to_send))

# Main Page
if analyze_button and ld_to_send and svm_to_send:
    with st.spinner(f"Analizando sesión '{selected_session}' con IA..."):
        files = {
            "ld_file": (ld_to_send.name, ld_to_send.getvalue()),
            "svm_file": (svm_to_send.name, svm_to_send.getvalue())
        }
        
        try:
            response = requests.post("http://localhost:8000/analyze", files=files)
            
            if response.status_code == 200:
                data = response.json()
                
                # 1. Visualización: Mapa de circuito mejorado
                st.header("📍 Mapa del Circuito y Puntos Críticos")
                
                # Dibujar el trazado
                track_x = data['circuit_data']['x']
                track_y = data['circuit_data']['y']
                
                fig = go.Figure()
                
                # Línea del trazado
                fig.add_trace(go.Scatter(
                    x=track_x, y=track_y,
                    mode='lines',
                    line=dict(color='lightgrey', width=2),
                    name='Trazado',
                    hoverinfo='skip'
                ))
                
                # Puntos de interés (Issues)
                issues_df = pd.DataFrame(data['issues_on_map'])
                if not issues_df.empty:
                    fig.add_trace(go.Scatter(
                        x=issues_df['x'],
                        y=issues_df['y'],
                        mode='markers',
                        marker=dict(
                            color=issues_df['color'],
                            size=12,
                            line=dict(width=2, color='DarkSlateGrey')
                        ),
                        text=issues_df['label'],
                        name='Puntos de Mejora',
                        hovertemplate="<b>%{text}</b><extra></extra>"
                    ))
                
                fig.update_layout(
                    xaxis_title="GPS Longitude",
                    yaxis_title="GPS Latitude",
                    yaxis=dict(scaleanchor="x", scaleratio=1),
                    showlegend=True,
                    template="plotly_dark",
                    margin=dict(l=0, r=0, t=30, b=0),
                    height=600
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # 1.5 Estadísticas de la Sesión
                st.header("📊 Resumen de la Sesión")
                s_stats = data.get('session_stats', {})
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("Vueltas Totales", s_stats.get('total_laps', '-'))
                    st.metric("Vuelta Rápida", s_stats.get('fastest_lap', '-'))
                with c2:
                    st.metric("Consumo Total", f"{s_stats.get('fuel_total', '-')} L")
                    st.metric("Consumo Medio", f"{s_stats.get('fuel_avg', '-')} L/vta")
                with c3:
                    st.metric("Desgaste Total", f"{s_stats.get('wear_total', '-')} %")
                    st.metric("Desgaste Medio", f"{s_stats.get('wear_avg', '-')} %/vta")
                with c4:
                    st.metric("Vta. Rápida #", s_stats.get('fastest_lap_num', '-'))

                # 2. Análisis Detallado
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🏁 Análisis de Conducción")
                    st.info(data['driving_analysis'])
                            
                with col2:
                    st.subheader("🛠️ Análisis de Setup")
                    st.warning(data['setup_analysis'])
                            
                # 3. Setup Completo (Estilo rFactor 2)
                st.header("🔧 Setup Completo y Modificaciones")
                st.markdown("A continuación se muestra el setup completo organizado por secciones. Los cambios recomendados están resaltados.")
                
                full_setup = data.get('full_setup', {})
                sections = full_setup.get('sections', [])
                
                if not sections:
                    st.error("No se pudieron generar las secciones de setup completo. Por favor, intenta de nuevo.")
                else:
                    for section in sections:
                        with st.expander(f"📂 Sección: {section['name']}", expanded=False):
                            # Preparar datos para la tabla
                            items = section.get('items', [])
                            if items:
                                table_data = []
                                for item in items:
                                    val_new = str(item.get('new', '')).strip()
                                    val_curr = str(item.get('current', '')).strip()

                                    # Lógica de cambio
                                    has_change = val_new.lower() != val_curr.lower()
                                    
                                    row = {
                                        "Parámetro": item['parameter'],
                                        "Valor Actual": val_curr,
                                        "Recomendación": f"✨ **{val_new}**" if has_change else "✅",
                                        "Motivo / Justificación": item['reason']
                                    }
                                    table_data.append(row)
                                
                                # Mostramos la tabla sin índice y con resaltado
                                if table_data:
                                    st.dataframe(
                                        table_data, 
                                        use_container_width=True, 
                                        hide_index=True,
                                        column_config={
                                            "Motivo / Justificación": st.column_config.TextColumn(
                                                width="large",
                                            )
                                        }
                                    )
                            else:
                                st.write("No hay parámetros en esta sección.")
                
            elif response.status_code == 400:
                error_detail = response.json().get('detail', 'Error desconocido.')
                st.error(f"❌ Error: {error_detail}")
            else:
                st.error(f"💥 Error en la API ({response.status_code}): {response.text}")
        except Exception as e:
            st.error(f"Error conectando con la API: {e}")
else:
    st.info("Sube los archivos .ld y .svm de la misma sesión para comenzar el ingeniero virtual.")
