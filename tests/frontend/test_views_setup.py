"""Unit tests for frontend/views/setup_view.py pure functions.

Streamlit is mocked before import to avoid UI execution at import time.
"""
import json
import sys
from unittest.mock import MagicMock

# ── Streamlit mock (must happen before any import of the module under test) ──
if "streamlit" not in sys.modules:
    _m = MagicMock()
    _m.session_state = {}
    sys.modules["streamlit"] = _m
if "streamlit.components" not in sys.modules:
    sys.modules["streamlit.components"] = MagicMock()
if "streamlit.components.v1" not in sys.modules:
    sys.modules["streamlit.components.v1"] = MagicMock()
# Authoritative reference — same object that setup_view.py imported as `st`
_st_mock = sys.modules["streamlit"]
if not isinstance(getattr(_st_mock, "session_state", None), dict):
    _st_mock.session_state = {}
# ─────────────────────────────────────────────────────────────────────────────

from frontend.views.setup_view import (  # noqa: E402
    _build_section_rows,
    _clean_svm_value,
    load_fixed_params,
    save_fixed_params,
    _load_param_mapping,
)


# ---------------------------------------------------------------------------
# _clean_svm_value
# ---------------------------------------------------------------------------

class TestCleanSvmValue:
    def test_value_with_double_slash(self):
        assert _clean_svm_value("223//N/mm") == "N/mm"

    def test_value_with_space_before_comment(self):
        assert _clean_svm_value("50 // L") == "L"

    def test_plain_value_no_comment(self):
        assert _clean_svm_value("42") == "42"

    def test_empty_string(self):
        assert _clean_svm_value("") == ""

    def test_only_double_slash(self):
        # Right side of "//" is empty string -> strip gives ""
        assert _clean_svm_value("//") == ""

    def test_multiple_slashes_takes_first_split(self):
        # Only splits on first "//"
        result = _clean_svm_value("100//N/mm//extra")
        assert result == "N/mm//extra"


# ---------------------------------------------------------------------------
# load_fixed_params
# ---------------------------------------------------------------------------

class TestLoadFixedParams:
    def test_returns_empty_set_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("frontend.views.setup_view.FIXED_PARAMS_FILE", str(tmp_path / "missing.json"))
        result = load_fixed_params()
        assert result == set()

    def test_loads_params_from_file(self, tmp_path, monkeypatch):
        fp = tmp_path / "fixed.json"
        fp.write_text(json.dumps(["CamberSetting", "SpringSetting"]), encoding="utf-8")
        monkeypatch.setattr("frontend.views.setup_view.FIXED_PARAMS_FILE", str(fp))
        result = load_fixed_params()
        assert result == {"CamberSetting", "SpringSetting"}

    def test_returns_empty_set_on_corrupt_file(self, tmp_path, monkeypatch):
        fp = tmp_path / "bad.json"
        fp.write_bytes(b"\xff\xfe garbage")
        monkeypatch.setattr("frontend.views.setup_view.FIXED_PARAMS_FILE", str(fp))
        result = load_fixed_params()
        assert result == set()


# ---------------------------------------------------------------------------
# save_fixed_params
# ---------------------------------------------------------------------------

class TestSaveFixedParams:
    def test_saves_and_reloads(self, tmp_path, monkeypatch):
        fp = tmp_path / "core" / "fixed_params.json"
        monkeypatch.setattr("frontend.views.setup_view.FIXED_PARAMS_FILE", str(fp))
        params = {"CamberSetting", "ToeInSetting"}
        assert save_fixed_params(params) is True
        assert fp.exists()
        loaded = json.loads(fp.read_text(encoding="utf-8"))
        assert set(loaded) == params

    def test_saves_empty_set(self, tmp_path, monkeypatch):
        fp = tmp_path / "core" / "fixed_params.json"
        monkeypatch.setattr("frontend.views.setup_view.FIXED_PARAMS_FILE", str(fp))
        assert save_fixed_params(set()) is True
        assert json.loads(fp.read_text()) == []


# ---------------------------------------------------------------------------
# _load_param_mapping
# ---------------------------------------------------------------------------

