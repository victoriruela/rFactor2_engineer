"""Integration tests for the 3D Replay feature (T1-T8).

Tests cross-module interactions:
  - AIW parser -> track storage -> retrieval
  - parse-aiw endpoint end-to-end (TestClient)
  - Track JSON schema consistency between pre-hosted and AIW-parsed tracks
  - Cockpit data builder -> render_3d_cockpit HTML generation
  - Full upload -> deduplicate -> retrieve flow
"""

import hashlib
import json
import os
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.track_parser import parse_aiw, router as parser_router
from app.core.track_storage import (
    canonical_json,
    compute_content_sha256,
    router as storage_router,
)

# ── Streamlit mock (must happen before importing streamlit_app) ──
_st_mock = MagicMock()
_st_mock.session_state = {}
_st_mock.file_uploader.return_value = None
_st_mock.sidebar.__enter__ = lambda s: s
_st_mock.sidebar.__exit__ = lambda *a: False
sys.modules.setdefault("streamlit", _st_mock)
sys.modules.setdefault("streamlit.components", MagicMock())
sys.modules.setdefault("streamlit.components.v1", MagicMock())

from frontend.streamlit_app import (  # noqa: E402
    _build_cockpit_data,
    render_3d_cockpit,
    compute_file_sha256,
)


# Override the session-scoped autouse fixture from conftest.py so that
# these tests run without requiring Ollama (they only test 3D replay).
@pytest.fixture(scope="session", autouse=True)
def require_ollama():
    """No-op override: 3D replay integration tests do not need Ollama."""
    return


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
SAMPLE_AIW = os.path.join(FIXTURES_DIR, "sample.aiw")

TRACK_JSON_SCHEMA_KEYS = {"name", "source", "points"}
POINT_SCHEMA_KEYS = {"x", "y", "z", "width_left", "width_right"}


@pytest.fixture
def sample_aiw_content():
    with open(SAMPLE_AIW, "r") as f:
        return f.read()


@pytest.fixture
def sample_aiw_bytes():
    with open(SAMPLE_AIW, "rb") as f:
        return f.read()


@pytest.fixture
def parsed_aiw_track(sample_aiw_content):
    """Parse the sample AIW fixture into track JSON."""
    return parse_aiw(sample_aiw_content, track_name="Test Circuit")


@pytest.fixture
def prehosted_track_json():
    """A track JSON in the same schema as generate_track_data.py output."""
    return {
        "name": "Spa-Francorchamps",
        "source": "tumftm+openf1",
        "points": [
            {"x": 0.0, "y": 0.0, "z": 100.0, "width_left": 6.0, "width_right": 5.0},
            {"x": 10.0, "y": 5.0, "z": 101.0, "width_left": 6.0, "width_right": 5.0},
            {"x": 20.0, "y": 10.0, "z": 102.0, "width_left": 6.5, "width_right": 5.5},
        ],
    }


@pytest.fixture
def tmp_dirs(tmp_path):
    prehosted = tmp_path / "tracks"
    community = tmp_path / "data" / "tracks"
    prehosted.mkdir(parents=True)
    community.mkdir(parents=True)
    return prehosted, community


@pytest.fixture
def full_app_client(tmp_dirs):
    """TestClient with both parser and storage routers, patched dirs."""
    prehosted, community = tmp_dirs
    test_app = FastAPI()
    test_app.include_router(parser_router)
    test_app.include_router(storage_router)

    with patch("app.core.track_storage.PREHOSTED_TRACKS_DIR", str(prehosted)), \
         patch("app.core.track_storage.COMMUNITY_TRACKS_DIR", str(community)):
        yield TestClient(test_app), prehosted, community


@pytest.fixture
def cockpit_df():
    """A realistic-ish DataFrame with all expected telemetry columns."""
    n = 50
    return pd.DataFrame({
        "Lap_Distance": np.linspace(0, 3000, n),
        "Ground_Speed": np.random.uniform(60, 250, n),
        "Throttle_Pos": np.random.uniform(0, 1, n),
        "Brake_Pos": np.random.uniform(0, 1, n),
        "Gear": np.random.choice([1, 2, 3, 4, 5, 6], n),
        "Engine_RPM": np.random.uniform(3000, 12000, n),
        "Steering_Wheel_Position": np.random.uniform(-180, 180, n),
        "Body_Pitch": np.random.uniform(-0.05, 0.05, n),
        "Body_Roll": np.random.uniform(-0.05, 0.05, n),
        "G_Force_Lat": np.random.uniform(-3, 3, n),
        "G_Force_Long": np.random.uniform(-3, 3, n),
        "Ride_Height_FL": np.random.uniform(0.02, 0.06, n),
        "Ride_Height_FR": np.random.uniform(0.02, 0.06, n),
        "Ride_Height_RL": np.random.uniform(0.02, 0.06, n),
        "Ride_Height_RR": np.random.uniform(0.02, 0.06, n),
    })


