"""Tests for track upload API and SHA256 dedup storage."""

import hashlib
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.track_storage import (
    canonical_json,
    compute_content_sha256,
    router,
)


@pytest.fixture()
def sample_track_json():
    return {
        "name": "Spa-Francorchamps",
        "source": "spa.aiw",
        "points": [
            {"x": 1.0, "y": 2.0, "z": 3.0, "width_left": 5.0, "width_right": 5.0},
            {"x": 4.0, "y": 5.0, "z": 6.0, "width_left": 5.0, "width_right": 5.0},
        ],
    }


@pytest.fixture()
def sample_sha256_source():
    return hashlib.sha256(b"fake aiw file content").hexdigest()


@pytest.fixture()
def tmp_dirs(tmp_path):
    """Create temporary directories for pre-hosted and community tracks."""
    prehosted = tmp_path / "tracks"
    community = tmp_path / "data" / "tracks"
    prehosted.mkdir(parents=True)
    community.mkdir(parents=True)
    return prehosted, community


@pytest.fixture()
def app_client(tmp_dirs):
    """Create a test client with patched directories."""
    from fastapi import FastAPI

    prehosted, community = tmp_dirs
    test_app = FastAPI()
    test_app.include_router(router)

    with patch("app.core.track_storage.PREHOSTED_TRACKS_DIR", str(prehosted)), \
         patch("app.core.track_storage.COMMUNITY_TRACKS_DIR", str(community)):
        yield TestClient(test_app), prehosted, community


# --- Unit tests for helper functions ---


class TestCanonicalJson:
    def test_sorted_keys(self):
        data = {"b": 2, "a": 1}
        result = canonical_json(data)
        assert result == '{"a":1,"b":2}'

    def test_no_spaces(self):
        data = {"key": "value"}
        result = canonical_json(data)
        assert " " not in result.replace("value", "")

    def test_deterministic(self):
        data = {"name": "test", "points": [{"x": 1, "y": 2}]}
        assert canonical_json(data) == canonical_json(data)


class TestComputeContentSha256:
    def test_returns_hex_string(self, sample_track_json):
        result = compute_content_sha256(sample_track_json)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self, sample_track_json):
        a = compute_content_sha256(sample_track_json)
        b = compute_content_sha256(sample_track_json)
        assert a == b

    def test_different_data_different_hash(self, sample_track_json):
        other = {**sample_track_json, "name": "Monza"}
        assert compute_content_sha256(sample_track_json) != compute_content_sha256(other)


# --- API endpoint tests ---


