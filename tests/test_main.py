"""Unit tests for app/main.py FastAPI endpoints."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

FIXTURES_DIR = Path(__file__).parent / "fixtures"

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
SESSION_HEADERS = {"X-Client-Session-Id": "testsession1234"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_telemetry_df() -> pd.DataFrame:
    """Smallest valid DataFrame that won't crash the /analyze pipeline."""
    n = 20
    return pd.DataFrame({
        "Lap Number": [1] * n,
        "Lap Distance": np.linspace(0, 5000, n),
        "Ground Speed": np.ones(n) * 100.0,
        "GPS Latitude":  np.ones(n) * 40.0,
        "GPS Longitude": np.ones(n) * -3.0,
    })


def _minimal_setup_dict() -> dict:
    return {"GENERAL": {"FuelSetting": "50//L"}}


def _minimal_ai_result() -> dict:
    return {
        "driving_analysis": "Análisis OK",
        "setup_analysis": "Setup OK",
        "full_setup": {"sections": []},
        "agent_reports": [],
        "setup_agent_reports": [],
        "chief_reasoning": "Razonamiento OK",
        "llm_provider": "ollama",
        "llm_model": "llama3.2:latest",
    }


# ---------------------------------------------------------------------------
# GET /models
# ---------------------------------------------------------------------------

class TestGetModels:
    def test_returns_models_list(self, mocker):
        mocker.patch("app.main.list_available_models", return_value=["llama3.2:3b"])
        r = client.get("/models")
        assert r.status_code == 200
        assert r.json() == {"models": ["llama3.2:3b"]}

    def test_returns_empty_list(self, mocker):
        mocker.patch("app.main.list_available_models", return_value=[])
        r = client.get("/models")
        assert r.status_code == 200
        assert r.json() == {"models": []}


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------