class TestLoadParamMapping:
    def test_returns_empty_mapping_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "frontend.views.setup_view.PARAM_MAPPING_FILE", str(tmp_path / "missing.json")
        )
        result = _load_param_mapping()
        assert result == {"sections": {}, "parameters": {}}

    def test_loads_mapping_from_file(self, tmp_path, monkeypatch):
        mapping_data = {
            "sections": {"FRONTLEFT": "Delantero Izquierdo"},
            "parameters": {"CamberSetting": "Caída"},
        }
        fp = tmp_path / "param_mapping.json"
        fp.write_text(json.dumps(mapping_data), encoding="utf-8")
        monkeypatch.setattr("frontend.views.setup_view.PARAM_MAPPING_FILE", str(fp))
        result = _load_param_mapping()
        assert result["sections"]["FRONTLEFT"] == "Delantero Izquierdo"
        assert result["parameters"]["CamberSetting"] == "Caída"

    def test_returns_empty_mapping_on_corrupt_file(self, tmp_path, monkeypatch):
        fp = tmp_path / "bad.json"
        fp.write_bytes(b"not json")
        monkeypatch.setattr("frontend.views.setup_view.PARAM_MAPPING_FILE", str(fp))
        result = _load_param_mapping()
        assert result == {"sections": {}, "parameters": {}}


# ---------------------------------------------------------------------------
# _build_section_rows
# ---------------------------------------------------------------------------

class TestBuildSectionRows:
    MAPPING = {
        "sections": {},
        "parameters": {"CamberSetting": "Caída (Camber)", "SpringSetting": "Muelle"},
    }

    def setup_method(self):
        """Reset mock session_state before each test."""
        _st_mock.session_state.clear()
        _st_mock.session_state["temp_fixed_params"] = set()

    def test_basic_row_building(self):
        params = {"CamberSetting": "-2.5//degrees"}
        rows = _build_section_rows("FRONTLEFT", params, self.MAPPING)
        assert len(rows) == 1
        row = rows[0]
        assert row["Parámetro"] == "Caída (Camber)"
        assert row["Valor"] == "degrees"
        assert row["_internal_key"] == "CamberSetting"
        assert row["Fijar"] is False

    def test_fixed_param_is_checked(self):
        _st_mock.session_state["temp_fixed_params"] = {"CamberSetting"}
        params = {"CamberSetting": "-2.5//degrees"}
        rows = _build_section_rows("FRONTLEFT", params, self.MAPPING)
        assert rows[0]["Fijar"] is True

    def test_skips_gear_settings(self):
        params = {"Gear1Setting": "3.5", "SpringSetting": "200//N/mm"}
        rows = _build_section_rows("DRIVELINE", params, self.MAPPING)
        keys = [r["_internal_key"] for r in rows]
        assert "Gear1Setting" not in keys
        assert "SpringSetting" in keys

    def test_skips_vehicle_class_setting(self):
        params = {"VehicleClassSetting": "0", "CamberSetting": "-2.5//degrees"}
        rows = _build_section_rows("GENERAL", params, self.MAPPING)
        keys = [r["_internal_key"] for r in rows]
        assert "VehicleClassSetting" not in keys

    def test_skips_chassis_adj(self):
        params = {"ChassisAdjFront": "5", "CamberSetting": "-2.5//degrees"}
        rows = _build_section_rows("SUSPENSION", params, self.MAPPING)
        keys = [r["_internal_key"] for r in rows]
        assert "ChassisAdjFront" not in keys

    def test_skips_empty_value_after_clean(self):
        params = {"CamberSetting": "//"}  # cleans to ""
        rows = _build_section_rows("FRONTLEFT", params, self.MAPPING)
        assert rows == []

    def test_uses_internal_key_when_no_friendly_name(self):
        params = {"UnknownParam": "42"}
        rows = _build_section_rows("GENERAL", params, self.MAPPING)
        assert rows[0]["Parámetro"] == "UnknownParam"

    def test_plain_value_no_comment(self):
        params = {"SpringSetting": "200"}
        rows = _build_section_rows("SUSPENSION", params, self.MAPPING)
        assert rows[0]["Valor"] == "200"
