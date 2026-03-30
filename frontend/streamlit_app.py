import os
import sys

# Ensure project root is importable when Streamlit launches this file from frontend/.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st

from frontend import api_client, session_manager, telemetry_processing
from frontend.components import telemetry_embed
from frontend.config import (
    ANALYSIS_REQUEST_TIMEOUT,
    API_BASE_URL,
    MAT_PREVIEW_MAX_MB,
    TEMP_UPLOAD_ROOT,
    UPLOAD_CHUNK_SIZE,
)
from frontend.views import analysis_view, setup_view, sidebar_view, telemetry_view

# ─────────────────────────────────────────────────────────────────────────────
# Thin delegates — kept for test backward-compatibility
# ─────────────────────────────────────────────────────────────────────────────


def _ensure_temp_upload_root():
    return session_manager.ensure_temp_upload_root(TEMP_UPLOAD_ROOT)


def _cleanup_stale_temp_dirs(max_age_hours: int = 4):
    session_manager.cleanup_stale_temp_dirs(TEMP_UPLOAD_ROOT, max_age_hours=max_age_hours)


def _cleanup_temp_session_files():
    session_manager.cleanup_temp_session_files(st.session_state)


def _write_uploaded_file_in_chunks(uploaded_file, target_path, chunk_size=UPLOAD_CHUNK_SIZE):
    session_manager.write_uploaded_file_in_chunks(uploaded_file, target_path, chunk_size)


def _persist_uploaded_session(telemetry_file, svm_file):
    return session_manager.persist_uploaded_session(
        telemetry_file,
        svm_file,
        temp_upload_root=TEMP_UPLOAD_ROOT,
        chunk_size=UPLOAD_CHUNK_SIZE,
    )


def _is_valid_session_id(value):
    return session_manager.is_valid_session_id(value)


def _ensure_client_session_id():
    return session_manager.ensure_client_session_id(st.session_state)


def _api_headers():
    session_id = st.session_state.get("client_session_id")
    if not _is_valid_session_id(session_id):
        return {}
    return api_client.headers_for_session(session_id)


# ─────────────────────────────────────────────────────────────────────────────
# Cached helpers
# ─────────────────────────────────────────────────────────────────────────────


@st.cache_resource
def _run_startup_cleanup():
    _cleanup_stale_temp_dirs(max_age_hours=4)
    return True


@st.cache_data(show_spinner=False, max_entries=1, ttl=7200)
def get_mat_dataframe(file_path):
    try:
        df = telemetry_processing.load_mat_dataframe(file_path)
        return telemetry_processing.filter_incomplete_laps(df)
    except Exception as exc:
        st.error(f"Error procesando .mat: {exc}")
        return None


def precompute_all_laps(df, laps):
    return telemetry_processing.precompute_all_laps(df, laps)


def _build_lap_data(lap_df):
    return telemetry_processing.build_lap_data(lap_df)


def _lap_xy(lap_df, x_col, y_col):
    return telemetry_processing.lap_xy(lap_df, x_col, y_col)


def plot_all_laps_interactive(all_lap_figs, laps, lap_options, fastest_lap):
    telemetry_embed.plot_all_laps_interactive(all_lap_figs, laps, lap_options, fastest_lap)


def cleanup_server_data():
    try:
        api_client.post_cleanup(API_BASE_URL, st.session_state.get("client_session_id"), timeout=10)
    except Exception:
        pass


def _post_analysis_with_local_files(data_form):
    """Delegate kept for test backward-compatibility; used by analysis_view internally."""
    tele_path = st.session_state.get("telemetry_temp_path")
    svm_path = st.session_state.get("svm_temp_path")
    tele_name = st.session_state.get("tele_name") or os.path.basename(tele_path or "telemetry")
    svm_name = st.session_state.get("svm_name") or os.path.basename(svm_path or "setup.svm")

    if not tele_path or not svm_path or not os.path.exists(tele_path) or not os.path.exists(svm_path):
        raise FileNotFoundError("Local temporary upload files are missing")

    with open(tele_path, "rb") as telemetry_fh, open(svm_path, "rb") as svm_fh:
        files = {
            "telemetry_file": (tele_name, telemetry_fh),
            "svm_file": (svm_name, svm_fh),
        }
        return api_client.post_analyze_with_files(
            API_BASE_URL,
            st.session_state.get("client_session_id"),
            data_form,
            files,
            ANALYSIS_REQUEST_TIMEOUT,
        )


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="rFactor2 Engineer", layout="wide")

_run_startup_cleanup()

st.title("🏎️ rFactor2 Engineer")
st.subheader("Análisis de Telemetría y Setup mediante IA")

session = sidebar_view.render_sidebar()
tele_path = session["tele_path"]
svm_path = session["svm_path"]
tele_name = session["tele_name"]

if not (tele_path and svm_path):
    st.info("👋 Sube tus archivos o elige una sesión anterior en la barra lateral para comenzar.")
else:
    file_size_mb = 0.0
    try:
        file_size_mb = os.path.getsize(tele_path) / (1024 * 1024)
    except Exception:
        pass

    skip_mat_preview = tele_name.endswith(".mat") and file_size_mb > MAT_PREVIEW_MAX_MB

    if tele_name.endswith(".mat") and not skip_mat_preview:
        df_local = get_mat_dataframe(tele_path)

        if df_local is None or "Lap_Number" not in df_local.columns:
            st.error("No se encontró canal 'Lap_Number' en el .mat")
        else:
            laps = sorted([int(lap) for lap in df_local["Lap_Number"].unique() if lap > 0])

            if not laps:
                st.warning("No se encontraron vueltas completas.")
            else:
                # Build / retrieve lap figure cache
                _cache_key = (tele_path, tuple(laps))
                if st.session_state.get("_lap_cache_key") != _cache_key:
                    with st.spinner("Procesando telemetría..."):
                        st.session_state["_lap_cache"] = precompute_all_laps(df_local, tuple(laps))
                        st.session_state["_lap_cache_key"] = _cache_key
                all_lap_figs = st.session_state["_lap_cache"]

                lap_times, fastest_lap = telemetry_view.compute_fastest_lap(df_local, laps)

                tab_tele, tab_setup, tab_ai = st.tabs(
                    ["📊 Telemetría", "🔧 Setup", "🤖 Análisis AI"]
                )

                with tab_tele:
                    telemetry_view.render_telemetry_tab(
                        df_local, laps, all_lap_figs, lap_times, fastest_lap
                    )

                with tab_setup:
                    setup_view.render_setup_tab(svm_path)

                with tab_ai:
                    analysis_view.render_analysis_tab(tele_path, svm_path, tele_name)
    else:
        if skip_mat_preview:
            st.warning(
                f"Archivo .mat grande ({file_size_mb:.1f} MB). "
                "Se omite la vista de telemetría para evitar reinicios del servidor. "
                "Puedes ejecutar el análisis IA igualmente."
            )
        else:
            st.info("La visualización detallada actualmente solo soporta archivos .mat.")

        analysis_view.render_analysis_tab(tele_path, svm_path, tele_name)