class TestUploadEndpoint:
    def test_upload_creates_file(self, app_client, sample_track_json, sample_sha256_source):
        client, _, community = app_client
        resp = client.post("/tracks/upload", json={
            "sha256_source": sample_sha256_source,
            "track_json": sample_track_json,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["content_sha256"]
        assert data["name"] == "Spa-Francorchamps"

        # Verify file was written
        files = list(community.glob("*.json"))
        assert len(files) == 1

    def test_upload_duplicate_skips_write(self, app_client, sample_track_json, sample_sha256_source):
        client, _, community = app_client
        payload = {
            "sha256_source": sample_sha256_source,
            "track_json": sample_track_json,
        }
        resp1 = client.post("/tracks/upload", json=payload)
        assert resp1.json()["status"] == "created"

        resp2 = client.post("/tracks/upload", json=payload)
        assert resp2.json()["status"] == "duplicate"

        # Still only one file
        files = list(community.glob("*.json"))
        assert len(files) == 1

    def test_upload_same_content_different_source(self, app_client, sample_track_json):
        client, _, community = app_client
        payload1 = {
            "sha256_source": "a" * 64,
            "track_json": sample_track_json,
        }
        payload2 = {
            "sha256_source": "b" * 64,
            "track_json": sample_track_json,
        }
        client.post("/tracks/upload", json=payload1)
        resp2 = client.post("/tracks/upload", json=payload2)
        assert resp2.json()["status"] == "duplicate"

    def test_upload_invalid_sha256_source(self, app_client, sample_track_json):
        client, _, _ = app_client
        resp = client.post("/tracks/upload", json={
            "sha256_source": "not-a-hex-string",
            "track_json": sample_track_json,
        })
        assert resp.status_code == 422


class TestGetTrackEndpoint:
    def test_get_existing_track(self, app_client, sample_track_json, sample_sha256_source):
        client, _, _ = app_client
        upload_resp = client.post("/tracks/upload", json={
            "sha256_source": sample_sha256_source,
            "track_json": sample_track_json,
        })
        content_sha256 = upload_resp.json()["content_sha256"]

        resp = client.get(f"/tracks/{content_sha256}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Spa-Francorchamps"
        assert data["content_sha256"] == content_sha256

    def test_get_nonexistent_track(self, app_client):
        client, _, _ = app_client
        resp = client.get(f"/tracks/{'0' * 64}")
        assert resp.status_code == 404

    def test_get_prehosted_track(self, app_client, sample_track_json):
        client, prehosted, _ = app_client
        # Write a pre-hosted track file
        track_file = prehosted / "spa.json"
        track_file.write_text(json.dumps(sample_track_json))

        content_sha256 = compute_content_sha256(sample_track_json)
        resp = client.get(f"/tracks/{content_sha256}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Spa-Francorchamps"


class TestListTracksEndpoint:
    def test_list_empty(self, app_client):
        client, _, _ = app_client
        resp = client.get("/tracks/list")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_community_tracks(self, app_client, sample_track_json, sample_sha256_source):
        client, _, _ = app_client
        client.post("/tracks/upload", json={
            "sha256_source": sample_sha256_source,
            "track_json": sample_track_json,
        })
        resp = client.get("/tracks/list")
        assert resp.status_code == 200
        tracks = resp.json()
        assert len(tracks) == 1
        assert tracks[0]["name"] == "Spa-Francorchamps"
        assert tracks[0]["source"] == "community"
        assert tracks[0]["content_sha256"]
        assert tracks[0]["created_at"]

    def test_list_prehosted_tracks(self, app_client, sample_track_json):
        client, prehosted, _ = app_client
        track_file = prehosted / "monza.json"
        track_file.write_text(json.dumps(sample_track_json))

        resp = client.get("/tracks/list")
        tracks = resp.json()
        assert len(tracks) == 1
        assert tracks[0]["source"] == "prehosted"

    def test_list_both_sources(self, app_client, sample_track_json, sample_sha256_source):
        client, prehosted, _ = app_client

        # Pre-hosted track
        other_track = {**sample_track_json, "name": "Monza"}
        (prehosted / "monza.json").write_text(json.dumps(other_track))

        # Community track
        client.post("/tracks/upload", json={
            "sha256_source": sample_sha256_source,
            "track_json": sample_track_json,
        })

        resp = client.get("/tracks/list")
        tracks = resp.json()
        assert len(tracks) == 2
        sources = {t["source"] for t in tracks}
        assert sources == {"prehosted", "community"}


class TestDownloadTrackEndpoint:
    def test_download_community_track(self, app_client, sample_track_json, sample_sha256_source):
        client, _, _ = app_client
        upload_resp = client.post("/tracks/upload", json={
            "sha256_source": sample_sha256_source,
            "track_json": sample_track_json,
        })
        content_sha256 = upload_resp.json()["content_sha256"]

        resp = client.get(f"/tracks/{content_sha256}/download")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Spa-Francorchamps"
        assert "points" in data

    def test_download_prehosted_track(self, app_client, sample_track_json):
        client, prehosted, _ = app_client
        (prehosted / "test.json").write_text(json.dumps(sample_track_json))
        content_sha256 = compute_content_sha256(sample_track_json)

        resp = client.get(f"/tracks/{content_sha256}/download")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Spa-Francorchamps"

    def test_download_nonexistent(self, app_client):
        client, _, _ = app_client
        resp = client.get(f"/tracks/{'0' * 64}/download")
        assert resp.status_code == 404
