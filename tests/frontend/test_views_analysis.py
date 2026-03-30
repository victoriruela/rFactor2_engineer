"""Unit tests for frontend/views/analysis_view.py — non-UI logic.

_post_analysis() and the results-formatting helpers are tested here.
Streamlit is mocked before import to avoid UI execution.
"""
import sys
from unittest.mock import MagicMock, sentinel

# ── Streamlit mock ──────────────────────────────────────────────────────────
if "streamlit" not in sys.modules:
    _m = MagicMock()
    _m.session_state = {}
    sys.modules["streamlit"] = _m
if "streamlit.components" not in sys.modules:
    sys.modules["streamlit.components"] = MagicMock()
if "streamlit.components.v1" not in sys.modules:
    sys.modules["streamlit.components.v1"] = MagicMock()
# Authoritative reference — same object that analysis_view.py imported as `st`
_st_mock = sys.modules["streamlit"]
if not isinstance(getattr(_st_mock, "session_state", None), dict):
    _st_mock.session_state = {}
# ─────────────────────────────────────────────────────────────────────────────

import frontend.views.analysis_view as av  # noqa: E402


# ---------------------------------------------------------------------------
# _post_analysis
# ---------------------------------------------------------------------------

class TestPostAnalysis:
    def setup_method(self):
        _st_mock.session_state.clear()
        _st_mock.error.reset_mock()

    def test_returns_none_when_tele_missing(self, tmp_path):
        svm_path = tmp_path / "setup.svm"
        svm_path.write_bytes(b"svm")
        _st_mock.session_state["svm_name"] = "setup.svm"

        result = av._post_analysis(
            str(tmp_path / "missing.mat"), str(svm_path), "lap.mat", {}
        )
        assert result is None
        _st_mock.error.assert_called()

    def test_returns_none_when_svm_missing(self, tmp_path):
        tele_path = tmp_path / "lap.mat"
        tele_path.write_bytes(b"mat")
        _st_mock.session_state["svm_name"] = "missing.svm"

        result = av._post_analysis(
            str(tele_path), str(tmp_path / "missing.svm"), "lap.mat", {}
        )
        assert result is None
        _st_mock.error.assert_called()

    def test_calls_api_client_with_correct_args(self, tmp_path, mocker):
        tele_path = tmp_path / "lap.mat"
        svm_path = tmp_path / "setup.svm"
        tele_path.write_bytes(b"tele")
        svm_path.write_bytes(b"svm")

        _st_mock.session_state["svm_name"] = "setup.svm"
        _st_mock.session_state["client_session_id"] = "sess123"

        mock_post = mocker.patch(
            "frontend.views.analysis_view.api_client.post_analyze_with_files",
            return_value=sentinel.response,
        )

        result = av._post_analysis(
            str(tele_path), str(svm_path), "lap.mat", {"provider": "ollama"}
        )

        assert result is sentinel.response
        args, _ = mock_post.call_args
        assert args[1] == "sess123"          # session id
        assert args[2] == {"provider": "ollama"}  # data_form
        assert "telemetry_file" in args[3]
        assert "svm_file" in args[3]

    def test_uses_svm_name_from_session_state(self, tmp_path, mocker):
        tele_path = tmp_path / "lap.mat"
        svm_path = tmp_path / "setup.svm"
        tele_path.write_bytes(b"tele")
        svm_path.write_bytes(b"svm")

        _st_mock.session_state["svm_name"] = "my_setup.svm"
        mock_post = mocker.patch(
            "frontend.views.analysis_view.api_client.post_analyze_with_files",
            return_value=sentinel.response,
        )

        av._post_analysis(str(tele_path), str(svm_path), "lap.mat", {})
        args, _ = mock_post.call_args
        files = args[3]
        svm_name_in_call = files["svm_file"][0]
        assert svm_name_in_call == "my_setup.svm"

    def test_falls_back_to_basename_when_svm_name_missing(self, tmp_path, mocker):
        tele_path = tmp_path / "lap.mat"
        svm_path = tmp_path / "setup.svm"
        tele_path.write_bytes(b"tele")
        svm_path.write_bytes(b"svm")

        _st_mock.session_state.pop("svm_name", None)
        mock_post = mocker.patch(
            "frontend.views.analysis_view.api_client.post_analyze_with_files",
            return_value=sentinel.response,
        )

        av._post_analysis(str(tele_path), str(svm_path), "lap.mat", {})
        args, _ = mock_post.call_args
        files = args[3]
        assert files["svm_file"][0] == "setup.svm"


# ---------------------------------------------------------------------------
# _normalize_model_list
# ---------------------------------------------------------------------------


class TestNormalizeModelList:
    def test_sorts_case_insensitive_and_deduplicates(self):
        models = ["llama3.2:latest", "mistral:latest", "LLaMA3.2:latest", "mistral:latest"]
        result = av._normalize_model_list(models)
        assert result == ["llama3.2:latest", "mistral:latest"]

    def test_ignores_non_string_and_empty_values(self):
        models = ["", "  ", None, 123, "qwen2.5:7b", " qwen2.5:7b "]
        result = av._normalize_model_list(models)
        assert result == ["qwen2.5:7b"]

    def test_returns_empty_list_when_no_valid_models(self):
        assert av._normalize_model_list(["", " ", None]) == []