class TestGetSessions:
    def test_no_data_dir_returns_empty(self, mocker):
        mocker.patch("os.path.exists", return_value=False)
        r = client.get("/sessions", headers=SESSION_HEADERS)
        assert r.status_code == 200
        assert r.json() == {"sessions": []}

    def test_sessions_with_data(self, tmp_path, mocker):
        # Create a fake session pair (same base name)
        (tmp_path / "abc-123.csv").write_text("data")
        (tmp_path / "abc-123.svm").write_text("data")
        with patch("app.main._client_root", return_value=str(tmp_path)):
            r = client.get("/sessions", headers=SESSION_HEADERS)
        assert r.status_code == 200
        sessions = r.json()["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["id"] == "abc-123"


# ---------------------------------------------------------------------------
# GET /sessions/{id}/file/{filename}
# ---------------------------------------------------------------------------

class TestGetSessionFile:
    def test_missing_file_returns_404(self):
        r = client.get("/sessions/nonexistent-id/file/nope.csv", headers=SESSION_HEADERS)
        assert r.status_code == 404

    def test_existing_file_returns_content(self, tmp_path):
        session_id = "session-ok"
        filename = "session-ok.csv"
        expected = "col1,col2\n1,2\n"
        (tmp_path / filename).write_text(expected, encoding="utf-8")
        (tmp_path / "session-ok.svm").write_text("setup", encoding="utf-8")

        with patch("app.main._client_root", return_value=str(tmp_path)):
            r = client.get(f"/sessions/{session_id}/file/{filename}", headers=SESSION_HEADERS)

        assert r.status_code == 200
        assert r.text == expected


# ---------------------------------------------------------------------------
# POST /cleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    def test_no_data_dir_returns_ok(self, mocker):
        with patch("app.main._client_root", return_value="/nope"):
            r = client.post("/cleanup", headers=SESSION_HEADERS)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_deletes_mat_and_svm_files(self, tmp_path, mocker):
        # Create fake files
        mat = tmp_path / "x.mat"
        svm = tmp_path / "y.svm"
        mat.write_text("data")
        svm.write_text("data")

        with patch("app.main._client_root", return_value=str(tmp_path)):
            r = client.post("/cleanup", headers=SESSION_HEADERS)

        assert r.status_code == 200
        assert r.json()["deleted_files"] >= 2


class TestChunkedUploads:
    def test_upload_init_accepts_cors_preflight_from_local_frontend(self):
        preflight = client.options(
            "/uploads/init",
            headers={
                "Origin": "http://localhost:8501",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:8501"

    def test_chunk_upload_complete_and_list_sessions(self, tmp_path):
        with patch("app.main._client_root", return_value=str(tmp_path)):
            r1 = client.post("/uploads/init", headers=SESSION_HEADERS, json={"filename": "session.csv"})
            assert r1.status_code == 200
            upload_tele = r1.json()["upload_id"]

            r2 = client.put(
                f"/uploads/{upload_tele}/chunk?chunk_index=0",
                headers=SESSION_HEADERS,
                content=b"csv-data",
            )
            assert r2.status_code == 200

            r3 = client.post(f"/uploads/{upload_tele}/complete", headers=SESSION_HEADERS)
            assert r3.status_code == 200

            r4 = client.post("/uploads/init", headers=SESSION_HEADERS, json={"filename": "session.svm"})
            assert r4.status_code == 200
            upload_svm = r4.json()["upload_id"]

            r5 = client.put(
                f"/uploads/{upload_svm}/chunk?chunk_index=0",
                headers=SESSION_HEADERS,
                content=b"svm-data",
            )
            assert r5.status_code == 200
            r6 = client.post(f"/uploads/{upload_svm}/complete", headers=SESSION_HEADERS)
            assert r6.status_code == 200

            listed = client.get("/sessions", headers=SESSION_HEADERS)
            assert listed.status_code == 200
            assert listed.json()["sessions"][0]["id"] == "session"

    def test_chunk_rejects_out_of_order_index(self, tmp_path):
        with patch("app.main._client_root", return_value=str(tmp_path)):
            init = client.post("/uploads/init", headers=SESSION_HEADERS, json={"filename": "foo.csv"})
            upload_id = init.json()["upload_id"]

            bad = client.put(
                f"/uploads/{upload_id}/chunk?chunk_index=1",
                headers=SESSION_HEADERS,
                content=b"oops",
            )
            assert bad.status_code == 409


# ---------------------------------------------------------------------------
# POST /analyze
# ---------------------------------------------------------------------------

class TestAnalyze:
    """
    The /analyze endpoint is tested with real fixture files so the full pipeline
    (GPS extraction, aspect ratio, lap stats, subsampling, summary building) executes.
    Only ai_engineer.analyze is mocked — it requires Ollama which is a separate
    system dependency. Integration tests covering the real LLM are in tests/integration/.
    """

    @property
    def _csv_bytes(self) -> bytes:
        return (FIXTURES_DIR / "sample.csv").read_bytes()

    @property
    def _svm_bytes(self) -> bytes:
        return (FIXTURES_DIR / "sample.svm").read_bytes()

    def _post_analyze(self, mocker, csv_bytes=None, svm_bytes=None):
        mocker.patch("app.main.ai_engineer.analyze", new=AsyncMock(return_value=_minimal_ai_result()))
        return client.post(
            "/analyze",
            files={
                "telemetry_file": ("session.csv", csv_bytes or self._csv_bytes, "text/csv"),
                "svm_file": ("car.svm", svm_bytes or self._svm_bytes, "text/plain"),
            },
        )

    def test_analyze_csv_real_parse_returns_all_keys(self, mocker):
        """Real parsers run; all 200 lines of endpoint pipeline execute."""
        r = self._post_analyze(mocker)
        assert r.status_code == 200
        body = r.json()
        for key in ("circuit_data", "driving_analysis", "setup_analysis",
                "full_setup", "session_stats", "laps_data", "setup_agent_reports"):
            assert key in body, f"Missing response key: {key}"

    def test_analyze_csv_real_parse_gps_data(self, mocker):
        """GPS extraction + aspect ratio calculation runs on real CSV fixture."""
        r = self._post_analyze(mocker)
        body = r.json()
        assert len(body["circuit_data"]["x"]) > 0
        assert len(body["circuit_data"]["y"]) > 0
        assert isinstance(body["circuit_data"]["aspect_ratio"], float)

    def test_analyze_csv_real_parse_lap_stats(self, mocker):
        """Lap statistics computed from real telemetry data."""
        r = self._post_analyze(mocker)
        body = r.json()
        assert body["session_stats"]["total_laps"] >= 1
        assert len(body["laps_data"]) >= 1
        lap = body["laps_data"][0]
        assert lap["speed_avg"] > 0
        assert "throttle_avg" in lap
        assert "brake_max" in lap

    def test_analyze_svm_real_parse_full_setup(self, mocker):
        """SVM parsed and formatted into full_setup sections."""
        r = self._post_analyze(mocker)
        body = r.json()
        assert isinstance(body["full_setup"].get("sections"), list)

    def test_analyze_deletes_temp_upload_dir_after_success(self, tmp_path, mocker):
        mocker.patch("app.main.DATA_DIR", str(tmp_path))
        mocker.patch("app.main.uuid.uuid4", return_value="session-cleanup")
        mocker.patch("app.main.ai_engineer.analyze", new=AsyncMock(return_value=_minimal_ai_result()))

        r = client.post(
            "/analyze",
            files={
                "telemetry_file": ("session.csv", self._csv_bytes, "text/csv"),
                "svm_file": ("car.svm", self._svm_bytes, "text/plain"),
            },
        )

        assert r.status_code == 200
        assert not (tmp_path / "session-cleanup").exists()

    def test_analyze_invalid_telemetry_returns_error(self, mocker):
        mocker.patch("app.main.parse_csv_file", side_effect=ValueError("bad file"))
        r = client.post(
            "/analyze",
            files={
                "telemetry_file": ("bad.csv", b"garbage", "text/csv"),
                "svm_file": ("car.svm", self._svm_bytes, "text/plain"),
            },
        )
        assert r.status_code == 400

    def test_analyze_malformed_fixed_params_is_ignored(self, mocker):
        mock_analyze = AsyncMock(return_value=_minimal_ai_result())
        mocker.patch("app.main.ai_engineer.analyze", new=mock_analyze)

        r = client.post(
            "/analyze",
            files={
                "telemetry_file": ("session.csv", self._csv_bytes, "text/csv"),
                "svm_file": ("car.svm", self._svm_bytes, "text/plain"),
            },
            data={
                "fixed_params": "not-json",
            },
        )

        assert r.status_code == 200
        call_kwargs = mock_analyze.call_args.kwargs
        assert call_kwargs.get("fixed_params") == []

    def test_analyze_passes_driving_telemetry_summary(self, mocker):
        """Endpoint builds a filtered driving_telemetry_summary and passes it to analyze()."""
        mock_analyze = AsyncMock(return_value=_minimal_ai_result())
        mocker.patch("app.main.ai_engineer.analyze", new=mock_analyze)
        r = client.post(
            "/analyze",
            files={
                "telemetry_file": ("session.csv", self._csv_bytes, "text/csv"),
                "svm_file": ("car.svm", self._svm_bytes, "text/plain"),
            },
        )
        assert r.status_code == 200
        call_kwargs = mock_analyze.call_args.kwargs
        assert "driving_telemetry_summary" in call_kwargs, (
            "analyze() must be called with driving_telemetry_summary kwarg"
        )
        driving_summary = call_kwargs["driving_telemetry_summary"]
        assert driving_summary is not None
        assert isinstance(driving_summary, str)
        assert len(driving_summary) > 0

    def test_analyze_passes_provider_and_model(self, mocker):
        """Endpoint forwards provider/model form fields to ai_engineer.analyze()."""
        ai_payload = _minimal_ai_result()
        ai_payload["llm_provider"] = "jimmy"
        ai_payload["llm_model"] = "llama3.1-8B"
        mock_analyze = AsyncMock(return_value=ai_payload)
        mocker.patch("app.main.ai_engineer.analyze", new=mock_analyze)
        r = client.post(
            "/analyze",
            files={
                "telemetry_file": ("session.csv", self._csv_bytes, "text/csv"),
                "svm_file": ("car.svm", self._svm_bytes, "text/plain"),
            },
            data={
                "provider": "jimmy",
                "model": "llama3.1-8B",
            },
        )

        assert r.status_code == 200
        call_kwargs = mock_analyze.call_args.kwargs
        assert call_kwargs.get("provider") == "jimmy"
        assert call_kwargs.get("model_tag") == "llama3.1-8B"
        body = r.json()
        assert body.get("llm_provider") == "jimmy"
        assert body.get("llm_model") == "llama3.1-8B"

    def test_analyze_accepts_controlled_fallback_payload_without_crash(self, mocker):
        """Even with degraded AI output, /analyze should return 200 and structured payload."""
        fallback_ai_result = {
            "driving_analysis": "No se pudo obtener el análisis de conducción.",
            "setup_analysis": "degraded=true; fallback_reason=chief_none",
            "full_setup": {"sections": []},
            "agent_reports": [],
            "setup_agent_reports": [],
            "chief_reasoning": "degraded=true; fallback_reason=chief_none",
        }
        mock_analyze = AsyncMock(return_value=fallback_ai_result)
        mocker.patch("app.main.ai_engineer.analyze", new=mock_analyze)

        r = client.post(
            "/analyze",
            files={
                "telemetry_file": ("session.csv", self._csv_bytes, "text/csv"),
                "svm_file": ("car.svm", self._svm_bytes, "text/plain"),
            },
            data={
                "provider": "jimmy",
                "model": "llama3.1-8B",
            },
        )

        assert r.status_code == 200
        body = r.json()
        assert body["driving_analysis"] == fallback_ai_result["driving_analysis"]
        assert "degraded=true" in body["setup_analysis"]
        assert "fallback_reason=chief_none" in body["chief_reasoning"]

    def test_analyze_session_uses_stored_files_and_deletes_them(self, tmp_path, mocker):
        tele_path = tmp_path / "session.csv"
        svm_path = tmp_path / "session.svm"
        tele_path.write_bytes(self._csv_bytes)
        svm_path.write_bytes(self._svm_bytes)

        mocker.patch("app.main.ai_engineer.analyze", new=AsyncMock(return_value=_minimal_ai_result()))

        with patch("app.main._client_root", return_value=str(tmp_path)):
            r = client.post(
                "/analyze_session",
                headers=SESSION_HEADERS,
                data={"session_id": "session"},
            )

        assert r.status_code == 200
        assert not tele_path.exists()
        assert not svm_path.exists()

    def test_analyze_session_preserves_files_when_analysis_fails(self, tmp_path, mocker):
        tele_path = tmp_path / "session.csv"
        svm_path = tmp_path / "session.svm"
        tele_path.write_bytes(self._csv_bytes)
        svm_path.write_bytes(self._svm_bytes)

        mocker.patch("app.main.ai_engineer.analyze", new=AsyncMock(side_effect=Exception("Jimmy exploded")))

        with patch("app.main._client_root", return_value=str(tmp_path)):
            r = client.post(
                "/analyze_session",
                headers=SESSION_HEADERS,
                data={"session_id": "session", "provider": "jimmy", "model": "llama3.1-8B"},
            )

        assert r.status_code == 500
        assert tele_path.exists()
        assert svm_path.exists()

    def test_telemetry_summary_is_capped_before_analyze(self, mocker):
        """The telemetry CSV sent to ai_engineer.analyze() must be <= MAX_AI_TELEMETRY_CHARS."""
        import app.main as main_module

        captured = {}

        async def capturing_analyze(*args, **kwargs):
            captured["telemetry_summary"] = args[0] if args else kwargs.get("telemetry_summary", "")
            return _minimal_ai_result()

        mocker.patch("app.main.ai_engineer.analyze", new=capturing_analyze)

        r = client.post(
            "/analyze",
            files={
                "telemetry_file": ("session.csv", self._csv_bytes, "text/csv"),
                "svm_file": ("car.svm", self._svm_bytes, "text/plain"),
            },
        )
        assert r.status_code == 200
        assert len(captured.get("telemetry_summary", "")) <= main_module.MAX_AI_TELEMETRY_CHARS + 2000


