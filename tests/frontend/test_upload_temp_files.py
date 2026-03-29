import io
import sys
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import sentinel

import pytest


_st_mock = MagicMock()
_st_mock.session_state = {}
_st_mock.file_uploader.return_value = None
_st_mock.sidebar.__enter__ = lambda s: s
_st_mock.sidebar.__exit__ = lambda *a: False
sys.modules.setdefault("streamlit", _st_mock)
sys.modules.setdefault("streamlit.components", MagicMock())
sys.modules.setdefault("streamlit.components.v1", MagicMock())

from frontend import streamlit_app  # noqa: E402


class FakeUploadedFile:
    def __init__(self, name, content):
        self.name = name
        self._buffer = io.BytesIO(content)

    def read(self, size=-1):
        return self._buffer.read(size)

    def seek(self, offset, whence=0):
        return self._buffer.seek(offset, whence)


def test_write_uploaded_file_in_chunks_writes_complete_file_and_resets_cursor(tmp_path):
    content = (b"abcdefgh" * 1024) + b"tail"
    uploaded = FakeUploadedFile("session.mat", content)
    target_path = tmp_path / "session.mat"

    streamlit_app._write_uploaded_file_in_chunks(uploaded, target_path, chunk_size=1024)

    assert target_path.read_bytes() == content
    assert uploaded.read(8) == content[:8]


def test_persist_uploaded_session_creates_temp_files_under_session_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(streamlit_app, "TEMP_UPLOAD_ROOT", str(tmp_path))
    telemetry = FakeUploadedFile("telemetry.csv", b"csv-content")
    svm = FakeUploadedFile("setup.svm", b"svm-content")

    session_files = streamlit_app._persist_uploaded_session(telemetry, svm)

    assert Path(session_files["temp_upload_dir"]).exists()
    assert session_files["tele_name"] == "telemetry.csv"
    assert session_files["svm_name"] == "setup.svm"
    assert Path(session_files["telemetry_temp_path"]).read_bytes() == b"csv-content"
    assert Path(session_files["svm_temp_path"]).read_bytes() == b"svm-content"


def test_cleanup_temp_session_files_removes_directory_and_state(tmp_path):
    session_dir = tmp_path / "rf2-session"
    session_dir.mkdir()
    temp_file = session_dir / "telemetry.csv"
    temp_file.write_bytes(b"content")

    streamlit_app.st.session_state.clear()
    streamlit_app.st.session_state.update({
        "temp_upload_dir": str(session_dir),
        "telemetry_temp_path": str(temp_file),
        "svm_temp_path": str(session_dir / "setup.svm"),
        "tele_name": "telemetry.csv",
        "svm_name": "setup.svm",
    })

    streamlit_app._cleanup_temp_session_files()

    assert not session_dir.exists()
    assert "temp_upload_dir" not in streamlit_app.st.session_state
    assert "telemetry_temp_path" not in streamlit_app.st.session_state
    assert "svm_temp_path" not in streamlit_app.st.session_state


def test_ensure_client_session_id_generates_when_missing():
    streamlit_app.st.session_state.clear()

    generated = streamlit_app._ensure_client_session_id()

    assert isinstance(generated, str)
    assert len(generated) >= 8
    assert streamlit_app.st.session_state["client_session_id"] == generated
    assert streamlit_app._is_valid_session_id(generated)


def test_api_headers_uses_only_valid_session_id():
    streamlit_app.st.session_state.clear()
    streamlit_app.st.session_state["client_session_id"] = "***invalid***"
    assert streamlit_app._api_headers() == {}

    streamlit_app.st.session_state["client_session_id"] = "abc12345XYZ"
    assert streamlit_app._api_headers() == {"X-Client-Session-Id": "abc12345XYZ"}


def test_post_analysis_for_session_uses_long_running_timeout(mocker):
    streamlit_app.st.session_state.clear()
    streamlit_app.st.session_state["client_session_id"] = "abc12345XYZ"
    mock_post = mocker.patch("frontend.streamlit_app.requests.post", return_value=sentinel.response)

    response = streamlit_app._post_analysis_for_session("session-1", {"provider": "ollama", "model": "x"})

    assert response is sentinel.response
    mock_post.assert_called_once_with(
        f"{streamlit_app.API_BASE_URL}/analyze_session",
        data={"session_id": "session-1", "provider": "ollama", "model": "x"},
        headers={"X-Client-Session-Id": "abc12345XYZ"},
        timeout=streamlit_app.ANALYSIS_REQUEST_TIMEOUT,
    )


def test_post_analysis_with_local_files_uses_analyze_endpoint(tmp_path, mocker):
    tele_path = tmp_path / "sample.mat"
    svm_path = tmp_path / "sample.svm"
    tele_path.write_bytes(b"tele")
    svm_path.write_bytes(b"svm")

    streamlit_app.st.session_state.clear()
    streamlit_app.st.session_state.update(
        {
            "client_session_id": "abc12345XYZ",
            "telemetry_temp_path": str(tele_path),
            "svm_temp_path": str(svm_path),
            "tele_name": "sample.mat",
            "svm_name": "sample.svm",
        }
    )
    mock_post = mocker.patch("frontend.streamlit_app.requests.post", return_value=sentinel.response)

    response = streamlit_app._post_analysis_with_local_files({"provider": "jimmy"})

    assert response is sentinel.response
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["timeout"] == streamlit_app.ANALYSIS_REQUEST_TIMEOUT
    assert kwargs["headers"] == {"X-Client-Session-Id": "abc12345XYZ"}
    assert kwargs["data"] == {"provider": "jimmy"}
    assert "telemetry_file" in kwargs["files"]
    assert "svm_file" in kwargs["files"]


def test_post_analysis_with_local_files_raises_if_missing_files(mocker):
    streamlit_app.st.session_state.clear()
    streamlit_app.st.session_state.update(
        {
            "telemetry_temp_path": "C:/missing/sample.mat",
            "svm_temp_path": "C:/missing/sample.svm",
        }
    )
    mocker.patch("frontend.streamlit_app.requests.post", return_value=sentinel.response)

    with pytest.raises(FileNotFoundError):
        streamlit_app._post_analysis_with_local_files({})
