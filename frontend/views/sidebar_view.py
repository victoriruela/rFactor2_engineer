"""Sidebar UI: file upload and ephemeral session controls."""

from __future__ import annotations

import os
import tempfile

import streamlit as st

from frontend import api_client, session_manager
from frontend.components.browser_session import sync_browser_session_id
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

        client_session_id = _sync_client_session_id()

        if "fixed_params" not in st.session_state:
            # Deferred import avoids circular dependency; fixed_params lives in setup_view
            from frontend.views.setup_view import load_fixed_params  # noqa: PLC0415
            st.session_state["fixed_params"] = load_fixed_params()

        if "selected_session_name" not in st.session_state:
            st.session_state["selected_session_name"] = None
        if "_load_local_requested" not in st.session_state:
            st.session_state["_load_local_requested"] = False
        if "_load_local_status" not in st.session_state:
            st.session_state["_load_local_status"] = ""
        if "_load_local_error" not in st.session_state:
            st.session_state["_load_local_error"] = ""

        _restore_session_if_possible(client_session_id)

        if not st.session_state["selected_session_name"]:
            st.caption("Modo efímero: los datos se mantienen solo durante esta sesión de navegador.")

            tele_result = chunked_uploader(
                label="Archivo de telemetría (.mat/.csv)",
                help_text="Subida en fragmentos con progreso y temporizador. Válido para archivos grandes.",
                browser_api_base_url=BROWSER_API_BASE_URL,
                client_session_id=client_session_id,
                chunk_size=UPLOAD_CHUNK_SIZE,
                file_types=["mat", "csv"],
                height=185,
                key="chunked_tele_upload",
            )
            if tele_result:
                st.session_state["_chunked_tele_result"] = tele_result

            svm_result = chunked_uploader(
                label="Archivo setup (.svm)",
                help_text="Subida en fragmentos con el mismo flujo que la telemetría.",
                browser_api_base_url=BROWSER_API_BASE_URL,
                client_session_id=client_session_id,
                chunk_size=UPLOAD_CHUNK_SIZE,
                file_types=["svm"],
                height=185,
                key="chunked_svm_upload",
            )
            if svm_result:
                st.session_state["_chunked_svm_result"] = svm_result

            tele_ready = bool(st.session_state.get("_chunked_tele_result"))
            svm_ready = bool(st.session_state.get("_chunked_svm_result"))

            st.caption(f"Telemetría: {'lista' if tele_ready else 'pendiente'}")
            st.caption(f"Setup: {'listo' if svm_ready else 'pendiente'}")

            if st.session_state.get("_load_local_status"):
                st.info(st.session_state["_load_local_status"])
            if st.session_state.get("_load_local_error"):
                st.error(st.session_state["_load_local_error"])

            st.button(
                "Cargar sesión local",
                use_container_width=True,
                disabled=not (tele_ready and svm_ready),
                on_click=_request_local_load,
            )

            if st.session_state.get("_load_local_requested"):
                try:
                    st.session_state["_load_local_error"] = ""
                    tele_info = st.session_state.get("_chunked_tele_result")
                    svm_info = st.session_state.get("_chunked_svm_result")
                    if not tele_info or not svm_info:
                        st.session_state["_load_local_requested"] = False
                        st.session_state["_load_local_error"] = (
                            "Falta algún archivo cargado. Sube telemetría y setup antes de continuar."
                        )
                        return result

                    tele_session_id = tele_info.get("session_id") or client_session_id
                    svm_session_id = svm_info.get("session_id") or client_session_id
                    if tele_session_id != svm_session_id:
                        st.session_state["_load_local_requested"] = False
                        st.session_state["_load_local_error"] = (
                            "Telemetría y setup pertenecen a sesiones distintas. Vuelve a subir ambos archivos."
                        )
                        return result

                    with st.spinner("Preparando sesión local…"):
                        st.session_state["_load_local_status"] = "Preparando sesión local…"
                        session_manager.cleanup_temp_session_files(st.session_state)

                        temp_root = session_manager.ensure_temp_upload_root(TEMP_UPLOAD_ROOT)
                        session_dir = tempfile.mkdtemp(prefix="rf2-session-", dir=temp_root)
                        tele_name = os.path.basename(tele_info["filename"])
                        svm_name = os.path.basename(svm_info["filename"])
                        tele_path = os.path.join(session_dir, tele_name)
                        svm_path = os.path.join(session_dir, svm_name)

                        st.session_state["_load_local_status"] = "Descargando telemetría desde backend…"
                        api_client.download_uploaded_file(
                            API_BASE_URL,
                            tele_session_id,
                            tele_name,
                            tele_path,
                            timeout=1800,
                        )

                        st.session_state["_load_local_status"] = "Descargando setup desde backend…"
                        api_client.download_uploaded_file(
                            API_BASE_URL,
                            svm_session_id,
                            svm_name,
                            svm_path,
                            timeout=1800,
                        )

                        if not os.path.exists(tele_path) or os.path.getsize(tele_path) == 0:
                            raise RuntimeError("La telemetría descargada está vacía o no existe")
                        if not os.path.exists(svm_path) or os.path.getsize(svm_path) == 0:
                            raise RuntimeError("El setup descargado está vacío o no existe")

                        st.session_state.update({
                            "temp_upload_dir": session_dir,
                            "telemetry_temp_path": tele_path,
                            "svm_temp_path": svm_path,
                            "tele_name": tele_name,
                            "svm_name": svm_name,
                        })
                        st.session_state["selected_session_name"] = os.path.splitext(tele_name)[0]
                        st.session_state.pop("_chunked_tele_result", None)
                        st.session_state.pop("_chunked_svm_result", None)
                        st.session_state["_load_local_status"] = "Sesión local preparada."
                        st.session_state["_load_local_requested"] = False
                    st.success("Archivos cargados en memoria local de sesión")
                    st.rerun()
                except Exception as exc:
                    st.session_state["_load_local_requested"] = False
                    st.session_state["_load_local_error"] = f"No se pudo cargar la sesión local: {exc}"
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
                _reset_for_new_session()
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


