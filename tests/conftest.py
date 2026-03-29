"""Shared fixtures for all unit tests."""
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_svm_content() -> str:
    return (
        "[GENERAL]\n"
        "// This is a comment\n"
        "FuelSetting=50//L\n"
        "Gear1Setting=1\n"
        "\n"
        "[SUSPENSION]\n"
        "SpringSetting=100//N/mm\n"
        "CamberSetting=-3.0\n"
    )


@pytest.fixture
def sample_setup_dict() -> dict:
    return {
        "GENERAL": {"FuelSetting": "50//L"},
        "SUSPENSION": {"SpringSetting": "100//N/mm"},
        "BASIC": {"ignored": "1"},
        "LEFTFENDER": {"also_ignored": "2"},
        "RIGHTFENDER": {"also_ignored": "3"},
    }


def _make_lap_block(lap_num: int, n_samples: int, dist_start: float = 0.0, dist_end: float = 5000.0) -> pd.DataFrame:
    return pd.DataFrame({
        "Lap Number": [lap_num] * n_samples,
        "Lap Distance": np.linspace(dist_start, dist_end, n_samples),
        "Session_Elapsed_Time": np.linspace(0, 90, n_samples) + (lap_num - 1) * 90,
        "Ground Speed": np.random.uniform(50, 200, n_samples),
    })


@pytest.fixture
def sample_lap_dataframe() -> pd.DataFrame:
    """3 full laps (100 samples each, dist 0–5000) + 1 out-lap (lap 0, 10 samples)."""
    out_lap = _make_lap_block(0, 10, dist_end=500.0)
    lap1 = _make_lap_block(1, 100)
    lap2 = _make_lap_block(2, 100)
    lap3 = _make_lap_block(3, 100)
    return pd.concat([out_lap, lap1, lap2, lap3], ignore_index=True)


@pytest.fixture
def sample_multi_speed_dataframe() -> pd.DataFrame:
    """Like sample_lap_dataframe but with noisy GPS columns."""
    out_lap = _make_lap_block(0, 10, dist_end=500.0)
    lap1 = _make_lap_block(1, 100)
    lap2 = _make_lap_block(2, 100)
    lap3 = _make_lap_block(3, 100)
    df = pd.concat([out_lap, lap1, lap2, lap3], ignore_index=True)
    n = len(df)
    rng = np.random.default_rng(42)
    df["GPS Latitude"] = 40.0 + rng.normal(0, 0.001, n)
    df["GPS Longitude"] = -3.0 + rng.normal(0, 0.001, n)
    # Inject a few zeros to test the replace-0-with-NaN logic
    df.loc[5, "GPS Latitude"] = 0.0
    df.loc[10, "GPS Longitude"] = 0.0
    return df
