"""Chunked and direct upload helpers."""

from __future__ import annotations

import json
import os
import shutil
import uuid

from fastapi import HTTPException, Request, UploadFile

from app.config import settings
from app.services import session_service


async def write_upload_to_disk(
    upload_file: UploadFile,
    destination_path: str,
    chunk_size: int = settings.UPLOAD_CHUNK_SIZE,
) -> None:
    with open(destination_path, "wb") as output_file:
        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break
            output_file.write(chunk)


def init_upload(filename: str, client_session_id: str) -> dict:
    session_service.prune_stale_chunks(client_session_id)
    upload_id = str(uuid.uuid4())
    chunk_dir = session_service.chunk_root(client_session_id)
    os.makedirs(chunk_dir, exist_ok=True)

    safe_name = session_service.safe_filename(filename)
    meta = {"filename": safe_name, "next_chunk": 0, "bytes_received": 0}

    part_path = session_service.chunk_part_path(client_session_id, upload_id)
    with open(part_path, "wb") as _:
        pass

    with open(session_service.chunk_meta_path(client_session_id, upload_id), "w", encoding="utf-8") as handle:
        json.dump(meta, handle)

    return {"upload_id": upload_id, "chunk_size": settings.UPLOAD_CHUNK_SIZE, "filename": safe_name}


async def append_chunk(upload_id: str, request: Request, chunk_index: int, client_session_id: str) -> dict:
    meta_path = session_service.chunk_meta_path(client_session_id, upload_id)
    part_path = session_service.chunk_part_path(client_session_id, upload_id)
    if not os.path.exists(meta_path) or not os.path.exists(part_path):
        raise HTTPException(status_code=404, detail="Upload not initialized")

    with open(meta_path, "r", encoding="utf-8") as handle:
        meta = json.load(handle)

    expected_index = int(meta.get("next_chunk", 0))
    if chunk_index != expected_index:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid chunk index. Expected {expected_index}, received {chunk_index}",
        )

    body = await request.body()
    if body is None:
        raise HTTPException(status_code=400, detail="Missing chunk body")

    with open(part_path, "ab") as part_file:
        part_file.write(body)

    meta["next_chunk"] = expected_index + 1
    meta["bytes_received"] = int(meta.get("bytes_received", 0)) + len(body)
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(meta, handle)

    return {
        "upload_id": upload_id,
        "chunk_index": chunk_index,
        "bytes_received": meta["bytes_received"],
    }


def complete_upload(upload_id: str, client_session_id: str, root_resolver=session_service.client_root) -> dict:
    meta_path = session_service.chunk_meta_path(client_session_id, upload_id)
    part_path = session_service.chunk_part_path(client_session_id, upload_id)
    if not os.path.exists(meta_path) or not os.path.exists(part_path):
        raise HTTPException(status_code=404, detail="Upload not initialized")

    with open(meta_path, "r", encoding="utf-8") as handle:
        meta = json.load(handle)

    client_root = root_resolver(client_session_id)
    os.makedirs(client_root, exist_ok=True)

    final_name = session_service.safe_filename(meta.get("filename", ""))
    final_path = os.path.join(client_root, final_name)

    if os.path.exists(final_path):
        os.remove(final_path)
    shutil.move(part_path, final_path)
    os.remove(meta_path)

    return {"filename": final_name, "bytes_received": int(meta.get("bytes_received", 0))}
