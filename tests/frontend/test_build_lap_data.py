"""Unit tests for _build_lap_data() in frontend/streamlit_app.py.

Streamlit runs module-level UI code at import time, so we mock the entire
streamlit package before importing the module under test.  The functions
under test (_build_lap_data, _lap_xy) are pure data-manipulation helpers
that don't depend on any live Streamlit state.
"""

import sys
from unittest.mock import MagicMock

# ── Streamlit mock (must happen before the first import of streamlit_app) ──
_st_mock = MagicMock()
_st_mock.session_state = {}         # real dict so get/set/contains work
_st_mock.file_uploader.return_value = None   # "no files" → sidebar stays empty
# Make context managers work (sidebar, form, spinner, …)
_st_mock.sidebar.__enter__ = lambda s: s
_st_mock.sidebar.__exit__ = lambda *a: False
sys.modules.setdefault("streamlit", _st_mock)
sys.modules.setdefault("streamlit.components", MagicMock())
sys.modules.setdefault("streamlit.components.v1", MagicMock())
# ── End mock ───────────────────────────────────────────────────────────────

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from frontend.streamlit_app import _build_lap_data, _lap_xy  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_lap_df(
    n: int = 100,
    include_gps: bool = True,
    include_brake: bool = True,
    include_throttle: bool = True,
    brake_values=None,
    throttle_values=None,
) -> pd.DataFrame:
    """Minimal lap DataFrame accepted by _build_lap_data()."""
    data: dict = {
        "Lap_Distance": np.linspace(0, 4500, n),
        "Ground_Speed": np.ones(n) * 120.0,
    }
    if include_gps:
        data["GPS_Longitude"] = np.linspace(135.7, 135.9, n)
        data["GPS_Latitude"] = np.linspace(34.8, 34.85, n)
    if include_brake:
        if brake_values is not None:
            data["Brake_Pos"] = np.array(brake_values[:n], dtype=float)
        else:
            data["Brake_Pos"] = np.linspace(0.0, 1.0, n)
    if include_throttle:
        if throttle_values is not None:
            data["Throttle_Pos"] = np.array(throttle_values[:n], dtype=float)
        else:
            data["Throttle_Pos"] = np.linspace(1.0, 0.0, n)
    return pd.DataFrame(data)


# ─────────────────────────────────────────────────────────────────────────────
# _lap_xy
# ─────────────────────────────────────────────────────────────────────────────

class TestLapXy:
    def test_returns_two_lists_of_same_length(self):
        df = _make_lap_df(n=10)
        xs, ys = _lap_xy(df, "GPS_Longitude", "GPS_Latitude")
        assert len(xs) == len(ys)
        assert len(xs) >= 10  # may have extra None breaks

    def test_missing_columns_returns_empty(self):
        df = pd.DataFrame({"other": [1, 2]})
        xs, ys = _lap_xy(df, "GPS_Longitude", "GPS_Latitude")
        assert xs == []
        assert ys == []

    def test_single_point_no_breaks(self):
        df = pd.DataFrame({
            "GPS_Longitude": [1.0],
            "GPS_Latitude": [2.0],
        })
        xs, ys = _lap_xy(df, "GPS_Longitude", "GPS_Latitude")
        assert xs == [1.0]
        assert ys == [2.0]


# ─────────────────────────────────────────────────────────────────────────────
# _build_lap_data — structure
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildLapDataStructure:
    def test_returns_none_without_lap_distance(self):
        df = pd.DataFrame({"Ground_Speed": [100.0]})
        assert _build_lap_data(df) is None

    def test_returns_dict_with_required_keys(self):
        df = _make_lap_df(include_gps=False)
        result = _build_lap_data(df)
        assert result is not None
        assert "max_dist" in result
        assert "channels" in result

    def test_max_dist_equals_last_value(self):
        df = _make_lap_df(n=50)
        result = _build_lap_data(df)
        assert abs(result["max_dist"] - 4500.0) < 1.0

    def test_channels_speed_present(self):
        df = _make_lap_df()
        result = _build_lap_data(df)
        assert "speed" in result["channels"]


