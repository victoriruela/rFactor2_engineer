"""Unit tests for _build_cockpit_data() in frontend/streamlit_app.py.

Uses the same Streamlit mocking pattern as test_build_lap_data.py.
"""

import sys
from unittest.mock import MagicMock

# ── Streamlit mock (must happen before the first import of streamlit_app) ──
_st_mock = MagicMock()
_st_mock.session_state = {}
_st_mock.file_uploader.return_value = None
_st_mock.sidebar.__enter__ = lambda s: s
_st_mock.sidebar.__exit__ = lambda *a: False
sys.modules.setdefault("streamlit", _st_mock)
sys.modules.setdefault("streamlit.components", MagicMock())
sys.modules.setdefault("streamlit.components.v1", MagicMock())
# ── End mock ───────────────────────────────────────────────────────────────

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from frontend.streamlit_app import _build_cockpit_data  # noqa: E402
from frontend.streamlit_app import render_3d_cockpit  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_cockpit_df(
    n: int = 100,
    include_physics: bool = True,
    include_ride_height: bool = True,
) -> pd.DataFrame:
    """Minimal lap DataFrame with channels needed for cockpit replay."""
    data = {
        "Lap_Distance": np.linspace(0, 4500, n),
        "Ground_Speed": np.random.uniform(80, 200, n),
        "Throttle_Pos": np.random.uniform(0, 1, n),
        "Brake_Pos": np.random.uniform(0, 1, n),
        "Gear": np.random.choice([1, 2, 3, 4, 5, 6], n),
        "Engine_RPM": np.random.uniform(3000, 9000, n),
        "Steering_Wheel_Position": np.random.uniform(-90, 90, n),
    }
    if include_physics:
        data["Body_Pitch"] = np.random.uniform(-0.05, 0.05, n)
        data["Body_Roll"] = np.random.uniform(-0.05, 0.05, n)
        data["G_Force_Lat"] = np.random.uniform(-2, 2, n)
        data["G_Force_Long"] = np.random.uniform(-2, 2, n)
    if include_ride_height:
        for w in ["FL", "FR", "RL", "RR"]:
            data[f"Ride_Height_{w}"] = np.random.uniform(0.03, 0.06, n)
    return pd.DataFrame(data)


