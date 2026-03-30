"""Setup tab: fixed-params editor backed by the .svm file."""

from __future__ import annotations

import json
import os

import pandas as pd
import streamlit as st

from frontend import setup_parser
from frontend.config import FIXED_PARAMS_FILE, PARAM_MAPPING_FILE

_SKIP_SECTIONS = frozenset({"LEFTFENDER", "RIGHTFENDER"})
_SKIP_PARAMS = frozenset({"VehicleClassSetting", "UpgradeSetting"})


# ---------------------------------------------------------------------------
# Fixed-params persistence
# ---------------------------------------------------------------------------


def load_fixed_params() -> set:
    """Load the set of locked parameter names from disk."""
    if os.path.exists(FIXED_PARAMS_FILE):
        try:
            with open(FIXED_PARAMS_FILE, "r", encoding="utf-8") as fh:
                return set(json.load(fh))
        except Exception:
            pass
    return set()


def save_fixed_params(params_set: set) -> bool:
    """Persist the locked parameter names to disk."""
    try:
        os.makedirs(os.path.dirname(FIXED_PARAMS_FILE), exist_ok=True)
        with open(FIXED_PARAMS_FILE, "w", encoding="utf-8") as fh:
            json.dump(list(params_set), fh, indent=2, ensure_ascii=False)
        return True
    except Exception as exc:
        st.error(f"Error al guardar parámetros: {exc}")
        return False


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def render_setup_tab(svm_path: str) -> None:
    """Render the Setup tab contents for *svm_path*."""
    st.header("Configuración del Coche (.svm)")

    if "temp_fixed_params" not in st.session_state:
        st.session_state["temp_fixed_params"] = st.session_state["fixed_params"].copy()

    setup_data = setup_parser.parse_svm_content(svm_path)
    mapping = _load_param_mapping()

    with st.form("setup_fixed_params_form", border=False):
        save_col1, save_col2 = st.columns([1.5, 3.5])
        with save_col1:
            submitted = st.form_submit_button("💾 Guardar parámetros fijados", use_container_width=True)
        with save_col2:
            st.info(
                "Selecciona los parámetros que quieres fijar para que la IA sepa que no se "
                "tienen que modificar y pulsa el botón para guardar todos los cambios.",
                icon="ℹ️",
            )

        for section, params in setup_data.items():
            if section.upper() in _SKIP_SECTIONS:
                continue
            friendly_section = mapping.get("sections", {}).get(section, section)
            with st.expander(f"🔩 {friendly_section}"):
                rows = _build_section_rows(section, params, mapping)
                if rows:
                    st.session_state[f"rows_{section}"] = rows
                    df_setup = pd.DataFrame(rows)
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
                            "_internal_key": None,
                        },
                        disabled=["Parámetro", "Valor"],
                        hide_index=True,
                        key=f"editor_{section}",
                    )

        if submitted:
            _apply_fixed_params_changes(setup_data)

        has_rows = any(
            len(p) > 0
            for sec, p in setup_data.items()
            if sec.upper() not in _SKIP_SECTIONS
        )
        if not has_rows:
            st.caption("No hay parámetros configurados disponibles.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_param_mapping() -> dict:
    mapping: dict = {"sections": {}, "parameters": {}}
    if os.path.exists(PARAM_MAPPING_FILE):
        try:
            with open(PARAM_MAPPING_FILE, "r", encoding="utf-8") as fh:
                mapping = json.load(fh)
        except Exception:
            pass
    return mapping


def _clean_svm_value(val: str) -> str:
    val_str = str(val)
    if "//" in val_str:
        parts = val_str.split("//", 1)
        if len(parts) > 1:
            return parts[1].strip()
    return val_str.strip()


def _build_section_rows(section: str, params: dict, mapping: dict) -> list[dict]:
    rows = []
    for key, val in params.items():
        if key.startswith("Gear") and "Setting" in key:
            continue
        if key in _SKIP_PARAMS:
            continue
        friendly_param = mapping.get("parameters", {}).get(key, key)
        if friendly_param.startswith("Ajuste de Chasis") or key.startswith("ChassisAdj"):
            continue
        clean_v = _clean_svm_value(val)
        if not clean_v:
            continue
        is_fixed = key in st.session_state["temp_fixed_params"]
        rows.append(
            {
                "Fijar": is_fixed,
                "Parámetro": friendly_param,
                "Valor": clean_v,
                "_internal_key": key,
            }
        )
    return rows


def _apply_fixed_params_changes(setup_data: dict) -> None:
    new_fixed = st.session_state["fixed_params"].copy()
    for section in setup_data.keys():
        editor_key = f"editor_{section}"
        rows_key = f"rows_{section}"
        if editor_key not in st.session_state or rows_key not in st.session_state:
            continue
        changes = st.session_state[editor_key]
        rows = st.session_state[rows_key]
        for idx_str, change in changes.get("edited_rows", {}).items():
            idx = int(idx_str)
            if idx < len(rows):
                internal_key = rows[idx]["_internal_key"]
                if "Fijar" in change:
                    if change["Fijar"]:
                        new_fixed.add(internal_key)
                    else:
                        new_fixed.discard(internal_key)

    st.session_state["fixed_params"] = new_fixed
    st.session_state["temp_fixed_params"] = new_fixed.copy()
    if save_fixed_params(new_fixed):
        st.success("¡Parámetros guardados correctamente!")
        st.rerun()
