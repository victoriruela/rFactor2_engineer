"""Tests for track selection auto-match logic and data preparation helpers."""

import hashlib

import pytest


# ---------------------------------------------------------------------------
# Import helpers under test.  They are pure functions that live in the
# frontend module but have zero Streamlit dependency.
# ---------------------------------------------------------------------------
from frontend.streamlit_app import (
    compute_track_centroid,
    find_best_track_match,
    build_track_preview_data,
    compute_file_sha256,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_track_json():
    """Minimal track JSON (list of waypoints with x, y, lat, lon)."""
    return {
        "name": "Spa-Francorchamps",
        "waypoints": [
            {"x": 0, "y": 0, "lat": 50.4372, "lon": 5.9714},
            {"x": 100, "y": 50, "lat": 50.4382, "lon": 5.9724},
            {"x": 200, "y": 0, "lat": 50.4392, "lon": 5.9734},
        ],
    }


@pytest.fixture
def known_tracks():
    """Two pre-hosted tracks with known centroids."""
    return [
        {
            "name": "Spa-Francorchamps",
            "content_sha256": "abc123",
            "centroid_lat": 50.4382,
            "centroid_lon": 5.9724,
        },
        {
            "name": "Monza",
            "content_sha256": "def456",
            "centroid_lat": 45.6156,
            "centroid_lon": 9.2811,
        },
    ]


# ── compute_track_centroid ────────────────────────────────────────────────


class TestComputeTrackCentroid:
    def test_returns_mean_lat_lon(self, sample_track_json):
        lat, lon = compute_track_centroid(sample_track_json)
        assert lat == pytest.approx(50.4382, abs=1e-4)
        assert lon == pytest.approx(5.9724, abs=1e-4)

    def test_empty_waypoints_returns_none(self):
        result = compute_track_centroid({"waypoints": []})
        assert result is None

    def test_missing_waypoints_returns_none(self):
        result = compute_track_centroid({})
        assert result is None

    def test_single_waypoint(self):
        track = {"waypoints": [{"lat": 10.0, "lon": 20.0}]}
        lat, lon = compute_track_centroid(track)
        assert lat == pytest.approx(10.0)
        assert lon == pytest.approx(20.0)


# ── find_best_track_match ─────────────────────────────────────────────────


class TestFindBestTrackMatch:
    def test_exact_match(self, known_tracks):
        result = find_best_track_match(50.4382, 5.9724, known_tracks)
        assert result is not None
        assert result["name"] == "Spa-Francorchamps"

    def test_close_match_within_threshold(self, known_tracks):
        # Slightly offset (within 0.01 degrees ~ 1 km)
        result = find_best_track_match(50.4385, 5.9720, known_tracks)
        assert result is not None
        assert result["name"] == "Spa-Francorchamps"

    def test_no_match_when_far(self, known_tracks):
        # Somewhere in the middle of nowhere
        result = find_best_track_match(0.0, 0.0, known_tracks)
        assert result is None

    def test_empty_known_tracks(self):
        result = find_best_track_match(50.0, 5.0, [])
        assert result is None

    def test_picks_closest(self, known_tracks):
        # Close to Monza
        result = find_best_track_match(45.616, 9.281, known_tracks)
        assert result is not None
        assert result["name"] == "Monza"


# ── build_track_preview_data ──────────────────────────────────────────────


class TestBuildTrackPreviewData:
    def test_extracts_xy(self, sample_track_json):
        xs, ys = build_track_preview_data(sample_track_json)
        assert xs == [0, 100, 200]
        assert ys == [0, 50, 0]

    def test_empty_waypoints(self):
        xs, ys = build_track_preview_data({"waypoints": []})
        assert xs == []
        assert ys == []

    def test_missing_waypoints(self):
        xs, ys = build_track_preview_data({})
        assert xs == []
        assert ys == []

    def test_falls_back_to_lat_lon_when_no_xy(self):
        """When waypoints lack x/y but have lat/lon, use lat/lon."""
        track = {
            "waypoints": [
                {"lat": 10.0, "lon": 20.0},
                {"lat": 10.1, "lon": 20.1},
            ]
        }
        xs, ys = build_track_preview_data(track)
        assert xs == [20.0, 20.1]  # lon as x
        assert ys == [10.0, 10.1]  # lat as y


# ── compute_file_sha256 ──────────────────────────────────────────────────


class TestComputeFileSha256:
    def test_known_hash(self):
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        assert compute_file_sha256(data) == expected

    def test_empty_bytes(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_file_sha256(b"") == expected