# ─────────────────────────────────────────────────────────────────────────────
# _build_lap_data — map data with GPS
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildLapDataMap:
    def test_map_key_present_when_gps_available(self):
        df = _make_lap_df(n=60)
        result = _build_lap_data(df)
        assert "map" in result

    def test_map_key_absent_when_no_gps(self):
        df = _make_lap_df(n=60, include_gps=False)
        result = _build_lap_data(df)
        assert "map" not in result

    def test_map_contains_lon_lat_dist(self):
        df = _make_lap_df(n=60)
        m = _build_lap_data(df)["map"]
        assert "lon" in m
        assert "lat" in m
        assert "dist" in m

    def test_map_dist_length_matches_dataframe(self):
        n = 80
        df = _make_lap_df(n=n)
        m = _build_lap_data(df)["map"]
        assert len(m["dist"]) == n


# ─────────────────────────────────────────────────────────────────────────────
# _build_lap_data — brake / throttle arrays in map
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildLapDataMapBrakeThrottle:
    """Core tests for the gradient-map feature (Tarea A)."""

    def test_map_has_brake_array(self):
        df = _make_lap_df(n=60)
        m = _build_lap_data(df)["map"]
        assert "brake" in m, "map must contain 'brake' array"

    def test_map_has_throttle_array(self):
        df = _make_lap_df(n=60)
        m = _build_lap_data(df)["map"]
        assert "throttle" in m, "map must contain 'throttle' array"

    def test_map_has_raw_lon_and_raw_lat(self):
        df = _make_lap_df(n=60)
        m = _build_lap_data(df)["map"]
        assert "raw_lon" in m
        assert "raw_lat" in m

    def test_brake_array_length_matches_dist(self):
        n = 70
        df = _make_lap_df(n=n)
        m = _build_lap_data(df)["map"]
        assert len(m["brake"]) == n

    def test_throttle_array_length_matches_dist(self):
        n = 70
        df = _make_lap_df(n=n)
        m = _build_lap_data(df)["map"]
        assert len(m["throttle"]) == n

    def test_raw_lon_length_matches_dist(self):
        n = 70
        df = _make_lap_df(n=n)
        m = _build_lap_data(df)["map"]
        assert len(m["raw_lon"]) == n

    def test_brake_scaled_0_to_100(self):
        """Brake_Pos values (0-1) must be scaled to 0-100 in the map."""
        n = 10
        # Brake_Pos = [0.0, 0.1, ..., 0.9] → expected: [0, 10, ..., 90]
        brake_vals = [i / 10 for i in range(n)]
        df = _make_lap_df(n=n, brake_values=brake_vals, throttle_values=[0.0] * n)
        m = _build_lap_data(df)["map"]
        assert m["brake"][0] == pytest.approx(0.0, abs=0.1)
        assert m["brake"][-1] == pytest.approx(90.0, abs=0.1)

    def test_throttle_scaled_0_to_100(self):
        """Throttle_Pos values (0-1) must be scaled to 0-100 in the map."""
        n = 10
        throttle_vals = [i / 10 for i in range(n)]
        df = _make_lap_df(n=n, throttle_values=throttle_vals, brake_values=[0.0] * n)
        m = _build_lap_data(df)["map"]
        assert m["throttle"][0] == pytest.approx(0.0, abs=0.1)
        assert m["throttle"][-1] == pytest.approx(90.0, abs=0.1)

    def test_brake_zeros_when_no_brake_column(self):
        df = _make_lap_df(n=20, include_brake=False)
        m = _build_lap_data(df)["map"]
        assert "brake" in m
        assert all(v == 0.0 for v in m["brake"])

    def test_throttle_zeros_when_no_throttle_column(self):
        df = _make_lap_df(n=20, include_throttle=False)
        m = _build_lap_data(df)["map"]
        assert "throttle" in m
        assert all(v == 0.0 for v in m["throttle"])

    def test_nan_brake_replaced_with_zero(self):
        n = 5
        brake_vals = [0.5, float("nan"), 0.3, float("nan"), 1.0]
        df = _make_lap_df(n=n, brake_values=brake_vals)
        m = _build_lap_data(df)["map"]
        assert m["brake"][1] == 0.0
        assert m["brake"][3] == 0.0


