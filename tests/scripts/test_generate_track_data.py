"""Tests for scripts/generate_track_data.py — written before implementation (TDD)."""

import json
import sys
import os
import numpy as np
import pytest

# Add project root to path so we can import the script module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tumftm_csv_content():
    """Minimal TUMFTM-format CSV (header comment + data rows)."""
    return (
        "# x_m, y_m, w_tr_right_m, w_tr_left_m\n"
        "0.0,0.0,5.0,6.0\n"
        "10.0,0.0,5.0,6.0\n"
        "20.0,10.0,5.5,6.5\n"
        "30.0,20.0,4.0,5.0\n"
    )


@pytest.fixture
def tumrt_bathurst_csv_content():
    """Minimal TUMRT Bathurst-format CSV with boundary columns."""
    return (
        "right_bound_x,right_bound_y,right_bound_z,"
        "left_bound_x,left_bound_y,left_bound_z\n"
        "1.0,0.0,10.0,  -1.0,0.0,10.0\n"
        "11.0,0.0,11.0,  9.0,0.0,11.0\n"
        "21.0,10.0,12.0, 19.0,10.0,12.0\n"
    )


@pytest.fixture
def openf1_location_data():
    """Simulated OpenF1 location response (list of dicts)."""
    return [
        {"x": 0.0, "y": 0.0, "z": 5.0, "date": "2024-01-01T00:00:00", "driver_number": 1},
        {"x": 100.0, "y": 0.0, "z": 6.0, "date": "2024-01-01T00:00:01", "driver_number": 1},
        {"x": 200.0, "y": 100.0, "z": 7.0, "date": "2024-01-01T00:00:02", "driver_number": 1},
        {"x": 300.0, "y": 200.0, "z": 8.0, "date": "2024-01-01T00:00:03", "driver_number": 1},
    ]


# ---------------------------------------------------------------------------
# Tests: parse_tumftm_csv
# ---------------------------------------------------------------------------

