"""AI analysis tab: provider selection, trigger, and results display."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from frontend import api_client, setup_parser
from frontend.config import ANALYSIS_REQUEST_TIMEOUT, API_BASE_URL


def _normalize_model_list(models_raw: list) -> list[str]:
    """Return unique, non-empty model names in deterministic order."""
    cleaned = [m.strip() for m in models_raw if isinstance(m, str) and m.strip()]
    # De-duplicate case-insensitively while preserving first-seen spelling.
    dedup: dict[str, str] = {}
    for name in cleaned:
        key = name.casefold()
        if key not in dedup:
            dedup[key] = name
    # Final sort guarantees stable UI order across reruns.
    return sorted(dedup.values(), key=str.casefold)


def render_analysis_tab(tele_path: str, svm_path: str, tele_name: str) -> None:
    """Render the AI analysis tab with provider selection and results."""
    st.header("Análisis de Ingeniero Virtual")

    provider_options = {
        "Ollama (local/remoto)": "ollama",
        "Jimmy API": "jimmy",
    }
    provider_label = st.selectbox("Proveedor LLM", list(provider_options.keys()))
    sel_provider = provider_options[provider_label]

    sel_model, sel_ollama_url, sel_ollama_api_key = _render_provider_controls(sel_provider)

    if st.button("🚀 Iniciar Análisis con IA"):
        _run_analysis(tele_path, svm_path, tele_name, sel_provider, sel_model, sel_ollama_url, sel_ollama_api_key)

    if "ai_analysis_data" in st.session_state:
        _render_results(svm_path)


# ---------------------------------------------------------------------------
# Provider selector widgets
# ---------------------------------------------------------------------------


def _render_provider_controls(sel_provider: str):
    """Render provider-specific widgets and return (model, ollama_url, ollama_api_key)."""
    if sel_provider != "ollama":
        st.caption("Modelo Jimmy seleccionado: llama3.1-8B")
        return "llama3.1-8B", "", ""

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

    models_params = {}
    if sel_ollama_url.strip():
        models_params["ollama_base_url"] = sel_ollama_url.strip()
    if sel_ollama_api_key.strip():
        models_params["ollama_api_key"] = sel_ollama_api_key.strip()

    try:
        resp = api_client.get_models(
            API_BASE_URL,
            st.session_state.get("client_session_id"),
            params=models_params,
            timeout=5,
        )
        available_models = resp.json().get("models", []) if resp.status_code == 200 else []
    except Exception:
        available_models = []

    available_models = _normalize_model_list(available_models)

    if available_models:
        selected_key = "selected_ollama_model"
        if st.session_state.get(selected_key) not in available_models:
            st.session_state[selected_key] = available_models[0]
        sel_model = st.selectbox("Modelo LLM", available_models, key=selected_key)
    else:
        st.session_state.pop("selected_ollama_model", None)
        st.warning("No se pudieron obtener modelos de Ollama. Se usará el modelo por defecto del backend.")
        sel_model = None

    return sel_model, sel_ollama_url, sel_ollama_api_key


# ---------------------------------------------------------------------------
# Analysis execution
# ---------------------------------------------------------------------------


def _run_analysis(
    tele_path: str,
    svm_path: str,
    tele_name: str,
    sel_provider: str,
    sel_model,
    sel_ollama_url: str,
    sel_ollama_api_key: str,
) -> None:
    st.session_state.pop("ai_analysis_data", None)
    st.session_state.pop("ai_model", None)

    with st.spinner("Analizando con IA…"):
        data_form: dict = {"provider": sel_provider}
        if sel_model:
            data_form["model"] = sel_model
        if sel_provider == "ollama" and sel_ollama_url.strip():
            data_form["ollama_base_url"] = sel_ollama_url.strip()
        if sel_provider == "ollama" and sel_ollama_api_key.strip():
            data_form["ollama_api_key"] = sel_ollama_api_key.strip()
        if st.session_state.get("fixed_params"):
            data_form["fixed_params"] = json.dumps(list(st.session_state["fixed_params"]))

        response = _post_analysis(tele_path, svm_path, tele_name, data_form)

    if response is None:
        return

    if response.status_code == 200:
        data = response.json()
        st.session_state["ai_analysis_data"] = data
        st.session_state["ai_telemetry_summary"] = data.get("telemetry_summary_sent", "")
        circuit = tele_name.split("-")[-2].strip() if "-" in tele_name else "Desconocido"
        st.session_state["ai_circuit_name"] = circuit
        backend_model = data.get("llm_model") or sel_model or "default"
        st.session_state["ai_model"] = f"{data.get('llm_provider', sel_provider)} / {backend_model}"
        st.session_state["ai_setup_data"] = setup_parser.parse_svm_content(svm_path)
    else:
        try:
            error_detail = response.json().get("detail")
        except Exception:
            error_detail = None
        msg = f"Error en el análisis ({response.status_code})"
        st.error(f"{msg}: {error_detail}" if error_detail else f"{msg}.")


def _post_analysis(tele_path: str, svm_path: str, tele_name: str, data_form: dict):
    import os  # noqa: PLC0415

    svm_name = st.session_state.get("svm_name") or os.path.basename(svm_path)

    if not os.path.exists(tele_path) or not os.path.exists(svm_path):
        st.error("No hay archivos locales de la sesión. Vuelve a cargarlos.")
        return None

    with open(tele_path, "rb") as tele_fh, open(svm_path, "rb") as svm_fh:
        files = {
            "telemetry_file": (tele_name, tele_fh),
            "svm_file": (svm_name, svm_fh),
        }
        return api_client.post_analyze_with_files(
            API_BASE_URL,
            st.session_state.get("client_session_id"),
            data_form,
            files,
            ANALYSIS_REQUEST_TIMEOUT,
        )


# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------


def _render_results(svm_path: str) -> None:  # noqa: ARG001
    data = st.session_state["ai_analysis_data"]

    llm_provider_used = data.get("llm_provider", "desconocido")
    llm_model_used = data.get("llm_model", "desconocido")
    st.caption(f"Proveedor/modelo usado en backend: {llm_provider_used} / {llm_model_used}")

    st.subheader("🏁 Análisis del Ingeniero de Conducción")
    st.info(data["driving_analysis"])

    _render_setup_recommendations(data)
    _render_agent_reasoning(data)


def _render_setup_recommendations(data: dict) -> None:
    if not data.get("full_setup") or not data["full_setup"].get("sections"):
        return

    st.subheader("⚙️ Setup Completo Recomendado por los ingenieros")
    for section in data["full_setup"]["sections"]:
        s_name = section.get("name", "Sección")
        s_items = section.get("items", [])
        changed_items = [
            it for it in s_items if str(it.get("current", "")) != str(it.get("new", ""))
        ]
        if not changed_items:
            continue
        with st.expander(f"🔩 {s_name} ({len(changed_items)} cambios)", expanded=True):
            rows = []
            for it in changed_items:
                param_name = it.get("parameter", "")
                if it.get("reanalyzed"):
                    param_name = f"🚀 {param_name}"
                rows.append(
                    {
                        "Parámetro": param_name,
                        "Actual": it.get("current", ""),
                        "Recomendado": it.get("new", ""),
                        "Motivo": it.get("reason", ""),
                    }
                )
            df_ai = pd.DataFrame(rows)
            st.table(df_ai.set_index("Parámetro"))


def _render_agent_reasoning(data: dict) -> None:
    setup_agent_reports = data.get("setup_agent_reports", [])
    agent_reports = setup_agent_reports or data.get("agent_reports", [])
    chief_reasoning = data.get("chief_reasoning", "")

    if not agent_reports and not chief_reasoning:
        return

    st.divider()
    st.subheader("💬 Razonamientos de los Agentes IA")
    st.info(
        "ℹ️ Esta sección muestra el **razonamiento interno** de cada agente. "
        "No es la tabla de cambios del setup — es la explicación técnica "
        "detrás de las recomendaciones.",
        icon="🧠",
    )

    if chief_reasoning:
        with st.expander("🎯 Ingeniero Jefe — Estrategia global", expanded=True):
            st.markdown(f"> {chief_reasoning.replace(chr(10), chr(10) + '> ')}")

    meaningful_reports = [
        r for r in (agent_reports or []) if r.get("summary", "").strip() or r.get("items", [])
    ]
    for report in meaningful_reports:
        sec_friendly = report.get("friendly_name") or report.get("name", "")
        sec_summary = report.get("summary", "").strip()
        sec_items = report.get("items", [])
        with st.expander(f"📝 {sec_friendly}", expanded=False):
            if sec_summary:
                st.markdown(f"> {sec_summary.replace(chr(10), chr(10) + '> ')}")
            if sec_items:
                st.markdown("---")
                for it in sec_items:
                    st.markdown(
                        f"**{it.get('parameter', '')}** → `{it.get('new_value', '')}`\n\n"
                        f"> _{it.get('reason', '')}_\n"
                    )