def _sync_client_session_id() -> str:
    current = st.session_state.get("client_session_id")
    browser_value = sync_browser_session_id(
        storage_key="rf2_client_session_id",
        candidate_session_id=current if session_manager.is_valid_session_id(current) else None,
        reset_counter=st.session_state.get("browser_session_reset_counter", 0),
        key="rf2_browser_session_sync",
    )
    return session_manager.ensure_client_session_id(st.session_state, preferred_session_id=browser_value)


def _restore_session_if_possible(client_session_id: str) -> None:
    if not session_manager.is_valid_session_id(client_session_id):
        return
    if st.session_state.get("selected_session_name"):
        return
    if st.session_state.get("_chunked_tele_result") or st.session_state.get("_chunked_svm_result"):
        return
    if st.session_state.get("_restore_attempted_for") == client_session_id:
        return

    st.session_state["_restore_attempted_for"] = client_session_id
    try:
        sessions = api_client.get_sessions(API_BASE_URL, client_session_id, timeout=10).get("sessions", [])
    except Exception:
        return
    if not sessions:
        return

    latest = sessions[0]
    try:
        temp_root = session_manager.ensure_temp_upload_root(TEMP_UPLOAD_ROOT)
        session_dir = tempfile.mkdtemp(prefix="rf2-restore-", dir=temp_root)
        tele_name = latest["telemetry"]
        svm_name = latest["svm"]
        tele_path = os.path.join(session_dir, tele_name)
        svm_path = os.path.join(session_dir, svm_name)
        api_client.download_uploaded_file(API_BASE_URL, client_session_id, tele_name, tele_path)
        api_client.download_uploaded_file(API_BASE_URL, client_session_id, svm_name, svm_path)
    except Exception:
        return

    st.session_state.update({
        "temp_upload_dir": session_dir,
        "telemetry_temp_path": tele_path,
        "svm_temp_path": svm_path,
        "tele_name": tele_name,
        "svm_name": svm_name,
        "selected_session_name": latest.get("display_name") or os.path.splitext(tele_name)[0],
    })


def _reset_for_new_session() -> None:
    session_manager.cleanup_temp_session_files(st.session_state)
    for key in (
        "selected_session_name",
        "client_session_id",
        "ai_analysis_data",
        "ai_model",
        "ai_circuit_name",
        "ai_setup_data",
        "_chunked_tele_result",
        "_chunked_svm_result",
        "_restore_attempted_for",
        "_lap_cache",
        "_lap_cache_key",
        "_load_local_requested",
        "_load_local_status",
        "_load_local_error",
    ):
        st.session_state.pop(key, None)
    st.session_state["browser_session_reset_counter"] = st.session_state.get("browser_session_reset_counter", 0) + 1


def _request_local_load() -> None:
    st.session_state["_load_local_requested"] = True
    st.session_state["_load_local_error"] = ""
