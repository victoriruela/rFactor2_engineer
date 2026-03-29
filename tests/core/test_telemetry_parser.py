"""Unit tests for app/core/telemetry_parser.py"""
import io
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from app.core.telemetry_parser import (
    _filter_incomplete_laps,
    parse_csv_file,
    parse_svm_file,
    parse_mat_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_csv_file(tmp_path: Path, data_rows: list[list], headers: list[str] | None = None) -> Path:
    """Write a MoTeC-style CSV (14 blank lines + header + units + data)."""
    if headers is None:
        headers = ["Lap Number", "Lap Distance", "Ground Speed", "GPS Latitude", "GPS Longitude"]
    p = tmp_path / "test.csv"
    lines = [""] * 14  # metadata lines
    lines.append(",".join(headers))       # line 15: headers
    lines.append(",".join([""] * len(headers)))  # line 16: units
    for row in data_rows:
        lines.append(",".join(str(v) for v in row))
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _make_svm_file(tmp_path: Path, content: str, encoding: str = "utf-8") -> Path:
    p = tmp_path / "test.svm"
    p.write_text(content, encoding=encoding)
    return p


# ---------------------------------------------------------------------------
# CSV tests
# ---------------------------------------------------------------------------

class TestParseCsvFile:
    def test_basic_returns_dataframe(self, tmp_path):
        rows = [[1, 0, 100, 40.0, -3.0], [1, 100, 110, 40.001, -3.001]]
        p = _make_csv_file(tmp_path, rows)
        df = parse_csv_file(str(p))
        assert isinstance(df, pd.DataFrame)
        assert "Lap Number" in df.columns
        assert "Ground Speed" in df.columns
        assert len(df) == 2

    def test_numeric_coercion_and_empty_row_drop(self, tmp_path):
        rows = [[1, 0, "abc", 40.0, -3.0], ["", "", "", "", ""]]
        p = _make_csv_file(tmp_path, rows)
        df = parse_csv_file(str(p))
        # "abc" should become NaN; fully-empty row should be dropped
        assert df["Ground Speed"].isna().any()
        assert len(df) == 1  # only one valid row

    def test_gps_smoothing_removes_zeros(self, tmp_path):
        gps_lat = [40.0] * 10
        gps_lon = [-3.0] * 10
        gps_lat[3] = 0.0  # inject zero
        rows = [[1, i * 10, 100 + i, lat, lon]
                for i, (lat, lon) in enumerate(zip(gps_lat, gps_lon))]
        p = _make_csv_file(tmp_path, rows)
        df = parse_csv_file(str(p))
        # After GPS smoothing, zeros should have been replaced
        assert (df["GPS Latitude"] != 0.0).all()

    def test_missing_headers_raises(self, tmp_path):
        p = tmp_path / "short.csv"
        p.write_text("line1\nline2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Error parseando CSV"):
            parse_csv_file(str(p))

    def test_empty_data_raises(self, tmp_path):
        p = _make_csv_file(tmp_path, [])  # no data rows
        with pytest.raises(ValueError, match="no contiene datos válidos"):
            parse_csv_file(str(p))


# ---------------------------------------------------------------------------
# SVM tests
# ---------------------------------------------------------------------------

class TestParseSvmFile:
    SVM_CONTENT = textwrap.dedent("""\
        [GENERAL]
        // This is a comment
        FuelSetting=50//L
        Gear1Setting=1
        [SUSPENSION]
        SpringSetting=100//N/mm
        CamberSetting=-3.0
    """)

    def test_basic_sections_parsed(self, tmp_path):
        p = _make_svm_file(tmp_path, self.SVM_CONTENT)
        result = parse_svm_file(str(p))
        assert "GENERAL" in result
        assert "SUSPENSION" in result
        assert result["GENERAL"]["FuelSetting"] == "50//L"
        assert result["SUSPENSION"]["CamberSetting"] == "-3.0"

    def test_utf16_encoding(self, tmp_path):
        p = _make_svm_file(tmp_path, self.SVM_CONTENT, encoding="utf-16")
        result = parse_svm_file(str(p))
        assert "GENERAL" in result

    def test_comments_not_in_output(self, tmp_path):
        p = _make_svm_file(tmp_path, self.SVM_CONTENT)
        result = parse_svm_file(str(p))
        for section in result.values():
            for key in section:
                assert not key.startswith("//")

    def test_inline_comment_preserved_in_value(self, tmp_path):
        p = _make_svm_file(tmp_path, self.SVM_CONTENT)
        result = parse_svm_file(str(p))
        # Inline comment is NOT stripped here — that's AIAngineer._clean_value's job
        assert "50//L" == result["GENERAL"]["FuelSetting"]

    def test_empty_file_raises(self, tmp_path):
        p = _make_svm_file(tmp_path, "// only a comment\n\n")
        with pytest.raises(ValueError, match="Error parseando .svm"):
            parse_svm_file(str(p))


# ---------------------------------------------------------------------------
# _filter_incomplete_laps tests
# ---------------------------------------------------------------------------

class TestFilterIncompleteLaps:
    def _df(self, laps: dict[int, int], dist_per_sample: float = 50.0) -> pd.DataFrame:
        """Build a DataFrame from {lap_num: n_samples}."""
        frames = []
        for lap, n in laps.items():
            frames.append(pd.DataFrame({
                "Lap Number": [lap] * n,
                "Lap Distance": np.linspace(0, n * dist_per_sample, n),
                "Session_Elapsed_Time": np.linspace(0, n * 0.9, n),
            }))
        return pd.concat(frames, ignore_index=True)

    def test_lap_zero_excluded(self, sample_lap_dataframe):
        result = _filter_incomplete_laps(sample_lap_dataframe)
        assert 0 not in result["Lap Number"].values

    def test_short_lap_removed(self):
        # Lap 2 has only 50% of max distance → should be removed
        df = self._df({1: 100, 2: 50, 3: 100})
        result = _filter_incomplete_laps(df)
        assert 2 not in result["Lap Number"].values
        assert 1 in result["Lap Number"].values
        assert 3 in result["Lap Number"].values

    def test_single_lap_returned_as_is(self):
        df = self._df({1: 100})
        result = _filter_incomplete_laps(df)
        assert list(result["Lap Number"].unique()) == [1]

    def test_no_distance_col_uses_sample_count(self):
        # DataFrame without Lap Distance — should use sample count
        frames = [
            pd.DataFrame({"Lap Number": [1] * 100, "Ground Speed": np.ones(100)}),
            pd.DataFrame({"Lap Number": [2] * 50,  "Ground Speed": np.ones(50)}),
        ]
        df = pd.concat(frames, ignore_index=True)
        result = _filter_incomplete_laps(df)
        assert 2 not in result["Lap Number"].values
        assert 1 in result["Lap Number"].values

    def test_duration_outlier_removed(self):
        # 3 normal laps (100 samples, duration ~90s) + 1 very long lap (200 samples, ~200s)
        frames = []
        for lap in range(1, 4):
            n = 100
            frames.append(pd.DataFrame({
                "Lap Number": [lap] * n,
                "Lap Distance": np.linspace(0, 5000, n),
                "Session_Elapsed_Time": np.linspace(0, 90, n) + (lap - 1) * 90,
            }))
        # Lap 4: same distance but takes 300s (> 110% of 90s median)
        n = 100
        frames.append(pd.DataFrame({
            "Lap Number": [4] * n,
            "Lap Distance": np.linspace(0, 5000, n),
            "Session_Elapsed_Time": np.linspace(270, 570, n),  # 300s duration
        }))
        df = pd.concat(frames, ignore_index=True)
        result = _filter_incomplete_laps(df)
        assert 4 not in result["Lap Number"].values


# ---------------------------------------------------------------------------
# .mat tests (scipy mocked)
# ---------------------------------------------------------------------------

class TestParseMatFile:
    # WHY we mock scipy.io.loadmat here (and why it is CORRECT):
    #
    # parse_mat_file uses `scipy.io.loadmat(struct_as_record=False, squeeze_me=True)`.
    # Real MoTeC .mat files use a MATLAB struct format that scipy returns as mat_struct
    # objects with a `.Value` attribute. We cannot reproduce this exact binary format
    # with scipy.io.savemat (which writes plain arrays, not structs) without actual
    # MoTeC-exported files. Our MagicMock with `.Value = np.array(...)` is structurally
    # identical to what scipy returns, so we are testing OUR code's logic correctly.
    # We trust scipy itself — it is a well-tested external library.
    def _mock_mat(self, mocker, channels: dict) -> None:
        """Patch scipy.io.loadmat to return mock structs with .Value."""
        def _make_struct(arr):
            s = MagicMock()
            s.Value = arr
            return s

        fake_mat = {k: _make_struct(np.array(v)) for k, v in channels.items()}
        fake_mat["__header__"] = b"MATLAB"
        mocker.patch("scipy.io.loadmat", return_value=fake_mat)

    def test_basic_columns_returned(self, tmp_path, mocker):
        self._mock_mat(mocker, {
            "Session_Elapsed_Time": list(range(10)),
            "Ground_Speed": [float(i) for i in range(10)],
            "Engine_RPM": [float(i * 100) for i in range(10)],
        })
        df = parse_mat_file(str(tmp_path / "fake.mat"))
        assert isinstance(df, pd.DataFrame)
        # Engine_RPM stays as-is (no rename rule for it)
        assert "Ground_Speed" in df.columns or "Speed" in df.columns

    def test_rename_map_applied(self, tmp_path, mocker):
        self._mock_mat(mocker, {
            "Session_Elapsed_Time": list(range(10)),
            "GPS_Latitude": [40.0 + i * 0.001 for i in range(10)],
            "GPS_Longitude": [-3.0 - i * 0.001 for i in range(10)],
            "Throttle_Pos": [float(i) for i in range(10)],
        })
        df = parse_mat_file(str(tmp_path / "fake.mat"))
        assert "GPS Latitude" in df.columns
        assert "GPS Longitude" in df.columns
        assert "Throttle" in df.columns

    def test_short_channel_padded(self, tmp_path, mocker):
        base = list(range(10))
        short = list(range(5))  # shorter than base
        self._mock_mat(mocker, {
            "Session_Elapsed_Time": base,
            "Short_Channel": short,
        })
        df = parse_mat_file(str(tmp_path / "fake.mat"))
        assert len(df) == 10
        assert df["Short_Channel"].isna().any()

    def test_long_channel_truncated(self, tmp_path, mocker):
        base = list(range(10))
        long_ch = list(range(20))  # longer than base
        self._mock_mat(mocker, {
            "Session_Elapsed_Time": base,
            "Long_Channel": long_ch,
        })
        df = parse_mat_file(str(tmp_path / "fake.mat"))
        assert len(df) == 10

    def test_no_valid_channels_raises(self, tmp_path, mocker):
        # All keys start with __ (no Value structs)
        mocker.patch("scipy.io.loadmat", return_value={"__header__": b"x", "__version__": b"1"})
        with pytest.raises(ValueError, match="Error parseando .mat"):
            parse_mat_file(str(tmp_path / "fake.mat"))
