"""Unit tests for frontend/views/telemetry_view.py pure functions."""
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

# ── No Streamlit calls in telemetry_view, but imported modules may pull it ──
sys.modules.setdefault("streamlit", MagicMock())
sys.modules.setdefault("streamlit.components", MagicMock())
sys.modules.setdefault("streamlit.components.v1", MagicMock())

from frontend.views.telemetry_view import _fmt_lap, compute_fastest_lap  # noqa: E402


# ---------------------------------------------------------------------------
# _fmt_lap
# ---------------------------------------------------------------------------

class TestFmtLap:
    def test_under_one_minute(self):
        # 45.0 seconds → "0:45:000"
        assert _fmt_lap(45.0) == "0:45:000"

    def test_over_one_minute(self):
        # 90.0 s → 1 min 30 s → "1:30:000"
        assert _fmt_lap(90.0) == "1:30:000"

    def test_with_fractional_seconds(self):
        # 75.3 s → 1 m 15.3 s → tenths = round(0.3*10)=3 → "1:15:300"
        assert _fmt_lap(75.3) == "1:15:300"

    def test_zero(self):
        assert _fmt_lap(0.0) == "0:00:000"

    def test_exactly_one_minute(self):
        assert _fmt_lap(60.0) == "1:00:000"


# ---------------------------------------------------------------------------
# compute_fastest_lap
# ---------------------------------------------------------------------------

def _make_df(laps_data: dict, use_last_laptime: bool = True) -> pd.DataFrame:
    """Build a minimal DataFrame for testing compute_fastest_lap.

    laps_data: {lap_num: (last_laptime, elapsed_start, elapsed_end)}
    """
    rows = []
    for lap_num, (lt, t_start, t_end) in laps_data.items():
        rows.append({
            "Lap_Number": lap_num,
            "Last_Laptime": lt if use_last_laptime else 0,
            "Session_Elapsed_Time": t_start,
        })
        rows.append({
            "Lap_Number": lap_num,
            "Last_Laptime": lt if use_last_laptime else 0,
            "Session_Elapsed_Time": t_end,
        })
    return pd.DataFrame(rows)


class TestComputeFastestLap:
    def test_uses_last_laptime_when_available(self):
        # lap 1=80s, lap 2=75s → fastest=2
        df = _make_df({1: (80.0, 0, 80), 2: (75.0, 80, 155)})
        lap_times, fastest = compute_fastest_lap(df, [1, 2])
        assert lap_times[1] == 80.0
        assert lap_times[2] == 75.0
        assert fastest == 2

    def test_fallback_to_elapsed_time(self):
        # No Last_Laptime column
        df = pd.DataFrame([
            {"Lap_Number": 1, "Session_Elapsed_Time": 0.0},
            {"Lap_Number": 1, "Session_Elapsed_Time": 90.0},
            {"Lap_Number": 2, "Session_Elapsed_Time": 90.0},
            {"Lap_Number": 2, "Session_Elapsed_Time": 170.0},
        ])
        lap_times, fastest = compute_fastest_lap(df, [1, 2])
        assert lap_times[1] == pytest.approx(90.0)
        assert lap_times[2] == pytest.approx(80.0)
        assert fastest == 2

    def test_skips_last_laptime_zero(self):
        # last_laptime=0 should fall through to elapsed time
        df = pd.DataFrame([
            {"Lap_Number": 1, "Last_Laptime": 0, "Session_Elapsed_Time": 0.0},
            {"Lap_Number": 1, "Last_Laptime": 0, "Session_Elapsed_Time": 88.0},
        ])
        lap_times, fastest = compute_fastest_lap(df, [1])
        assert lap_times[1] == pytest.approx(88.0)
        assert fastest == 1

    def test_empty_laps_list(self):
        df = pd.DataFrame(columns=["Lap_Number", "Last_Laptime"])
        lap_times, fastest = compute_fastest_lap(df, [])
        assert lap_times == {}
        assert fastest is None

    def test_single_lap(self):
        df = _make_df({1: (95.5, 0, 95.5)})
        lap_times, fastest = compute_fastest_lap(df, [1])
        assert fastest == 1
        assert lap_times[1] == 95.5

    def test_fastest_is_minimum(self):
        df = _make_df({1: (100.0, 0, 100), 2: (99.0, 100, 199), 3: (98.5, 199, 297.5)})
        _, fastest = compute_fastest_lap(df, [1, 2, 3])
        assert fastest == 3

    def test_missing_lap_in_df_does_not_crash(self):
        # Only lap 1 exists in df, but we ask for [1, 2]
        df = _make_df({1: (80.0, 0, 80)})
        lap_times, fastest = compute_fastest_lap(df, [1, 2])
        assert 2 not in lap_times
        assert fastest == 1