# ===========================================================================
# 1. Track JSON Schema Consistency
# ===========================================================================


class TestTrackJsonSchema:
    """Verify that AIW-parsed and pre-hosted tracks use the same schema."""

    def test_aiw_parsed_has_required_keys(self, parsed_aiw_track):
        assert set(parsed_aiw_track.keys()) >= TRACK_JSON_SCHEMA_KEYS

    def test_aiw_parsed_points_have_required_fields(self, parsed_aiw_track):
        for point in parsed_aiw_track["points"]:
            assert set(point.keys()) >= POINT_SCHEMA_KEYS

    def test_prehosted_has_required_keys(self, prehosted_track_json):
        assert set(prehosted_track_json.keys()) >= TRACK_JSON_SCHEMA_KEYS

    def test_prehosted_points_have_required_fields(self, prehosted_track_json):
        for point in prehosted_track_json["points"]:
            assert set(point.keys()) >= POINT_SCHEMA_KEYS

    def test_schemas_are_compatible(self, parsed_aiw_track, prehosted_track_json):
        """Both track sources must have identical point field sets."""
        aiw_fields = set(parsed_aiw_track["points"][0].keys())
        pre_fields = set(prehosted_track_json["points"][0].keys())
        assert aiw_fields == pre_fields

    def test_all_point_values_are_floats(self, parsed_aiw_track):
        for point in parsed_aiw_track["points"]:
            for key in POINT_SCHEMA_KEYS:
                assert isinstance(point[key], float), (
                    f"Point field '{key}' should be float, got {type(point[key])}"
                )

    def test_track_json_is_serializable(self, parsed_aiw_track):
        """Track JSON must be JSON-serializable (no numpy types etc.)."""
        serialized = json.dumps(parsed_aiw_track)
        roundtripped = json.loads(serialized)
        assert roundtripped == parsed_aiw_track


# ===========================================================================
# 2. AIW Parser -> POST /tracks/parse-aiw (end-to-end)
# ===========================================================================