# ─────────────────────────────────────────────────────────────────────────────
# _build_cockpit_data — basic structure
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildCockpitDataStructure:
    def test_returns_none_without_lap_distance(self):
        df = pd.DataFrame({"Ground_Speed": [100.0]})
        assert _build_cockpit_data(df) is None

    def test_returns_dict_with_all_required_keys(self):
        df = _make_cockpit_df()
        result = _build_cockpit_data(df)
        assert result is not None
        required_keys = [
            "lap_distance", "speed", "throttle", "brake", "gear",
            "rpm", "steering",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_all_arrays_same_length(self):
        n = 80
        df = _make_cockpit_df(n=n)
        result = _build_cockpit_data(df)
        expected_len = len(result["lap_distance"])
        for key, val in result.items():
            assert len(val) == expected_len, (
                f"Array '{key}' has length {len(val)}, expected {expected_len}"
            )

    def test_lap_distance_values_match_dataframe(self):
        n = 50
        df = _make_cockpit_df(n=n)
        result = _build_cockpit_data(df)
        assert len(result["lap_distance"]) == n
        assert result["lap_distance"][0] == pytest.approx(0.0, abs=0.1)
        assert result["lap_distance"][-1] == pytest.approx(4500.0, abs=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# _build_cockpit_data — speed units (km/h)
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildCockpitDataSpeed:
    def test_speed_is_in_kmh(self):
        """Ground_Speed from MoTeC is in km/h already, so values pass through."""
        n = 10
        df = _make_cockpit_df(n=n)
        df["Ground_Speed"] = np.full(n, 150.0)
        result = _build_cockpit_data(df)
        assert all(v == pytest.approx(150.0, abs=0.01) for v in result["speed"])


# ─────────────────────────────────────────────────────────────────────────────
# _build_cockpit_data — physics channels (optional)
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildCockpitDataPhysics:
    def test_physics_channels_present_when_available(self):
        df = _make_cockpit_df(include_physics=True)
        result = _build_cockpit_data(df)
        for key in ["body_pitch", "body_roll", "g_force_lat", "g_force_long"]:
            assert key in result, f"Missing physics key: {key}"

    def test_physics_channels_zero_when_missing(self):
        """When physics columns are absent, arrays should be all zeros."""
        df = _make_cockpit_df(include_physics=False)
        result = _build_cockpit_data(df)
        for key in ["body_pitch", "body_roll", "g_force_lat", "g_force_long"]:
            assert key in result, f"Missing physics key: {key}"
            assert all(v == 0.0 for v in result[key]), (
                f"Expected zeros for '{key}' when column is missing"
            )


# ─────────────────────────────────────────────────────────────────────────────
# _build_cockpit_data — ride height (averaged)
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildCockpitDataRideHeight:
    def test_ride_height_avg_present(self):
        df = _make_cockpit_df(include_ride_height=True)
        result = _build_cockpit_data(df)
        assert "ride_height_avg" in result

    def test_ride_height_avg_is_mean_of_four_wheels(self):
        n = 5
        df = _make_cockpit_df(n=n, include_ride_height=False)
        # Set known ride heights
        df["Ride_Height_FL"] = [0.04] * n
        df["Ride_Height_FR"] = [0.06] * n
        df["Ride_Height_RL"] = [0.04] * n
        df["Ride_Height_RR"] = [0.06] * n
        result = _build_cockpit_data(df)
        expected_avg = 0.05
        for v in result["ride_height_avg"]:
            assert v == pytest.approx(expected_avg, abs=0.001)

    def test_ride_height_avg_zeros_when_missing(self):
        df = _make_cockpit_df(include_ride_height=False)
        result = _build_cockpit_data(df)
        assert "ride_height_avg" in result
        assert all(v == 0.0 for v in result["ride_height_avg"])


# ─────────────────────────────────────────────────────────────────────────────
# _build_cockpit_data — NaN handling
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildCockpitDataNaN:
    def test_nan_values_replaced_with_zero(self):
        n = 5
        df = _make_cockpit_df(n=n)
        df.loc[2, "Ground_Speed"] = float("nan")
        df.loc[3, "Throttle_Pos"] = float("nan")
        result = _build_cockpit_data(df)
        assert result["speed"][2] == 0.0
        assert result["throttle"][3] == 0.0

    def test_no_none_values_in_output(self):
        """All output arrays must contain plain floats/ints, no None."""
        df = _make_cockpit_df(n=20)
        result = _build_cockpit_data(df)
        for key, arr in result.items():
            for i, v in enumerate(arr):
                assert v is not None, f"None found in '{key}' at index {i}"


# ─────────────────────────────────────────────────────────────────────────────
# _build_cockpit_data — throttle/brake normalization
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildCockpitDataNormalization:
    def test_throttle_is_0_to_1_range(self):
        n = 10
        df = _make_cockpit_df(n=n)
        df["Throttle_Pos"] = np.linspace(0, 1, n)
        result = _build_cockpit_data(df)
        assert all(0.0 <= v <= 1.0 for v in result["throttle"])

    def test_brake_is_0_to_1_range(self):
        n = 10
        df = _make_cockpit_df(n=n)
        df["Brake_Pos"] = np.linspace(0, 1, n)
        result = _build_cockpit_data(df)
        assert all(0.0 <= v <= 1.0 for v in result["brake"])

    def test_gear_is_integer_list(self):
        df = _make_cockpit_df(n=10)
        result = _build_cockpit_data(df)
        for v in result["gear"]:
            assert isinstance(v, (int, float))
            assert v == int(v)


# ─────────────────────────────────────────────────────────────────────────────
# T6: Bidirectional sync integration in cockpit HTML
# ─────────────────────────────────────────────────────────────────────────────

class TestCockpitSyncIntegration:
    """Verify that render_3d_cockpit() output includes T6 sync hooks."""

    @pytest.fixture()
    def cockpit_html(self):
        track = {
            "name": "test",
            "source": "test",
            "points": [
                {"x": 0, "y": 0, "z": 0, "width_left": 5, "width_right": 5},
                {"x": 10, "y": 0, "z": 0, "width_left": 5, "width_right": 5},
                {"x": 20, "y": 0, "z": 10, "width_left": 5, "width_right": 5},
            ],
        }
        return render_3d_cockpit(None, track)

    def test_cockpit_emits_cockpit_sync_on_scrub(self, cockpit_html):
        """Scrub handler should postMessage cockpitSync to parent."""
        assert "cockpitSync" in cockpit_html

    def test_cockpit_emits_cockpit_sync_on_playback(self, cockpit_html):
        """Animation loop should postMessage cockpitSync during playback."""
        assert "cockpitSync" in cockpit_html
        # Specifically in the playback section
        assert "emit position to parent for 2D chart sync during playback" in cockpit_html

    def test_cockpit_listens_for_chart_sync(self, cockpit_html):
        """Cockpit should listen for chartSync messages."""
        assert "chartSync" in cockpit_html

    def test_cockpit_has_sync_in_progress_guard(self, cockpit_html):
        """setCockpitPosition should use _syncInProgress to avoid loops."""
        assert "_syncInProgress" in cockpit_html

    def test_cockpit_no_track_returns_placeholder(self):
        """Without track data, returns a simple placeholder."""
        html = render_3d_cockpit(None, None)
        assert "No track data" in html
        assert "cockpitSync" not in html
