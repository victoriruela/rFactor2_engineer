import io
import sys
from pathlib import Path
from unittest.mock import MagicMock


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
