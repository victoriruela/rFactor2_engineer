"""Session-related filesystem operations."""

from __future__ import annotations

import datetime as dt
import os
import re
from typing import Dict, List, Optional

from fastapi import Cookie, Header, HTTPException

from app.config import settings

SESSION_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def normalize_session_id(raw_session_id: Optional[str]) -> str:
    if not raw_session_id:
        raise HTTPException(status_code=400, detail="Missing session identifier")

    normalized = raw_session_id.strip()
    if not SESSION_ID_REGEX.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="Invalid session identifier")
    return normalized


def resolve_client_session_id(
    x_client_session_id: Optional[str] = Header(None),
    rf2_session_id: Optional[str] = Cookie(None),
) -> str:
    return normalize_session_id(x_client_session_id or rf2_session_id)


def client_root(client_session_id: str) -> str:
    return os.path.join(settings.DATA_DIR, client_session_id)


def chunk_root(client_session_id: str) -> str:
    return os.path.join(client_root(client_session_id), "_chunks")


def chunk_meta_path(client_session_id: str, upload_id: str) -> str:
    return os.path.join(chunk_root(client_session_id), f"{upload_id}.json")


def chunk_part_path(client_session_id: str, upload_id: str) -> str:
    return os.path.join(chunk_root(client_session_id), f"{upload_id}.part")


def prune_stale_chunks(client_session_id: str) -> int:
    """Delete stale partial uploads (.part/.json) older than configured threshold."""
    root = chunk_root(client_session_id)
    if not os.path.isdir(root):
        return 0

    now = dt.datetime.now(dt.timezone.utc).timestamp()
    max_age_seconds = max(1, settings.CHUNK_STALE_HOURS) * 3600
    deleted = 0

    for name in os.listdir(root):
        if not name.endswith((".part", ".json")):
            continue
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        try:
            age = now - os.path.getmtime(path)
            if age >= max_age_seconds:
                os.remove(path)
                deleted += 1
        except OSError:
            continue
    return deleted


def safe_filename(filename: str) -> str:
    safe = os.path.basename((filename or "").strip())
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe


def list_client_sessions(client_session_id: str, root_resolver=client_root) -> List[Dict[str, str]]:
    root = root_resolver(client_session_id)
    if not os.path.exists(root):
        return []

    grouped: Dict[str, Dict[str, str]] = {}
    for name in os.listdir(root):
        full_path = os.path.join(root, name)
        if not os.path.isfile(full_path):
            continue

        lower = name.lower()
        if not lower.endswith((".mat", ".csv", ".svm")):
            continue

        base = name.rsplit(".", 1)[0]
        grouped.setdefault(base, {})
        if lower.endswith(".svm"):
            grouped[base]["svm"] = name
        else:
            grouped[base]["telemetry"] = name

    sessions: List[Dict[str, str]] = []
    for base, files in grouped.items():
        if "telemetry" in files and "svm" in files:
            sessions.append(
                {
                    "id": base,
                    "display_name": base,
                    "telemetry": files["telemetry"],
                    "svm": files["svm"],
                }
            )
    return sorted(sessions, key=lambda x: x["display_name"], reverse=True)


def find_session_pair(client_session_id: str, session_id: str, root_resolver=client_root) -> Dict[str, str]:
    target = session_id.strip()
    for item in list_client_sessions(client_session_id, root_resolver=root_resolver):
        if item["id"] == target:
            return item
    raise HTTPException(status_code=404, detail="Session not found")


def cleanup_client_data(client_session_id: str, root_resolver=client_root) -> Dict[str, int | str]:
    client_dir = root_resolver(client_session_id)
    if not os.path.exists(client_dir):
        return {"status": "ok", "message": "No data directory"}

    deleted_count = 0
    for root, _dirs, files in os.walk(client_dir):
        for file in files:
            if file.lower().endswith((".mat", ".csv", ".svm", ".part", ".json")):
                try:
                    os.remove(os.path.join(root, file))
                    deleted_count += 1
                except OSError:
                    pass

    for root, dirs, _files in os.walk(client_dir, topdown=False):
        for name in dirs:
            dir_path = os.path.join(root, name)
            if os.path.isdir(dir_path) and not os.listdir(dir_path):
                os.rmdir(dir_path)

    if os.path.isdir(client_dir) and not os.listdir(client_dir):
        os.rmdir(client_dir)

    return {"status": "ok", "deleted_files": deleted_count}


def cleanup_all_data(data_dir: str = settings.DATA_DIR) -> Dict[str, int | str]:
    """Delete every stored session/chunk/temp analysis artifact.

    This supports strict ephemeral mode where no data should survive page reloads.
    """
    if not os.path.isdir(data_dir):
        return {"status": "ok", "message": "No data directory", "deleted_files": 0}

    deleted_files = 0
    deleted_dirs = 0

    for root, _dirs, files in os.walk(data_dir):
        for file in files:
            try:
                os.remove(os.path.join(root, file))
                deleted_files += 1
            except OSError:
                continue

    for entry in os.scandir(data_dir):
        if entry.is_dir(follow_symlinks=False):
            try:
                os.rmdir(entry.path)
                deleted_dirs += 1
            except OSError:
                # Non-empty dir (rare race) or permission issue: best effort cleanup.
                try:
                    for subroot, subdirs, _ in os.walk(entry.path, topdown=False):
                        for name in subdirs:
                            subdir = os.path.join(subroot, name)
                            if os.path.isdir(subdir) and not os.listdir(subdir):
                                os.rmdir(subdir)
                    if os.path.isdir(entry.path) and not os.listdir(entry.path):
                        os.rmdir(entry.path)
                        deleted_dirs += 1
                except OSError:
                    continue

    return {"status": "ok", "deleted_files": deleted_files, "deleted_dirs": deleted_dirs}