class TestParseAiwEndpoint:
    """End-to-end test of the POST /tracks/parse-aiw endpoint."""

    def test_parse_aiw_endpoint_returns_track_json(self, full_app_client, sample_aiw_bytes):
        client, _, _ = full_app_client
        resp = client.post(
            "/tracks/parse-aiw",
            files={"file": ("test.aiw", sample_aiw_bytes, "application/octet-stream")},
            data={"track_name": "Spa-Test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Spa-Test"
        assert data["source"] == "aiw"
        assert len(data["points"]) == 7

    def test_parse_aiw_endpoint_default_name(self, full_app_client, sample_aiw_bytes):
        client, _, _ = full_app_client
        resp = client.post(
            "/tracks/parse-aiw",
            files={"file": ("test.aiw", sample_aiw_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Unknown"

    def test_parse_aiw_coordinate_mapping(self, full_app_client, sample_aiw_bytes):
        """Verify AIW_X->x, AIW_Z->y, AIW_Y->z mapping through the endpoint."""
        client, _, _ = full_app_client
        resp = client.post(
            "/tracks/parse-aiw",
            files={"file": ("test.aiw", sample_aiw_bytes, "application/octet-stream")},
        )
        points = resp.json()["points"]
        # First waypoint: wp_pos=(100.5, 25.3, 200.7)
        p0 = points[0]
        assert p0["x"] == pytest.approx(100.5)   # AIW_X
        assert p0["y"] == pytest.approx(200.7)   # AIW_Z
        assert p0["z"] == pytest.approx(25.3)    # AIW_Y (elevation)


# ===========================================================================
# 3. Upload -> Deduplicate -> Retrieve (end-to-end)
# ===========================================================================


class TestUploadDeduplicateRetrieve:
    """Full upload -> dedup -> retrieve flow via API."""

    def test_upload_then_retrieve(self, full_app_client, parsed_aiw_track):
        client, _, _ = full_app_client
        sha256_source = hashlib.sha256(b"test aiw content").hexdigest()

        # Upload
        resp = client.post("/tracks/upload", json={
            "sha256_source": sha256_source,
            "track_json": parsed_aiw_track,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        content_sha256 = data["content_sha256"]

        # Retrieve metadata
        resp2 = client.get(f"/tracks/{content_sha256}")
        assert resp2.status_code == 200
        assert resp2.json()["name"] == "Test Circuit"
        assert resp2.json()["source"] == "community"

        # Download full track
        resp3 = client.get(f"/tracks/{content_sha256}/download")
        assert resp3.status_code == 200
        downloaded = resp3.json()
        assert downloaded["name"] == parsed_aiw_track["name"]
        assert len(downloaded["points"]) == len(parsed_aiw_track["points"])

    def test_duplicate_upload_returns_duplicate(self, full_app_client, parsed_aiw_track):
        client, _, _ = full_app_client
        sha256_source = hashlib.sha256(b"test").hexdigest()
        payload = {
            "sha256_source": sha256_source,
            "track_json": parsed_aiw_track,
        }

        resp1 = client.post("/tracks/upload", json=payload)
        assert resp1.json()["status"] == "created"

        resp2 = client.post("/tracks/upload", json=payload)
        assert resp2.json()["status"] == "duplicate"

        # Content SHA should be the same
        assert resp1.json()["content_sha256"] == resp2.json()["content_sha256"]

    def test_list_returns_both_prehosted_and_community(
        self, full_app_client, parsed_aiw_track, prehosted_track_json
    ):
        client, prehosted_dir, _ = full_app_client

        # Write a pre-hosted track
        (prehosted_dir / "spa.json").write_text(json.dumps(prehosted_track_json))

        # Upload community track (different data so not a dup of prehosted)
        sha256_source = hashlib.sha256(b"community").hexdigest()
        client.post("/tracks/upload", json={
            "sha256_source": sha256_source,
            "track_json": parsed_aiw_track,
        })

        resp = client.get("/tracks/list")
        assert resp.status_code == 200
        tracks = resp.json()
        sources = {t["source"] for t in tracks}
        assert "prehosted" in sources
        assert "community" in sources

    def test_prehosted_duplicate_detected(
        self, full_app_client, prehosted_track_json
    ):
        """Uploading a track identical to a pre-hosted one returns duplicate."""
        client, prehosted_dir, _ = full_app_client
        (prehosted_dir / "spa.json").write_text(json.dumps(prehosted_track_json))

        sha256_source = hashlib.sha256(b"spa").hexdigest()
        resp = client.post("/tracks/upload", json={
            "sha256_source": sha256_source,
            "track_json": prehosted_track_json,
        })
        assert resp.json()["status"] == "duplicate"


# ===========================================================================
# 4. AIW Parser -> Storage -> Cockpit Rendering Pipeline
# ===========================================================================


class TestParserToRenderingPipeline:
    """Verify an AIW-parsed track can flow through storage and into
    render_3d_cockpit without errors."""

    def test_parsed_aiw_renders_valid_html(self, parsed_aiw_track):
        html = render_3d_cockpit(None, parsed_aiw_track)
        assert "three" in html.lower() or "THREE" in html
        assert "<canvas" in html
        assert "hud" in html.lower()
        assert "controls" in html.lower()

    def test_parsed_aiw_uploaded_then_rendered(self, full_app_client, sample_aiw_bytes):
        """Full pipeline: parse via endpoint -> upload -> download -> render."""
        client, _, _ = full_app_client

        # Parse
        parse_resp = client.post(
            "/tracks/parse-aiw",
            files={"file": ("circuit.aiw", sample_aiw_bytes, "application/octet-stream")},
            data={"track_name": "Pipeline Track"},
        )
        track_json = parse_resp.json()

        # Upload
        sha256_source = compute_file_sha256(sample_aiw_bytes)
        upload_resp = client.post("/tracks/upload", json={
            "sha256_source": sha256_source,
            "track_json": track_json,
        })
        content_sha256 = upload_resp.json()["content_sha256"]

        # Download
        dl_resp = client.get(f"/tracks/{content_sha256}/download")
        downloaded = dl_resp.json()

        # Render
        html = render_3d_cockpit(None, downloaded)
        assert "Pipeline Track" in html
        assert "setCockpitPosition" in html

    def test_prehosted_track_renders_valid_html(self, prehosted_track_json):
        html = render_3d_cockpit(None, prehosted_track_json)
        assert "Spa-Francorchamps" in html
        assert "<canvas" in html


# ===========================================================================
# 5. Cockpit Data Builder -> HTML Renderer
# ===========================================================================


class TestCockpitDataToRenderer:
    """Verify _build_cockpit_data() output integrates with render_3d_cockpit()."""

    def test_cockpit_data_renders_with_telemetry(
        self, cockpit_df, parsed_aiw_track
    ):
        cockpit_data = _build_cockpit_data(cockpit_df)
        assert cockpit_data is not None

        html = render_3d_cockpit(cockpit_data, parsed_aiw_track)
        # Should contain both track and telemetry data
        assert "TRACK_DATA" in html
        assert "TELEMETRY_DATA" in html
        assert "null" not in html.split("TELEMETRY_DATA")[1][:20]

    def test_cockpit_data_arrays_match_df_length(self, cockpit_df):
        cockpit_data = _build_cockpit_data(cockpit_df)
        expected_len = len(cockpit_df)
        for key, arr in cockpit_data.items():
            assert len(arr) == expected_len, (
                f"Array '{key}' length {len(arr)} != DataFrame length {expected_len}"
            )

    def test_cockpit_html_with_no_telemetry(self, parsed_aiw_track):
        """Track-only mode (no lap data) should still produce valid HTML."""
        html = render_3d_cockpit(None, parsed_aiw_track)
        assert "TELEMETRY_DATA" in html
        assert "setCockpitPosition" in html

    def test_cockpit_html_with_no_track_returns_placeholder(self):
        html = render_3d_cockpit(None, None)
        assert "No track data" in html
        assert "<canvas" not in html


# ===========================================================================
# 6. Three.js HTML Structure Verification
# ===========================================================================


class TestThreeJsHtmlStructure:
    """Structural verification of the rendered HTML."""

    @pytest.fixture
    def html(self, parsed_aiw_track):
        return render_3d_cockpit(None, parsed_aiw_track)

    def test_contains_threejs_cdn_import(self, html):
        assert "unpkg.com/three" in html

    def test_contains_canvas_element(self, html):
        assert '<canvas id="c">' in html

    def test_contains_hud_overlay(self, html):
        assert 'id="hud"' in html
        assert "hud-speed" in html
        assert "hud-gear" in html
        assert "hud-rpm" in html

    def test_contains_playback_controls(self, html):
        assert 'id="controls"' in html
        assert 'id="btn-play"' in html
        assert 'id="scrub"' in html
        assert 'id="speed-sel"' in html

    def test_exposes_set_cockpit_position(self, html):
        assert "window.setCockpitPosition" in html

    def test_contains_sync_hooks(self, html):
        assert "cockpitSync" in html
        assert "chartSync" in html
        assert "_syncInProgress" in html


# ===========================================================================
# 7. Content SHA256 Consistency
# ===========================================================================


class TestContentSha256Consistency:
    """Verify SHA256 dedup hashing is deterministic and consistent."""

    def test_same_track_different_upload_times_same_hash(self, parsed_aiw_track):
        h1 = compute_content_sha256(parsed_aiw_track)
        h2 = compute_content_sha256(parsed_aiw_track)
        assert h1 == h2

    def test_canonical_json_key_order_independent(self):
        d1 = {"z": 1, "a": 2, "m": 3}
        d2 = {"a": 2, "m": 3, "z": 1}
        assert canonical_json(d1) == canonical_json(d2)

    def test_file_sha256_matches_hashlib(self, sample_aiw_bytes):
        expected = hashlib.sha256(sample_aiw_bytes).hexdigest()
        assert compute_file_sha256(sample_aiw_bytes) == expected


# ===========================================================================
# 8. generate_track_data.py Schema Validation
# ===========================================================================


class TestGenerateTrackDataSchema:
    """Validate that build_track_json produces schema-compliant output."""

    def test_build_track_json_matches_schema(self):
        from scripts.generate_track_data import build_track_json

        points = [
            {"x": 0.0, "y": 0.0, "w_right": 5.0, "w_left": 6.0},
            {"x": 10.0, "y": 5.0, "w_right": 5.0, "w_left": 6.0},
        ]
        result = build_track_json("Test", "tumftm", points, z_values=None)

        # Must have top-level keys
        assert set(result.keys()) >= TRACK_JSON_SCHEMA_KEYS

        # Each point must have the required fields
        for point in result["points"]:
            assert set(point.keys()) >= POINT_SCHEMA_KEYS

    def test_build_track_json_compatible_with_render(self):
        """Track from generate_track_data should render without error."""
        from scripts.generate_track_data import build_track_json

        points = [
            {"x": 0.0, "y": 0.0, "w_right": 5.0, "w_left": 6.0},
            {"x": 50.0, "y": 25.0, "w_right": 5.0, "w_left": 6.0},
            {"x": 100.0, "y": 0.0, "w_right": 5.0, "w_left": 6.0},
        ]
        track = build_track_json("Render Test", "tumftm", points, z_values=None)
        html = render_3d_cockpit(None, track)
        assert "<canvas" in html
        assert "Render Test" in html

    def test_build_track_json_with_elevation_compatible_with_render(self):
        from scripts.generate_track_data import build_track_json

        points = [
            {"x": 0.0, "y": 0.0, "w_right": 5.0, "w_left": 6.0},
            {"x": 50.0, "y": 25.0, "w_right": 5.0, "w_left": 6.0},
            {"x": 100.0, "y": 0.0, "w_right": 5.0, "w_left": 6.0},
        ]
        z_vals = np.array([100.0, 110.0, 105.0])
        track = build_track_json("Elev Test", "tumftm+openf1", points, z_values=z_vals)
        html = render_3d_cockpit(None, track)
        assert "Elev Test" in html


# ===========================================================================
# 9. Module Import Smoke Test
# ===========================================================================


class TestModuleImports:
    """Verify all 3D replay modules import cleanly with no circular deps."""

    def test_track_parser_imports(self):
        import app.core.track_parser as mod
        assert callable(mod.parse_aiw)
        assert hasattr(mod, "router")

    def test_track_storage_imports(self):
        import app.core.track_storage as mod
        assert callable(mod.compute_content_sha256)
        assert callable(mod.canonical_json)
        assert hasattr(mod, "router")

    def test_generate_track_data_imports(self):
        import scripts.generate_track_data as mod
        assert callable(mod.parse_tumftm_csv)
        assert callable(mod.parse_tumrt_bathurst_csv)
        assert callable(mod.build_track_json)
        assert callable(mod.project_elevation)
        assert callable(mod.procrustes_align_2d)
        assert isinstance(mod.TUMFTM_TRACKS, list)
        assert isinstance(mod.TUMFTM_TO_OPENF1_MAPPING, dict)

    def test_main_app_imports_both_routers(self):
        from app.main import app as main_app
        route_paths = [r.path for r in main_app.routes]
        assert "/tracks/parse-aiw" in route_paths
        assert "/tracks/upload" in route_paths
        assert "/tracks/list" in route_paths

    def test_frontend_cockpit_functions_import(self):
        import frontend.streamlit_app as mod
        assert callable(mod._build_cockpit_data)
        assert callable(mod.render_3d_cockpit)
        assert callable(mod.compute_file_sha256)
        assert callable(mod.compute_track_centroid)
        assert callable(mod.find_best_track_match)
        assert callable(mod.build_track_preview_data)

    def test_frontend_pip_functions_import(self):
        import frontend.streamlit_app as mod
        assert len(mod.PIP_VALID_STATES) == 4
        assert callable(mod.pip_get_state)
        assert callable(mod.pip_transition)
        assert callable(mod.pip_restore_from_hidden)
        assert callable(mod.pip_restore_from_fullscreen)
        assert callable(mod.pip_css)
        assert callable(mod.pip_render_cockpit_container)
        assert isinstance(mod.PIP_STATE_MINI, str)
        assert isinstance(mod.PIP_STATE_HIDDEN, str)
        assert isinstance(mod.PIP_STATE_MAP_REPLACE, str)
        assert isinstance(mod.PIP_STATE_FULLSCREEN, str)