class TestParseTumftmCsv:
    def test_returns_correct_columns(self, tumftm_csv_content, tmp_path):
        from scripts.generate_track_data import parse_tumftm_csv

        csv_file = tmp_path / "test.csv"
        csv_file.write_text(tumftm_csv_content)

        points = parse_tumftm_csv(str(csv_file))
        assert len(points) == 4
        # Each point should have x, y, w_right, w_left
        for p in points:
            assert "x" in p
            assert "y" in p
            assert "w_right" in p
            assert "w_left" in p

    def test_values_parsed_correctly(self, tumftm_csv_content, tmp_path):
        from scripts.generate_track_data import parse_tumftm_csv

        csv_file = tmp_path / "test.csv"
        csv_file.write_text(tumftm_csv_content)

        points = parse_tumftm_csv(str(csv_file))
        assert points[0]["x"] == pytest.approx(0.0)
        assert points[0]["y"] == pytest.approx(0.0)
        assert points[0]["w_right"] == pytest.approx(5.0)
        assert points[0]["w_left"] == pytest.approx(6.0)
        assert points[2]["x"] == pytest.approx(20.0)
        assert points[2]["y"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Tests: parse_tumrt_bathurst_csv
# ---------------------------------------------------------------------------

class TestParseTumrtBathurstCsv:
    def test_returns_centerline_and_widths(self, tumrt_bathurst_csv_content, tmp_path):
        from scripts.generate_track_data import parse_tumrt_bathurst_csv

        csv_file = tmp_path / "bathurst.csv"
        csv_file.write_text(tumrt_bathurst_csv_content)

        points = parse_tumrt_bathurst_csv(str(csv_file))
        assert len(points) == 3
        for p in points:
            assert "x" in p
            assert "y" in p
            assert "z" in p
            assert "w_right" in p
            assert "w_left" in p

    def test_centerline_is_midpoint_of_boundaries(self, tumrt_bathurst_csv_content, tmp_path):
        from scripts.generate_track_data import parse_tumrt_bathurst_csv

        csv_file = tmp_path / "bathurst.csv"
        csv_file.write_text(tumrt_bathurst_csv_content)

        points = parse_tumrt_bathurst_csv(str(csv_file))
        # First row: right=(1,0,10), left=(-1,0,10) -> center=(0,0,10)
        assert points[0]["x"] == pytest.approx(0.0)
        assert points[0]["y"] == pytest.approx(0.0)
        assert points[0]["z"] == pytest.approx(10.0)

    def test_width_is_distance_from_center_to_boundary(self, tumrt_bathurst_csv_content, tmp_path):
        from scripts.generate_track_data import parse_tumrt_bathurst_csv

        csv_file = tmp_path / "bathurst.csv"
        csv_file.write_text(tumrt_bathurst_csv_content)

        points = parse_tumrt_bathurst_csv(str(csv_file))
        # First row: center=(0,0), right=(1,0) -> distance=1.0
        assert points[0]["w_right"] == pytest.approx(1.0)
        assert points[0]["w_left"] == pytest.approx(1.0)

    def test_elevation_preserved(self, tumrt_bathurst_csv_content, tmp_path):
        from scripts.generate_track_data import parse_tumrt_bathurst_csv

        csv_file = tmp_path / "bathurst.csv"
        csv_file.write_text(tumrt_bathurst_csv_content)

        points = parse_tumrt_bathurst_csv(str(csv_file))
        assert points[1]["z"] == pytest.approx(11.0)
        assert points[2]["z"] == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# Tests: project_elevation
# ---------------------------------------------------------------------------

class TestProjectElevation:
    def test_projects_z_via_nearest_neighbor(self):
        from scripts.generate_track_data import project_elevation

        # TUMFTM points (no Z)
        tumftm_xy = np.array([[0.0, 0.0], [10.0, 0.0], [20.0, 10.0]])
        # OpenF1 points with Z (already aligned)
        openf1_xyz = np.array([[0.0, 0.0, 100.0], [10.0, 0.0, 200.0], [20.0, 10.0, 300.0]])

        z_values = project_elevation(tumftm_xy, openf1_xyz)
        assert len(z_values) == 3
        assert z_values[0] == pytest.approx(100.0)
        assert z_values[1] == pytest.approx(200.0)
        assert z_values[2] == pytest.approx(300.0)

    def test_nearest_neighbor_interpolation(self):
        from scripts.generate_track_data import project_elevation

        # Point at (5,0) is closest to openf1 point at (0,0) or (10,0)
        tumftm_xy = np.array([[5.0, 0.0]])
        openf1_xyz = np.array([[0.0, 0.0, 100.0], [10.0, 0.0, 200.0]])

        z_values = project_elevation(tumftm_xy, openf1_xyz)
        # (5,0) is equidistant from both; either 100 or 200 is acceptable
        assert z_values[0] in [pytest.approx(100.0), pytest.approx(200.0)]


# ---------------------------------------------------------------------------
# Tests: build_track_json
# ---------------------------------------------------------------------------

class TestBuildTrackJson:
    def test_flat_track_format(self):
        from scripts.generate_track_data import build_track_json

        points = [
            {"x": 0.0, "y": 0.0, "w_right": 5.0, "w_left": 6.0},
            {"x": 10.0, "y": 0.0, "w_right": 5.0, "w_left": 6.0},
        ]

        result = build_track_json("Test Track", "tumftm", points, z_values=None)
        assert result["name"] == "Test Track"
        assert result["source"] == "tumftm"
        assert len(result["points"]) == 2
        assert result["points"][0]["z"] == 0.0
        assert result["points"][0]["width_left"] == 6.0
        assert result["points"][0]["width_right"] == 5.0

    def test_track_with_elevation(self):
        from scripts.generate_track_data import build_track_json

        points = [
            {"x": 0.0, "y": 0.0, "w_right": 5.0, "w_left": 6.0},
            {"x": 10.0, "y": 0.0, "w_right": 5.0, "w_left": 6.0},
        ]
        z_values = np.array([100.0, 200.0])

        result = build_track_json("Spa", "tumftm+openf1", points, z_values=z_values)
        assert result["source"] == "tumftm+openf1"
        assert result["points"][0]["z"] == pytest.approx(100.0)
        assert result["points"][1]["z"] == pytest.approx(200.0)

    def test_bathurst_with_precomputed_z(self):
        from scripts.generate_track_data import build_track_json

        points = [
            {"x": 0.0, "y": 0.0, "z": 10.0, "w_right": 1.0, "w_left": 1.0},
        ]

        result = build_track_json("Bathurst", "tumrt", points, z_values=None)
        assert result["points"][0]["z"] == pytest.approx(10.0)

    def test_output_is_json_serializable(self):
        from scripts.generate_track_data import build_track_json

        points = [
            {"x": 0.0, "y": 0.0, "w_right": 5.0, "w_left": 6.0},
        ]

        result = build_track_json("Test", "tumftm", points, z_values=None)
        # Should not raise
        json.dumps(result)


# ---------------------------------------------------------------------------
# Tests: TUMFTM_TO_OPENF1_MAPPING
# ---------------------------------------------------------------------------

class TestTrackMapping:
    def test_mapping_exists(self):
        from scripts.generate_track_data import TUMFTM_TO_OPENF1_MAPPING

        assert isinstance(TUMFTM_TO_OPENF1_MAPPING, dict)
        assert len(TUMFTM_TO_OPENF1_MAPPING) > 0

    def test_known_tracks_in_mapping(self):
        from scripts.generate_track_data import TUMFTM_TO_OPENF1_MAPPING

        # These TUMFTM tracks should have OpenF1 equivalents
        expected_keys = ["Spa", "Monza", "Silverstone"]
        for key in expected_keys:
            found = any(key.lower() in k.lower() for k in TUMFTM_TO_OPENF1_MAPPING)
            assert found, f"{key} should be in the mapping"


# ---------------------------------------------------------------------------
# Tests: TUMFTM_TRACKS list
# ---------------------------------------------------------------------------

class TestTumftmTracks:
    def test_tracks_list_exists(self):
        from scripts.generate_track_data import TUMFTM_TRACKS

        assert isinstance(TUMFTM_TRACKS, list)
        assert len(TUMFTM_TRACKS) >= 20  # Should have ~25 tracks


# ---------------------------------------------------------------------------
# Tests: procrustes alignment wrapper
# ---------------------------------------------------------------------------

class TestProcrustesAlign:
    def test_identity_transform(self):
        from scripts.generate_track_data import procrustes_align_2d

        # Same points should yield near-zero disparity
        pts = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        aligned, transform_params = procrustes_align_2d(pts, pts)
        np.testing.assert_allclose(aligned, pts, atol=1e-6)

    def test_scaled_and_rotated_alignment(self):
        from scripts.generate_track_data import procrustes_align_2d

        # Source: unit square
        source = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        # Target: scaled by 2
        target = source * 2.0

        aligned, transform_params = procrustes_align_2d(source, target)
        # After alignment, source should be scaled to match target
        np.testing.assert_allclose(aligned, target, atol=1e-6)
