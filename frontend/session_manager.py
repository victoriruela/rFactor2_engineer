"""Session-local file lifecycle helpers for Streamlit frontend."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
import uuid

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def ensure_temp_upload_root(temp_upload_root: str) -> str:
    os.makedirs(temp_upload_root, exist_ok=True)
    return temp_upload_root


def cleanup_stale_temp_dirs(temp_upload_root: str, max_age_hours: int = 4) -> None:
    if not os.path.isdir(temp_upload_root):
        return
    now = time.time()
    cutoff = now - max_age_hours * 3600
    for entry in os.scandir(temp_upload_root):
        if entry.is_dir(follow_symlinks=False):
            try:
                if entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry.path, ignore_errors=True)
            except OSError:
                continue


def cleanup_temp_session_files(state: dict) -> None:
    temp_dir = state.pop("temp_upload_dir", None)
    for key in ("telemetry_temp_path", "svm_temp_path", "tele_name", "svm_name", "selected_session_id"):
        state.pop(key, None)

    if temp_dir and os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


def write_uploaded_file_in_chunks(uploaded_file, target_path: str, chunk_size: int) -> None:
    uploaded_file.seek(0)
    with open(target_path, "wb") as temp_file:
        while True:
            chunk = uploaded_file.read(chunk_size)
            if not chunk:
                break
            temp_file.write(chunk)
    uploaded_file.seek(0)


def persist_uploaded_session(telemetry_file, svm_file, temp_upload_root: str, chunk_size: int) -> dict:
    temp_root = ensure_temp_upload_root(temp_upload_root)
    session_dir = tempfile.mkdtemp(prefix=f"rf2-session-{uuid.uuid4()}-", dir=temp_root)

    tele_name = os.path.basename(telemetry_file.name)
    svm_name = os.path.basename(svm_file.name)
    tele_path = os.path.join(session_dir, tele_name)
    svm_path = os.path.join(session_dir, svm_name)

    write_uploaded_file_in_chunks(telemetry_file, tele_path, chunk_size)
    write_uploaded_file_in_chunks(svm_file, svm_path, chunk_size)

    return {
        "temp_upload_dir": session_dir,
        "telemetry_temp_path": tele_path,
        "svm_temp_path": svm_path,
        "tele_name": tele_name,
        "svm_name": svm_name,
    }


def is_valid_session_id(value: object) -> bool:
    return isinstance(value, str) and bool(SESSION_ID_PATTERN.fullmatch(value.strip()))


def new_client_session_id() -> str:
    return uuid.uuid4().hex


def ensure_client_session_id(state: dict, preferred_session_id: str | None = None) -> str:
    if is_valid_session_id(preferred_session_id):
        state["client_session_id"] = preferred_session_id.strip()
        return state["client_session_id"]

    existing = state.get("client_session_id")
    if is_valid_session_id(existing):
        return existing

    generated = new_client_session_id()
    state["client_session_id"] = generated
    return generated
