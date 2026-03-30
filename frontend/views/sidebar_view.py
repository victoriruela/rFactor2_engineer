"""Sidebar UI: file upload and ephemeral session controls."""

from __future__ import annotations

import os
import tempfile

import streamlit as st

from frontend import api_client, session_manager
from frontend.components import browser_hooks
from frontend.components.chunked_uploader import chunked_uploader
from frontend.config import (
    API_BASE_URL,
    BROWSER_API_BASE_URL,
    TEMP_UPLOAD_ROOT,
    UPLOAD_CHUNK_SIZE,
)


def render_sidebar() -> dict:
    """Render the sidebar and return session path info.

    Returns a dict with keys ``tele_path``, ``svm_path``, ``tele_name``,
    ``svm_name`` (all may be *None* if no session is loaded).
    """
    result = dict(tele_path=None, svm_path=None, tele_name=None, svm_name=None)

    with st.sidebar:
        st.header("Carga de Datos")

        session_manager.ensure_client_session_id(st.session_state)
        _inject_cleanup_on_unload()

        if not st.session_state.get("_global_cleanup_done"):
            try:
                api_client.post_cleanup_all(API_BASE_URL, timeout=15)
            except Exception:
                pass
            st.session_state["_global_cleanup_done"] = True

        if "fixed_params" not in st.session_state:
            # Deferred import avoids circular dependency; fixed_params lives in setup_view
            from frontend.views.setup_view import load_fixed_params  # noqa: PLC0415
            st.session_state["fixed_params"] = load_fixed_params()

        if "selected_session_name" not in st.session_state:
            st.session_state["selected_session_name"] = None

        if not st.session_state["selected_session_name"]:
            st.caption("Modo efímero: los datos se mantienen solo durante esta sesión de navegador.")

            # Telemetry: chunked JS uploader (handles files > 100 MB through Cloudflare)
            client_session_id = st.session_state.get("client_session_id", "")
            tele_result = chunked_uploader(
                label="Arrastra el archivo de telemetría (.mat/.csv) aquí o pulsa Seleccionar",
                browser_api_base_url=BROWSER_API_BASE_URL,
                client_session_id=client_session_id,
                chunk_size=UPLOAD_CHUNK_SIZE,
                file_types=["mat", "csv"],
                height=120,
                key="chunked_tele_upload",
            )
            # Persist the component result in session_state so it survives reruns
            if tele_result:
                st.session_state["_chunked_tele_result"] = tele_result

            svm_file = st.file_uploader("Archivo setup (.svm)", type=["svm"], key="svm_upload")

            tele_ready = bool(st.session_state.get("_chunked_tele_result"))
            if tele_ready:
                fn = st.session_state["_chunked_tele_result"]["filename"]
                st.caption(f"📄 {fn}")

            if st.button(
                "Cargar sesión local",
                use_container_width=True,
                disabled=not (tele_ready and svm_file),
            ):
                try:
                    session_manager.cleanup_temp_session_files(st.session_state)
                    tele_info = st.session_state.pop("_chunked_tele_result")

                    # Download the telemetry file from backend temporary storage
                    # (it was already uploaded there by the browser JS chunked uploader).
                    temp_root = session_manager.ensure_temp_upload_root(TEMP_UPLOAD_ROOT)
                    session_dir = tempfile.mkdtemp(prefix="rf2-session-", dir=temp_root)
                    tele_name = os.path.basename(tele_info["filename"])
                    svm_name  = os.path.basename(svm_file.name)
                    tele_path = os.path.join(session_dir, tele_name)
                    svm_path  = os.path.join(session_dir, svm_name)

                    with st.spinner("Descargando archivo de telemetría del servidor…"):
                        api_client.download_session_file(
                            API_BASE_URL,
                            client_session_id,
                            tele_name,
                            tele_path,
                        )

                    session_manager.write_uploaded_file_in_chunks(svm_file, svm_path, UPLOAD_CHUNK_SIZE)

                    st.session_state.update({
                        "temp_upload_dir": session_dir,
                        "telemetry_temp_path": tele_path,
                        "svm_temp_path": svm_path,
                        "tele_name": tele_name,
                        "svm_name": svm_name,
                    })
                    st.session_state["selected_session_name"] = os.path.splitext(tele_name)[0]
                    st.success("Archivos cargados en memoria local de sesión")
                except Exception as exc:
                    st.error(f"No se pudo cargar la sesión local: {exc}")
        else:
            st.info(f"Sesión activa: **{st.session_state['selected_session_name']}**")

            if st.button("🆕 Nueva sesión", use_container_width=True):
                try:
                    api_client.post_cleanup(
                        API_BASE_URL,
                        st.session_state.get("client_session_id"),
                        timeout=10,
                    )
                except Exception:
                    pass
                session_manager.cleanup_temp_session_files(st.session_state)
                st.session_state.clear()
                st.rerun()

        if st.session_state.get("selected_session_name"):
            tele_path = st.session_state.get("telemetry_temp_path")
            svm_path = st.session_state.get("svm_temp_path")
            tele_name = st.session_state.get("tele_name")
            svm_name = st.session_state.get("svm_name")
            files_ok = bool(
                tele_path
                and os.path.exists(tele_path)
                and svm_path
                and os.path.exists(svm_path)
            )
            if not files_ok:
                st.warning("La sesión efímera ya no está disponible. Vuelve a cargar los archivos.")
                session_manager.cleanup_temp_session_files(st.session_state)
                st.session_state["selected_session_name"] = None
            else:
                result.update(
                    tele_path=tele_path,
                    svm_path=svm_path,
                    tele_name=tele_name,
                    svm_name=svm_name,
                )

    return result


def _inject_cleanup_on_unload() -> None:
    session_id = st.session_state.get("client_session_id")
    if session_manager.is_valid_session_id(session_id):
        browser_hooks.inject_cleanup_on_unload(session_id, BROWSER_API_BASE_URL)
