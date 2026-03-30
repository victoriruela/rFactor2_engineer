"""Track upload API with SHA256-based deduplication storage."""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

router = APIRouter()

# Directory paths (patched in tests)
PREHOSTED_TRACKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "tracks")
COMMUNITY_TRACKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tracks")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


# --- Pydantic models ---


class TrackUploadRequest(BaseModel):
    sha256_source: str
    track_json: Dict[str, Any]

    @field_validator("sha256_source")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        if not _SHA256_RE.fullmatch(v):
            raise ValueError("sha256_source must be a 64-char lowercase hex string")
        return v


class TrackUploadResponse(BaseModel):
    status: str  # "created" | "duplicate"
    content_sha256: str
    name: str


class TrackListEntry(BaseModel):
    name: str
    content_sha256: str
    source: str  # "prehosted" | "community"
    created_at: str


# --- Helper functions ---


def canonical_json(data: Any) -> str:
    """Produce deterministic JSON serialization for hashing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_content_sha256(track_json: Dict[str, Any]) -> str:
    """Compute SHA256 of the canonical JSON representation."""
    return hashlib.sha256(canonical_json(track_json).encode("utf-8")).hexdigest()


def _find_community_by_content_sha256(content_sha256: str) -> Optional[Path]:
    """Find the oldest community track file matching a content hash."""
    community_dir = Path(COMMUNITY_TRACKS_DIR)
    if not community_dir.exists():
        return None

    matches = []
    for f in community_dir.glob("*.json"):
        if f.name == ".gitkeep":
            continue
        # Filename format: {sha256_source}_{timestamp}_{content_sha256}.json
        parts = f.stem.rsplit("_", 1)
        if len(parts) == 2 and parts[1] == content_sha256:
            matches.append(f)

    if not matches:
        return None

    # Return oldest by filename (contains timestamp)
    matches.sort(key=lambda p: p.name)
    return matches[0]


def _find_prehosted_by_content_sha256(content_sha256: str) -> Optional[Path]:
    """Find a pre-hosted track matching a content hash."""
    prehosted_dir = Path(PREHOSTED_TRACKS_DIR)
    if not prehosted_dir.exists():
        return None

    for f in prehosted_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if compute_content_sha256(data) == content_sha256:
                return f
        except (json.JSONDecodeError, OSError):
            continue
    return None


# --- Endpoints ---


@router.post("/tracks/upload", response_model=TrackUploadResponse)
async def upload_track(req: TrackUploadRequest):
    """Upload a processed track JSON with SHA256 deduplication."""
    content_sha256 = compute_content_sha256(req.track_json)
    name = req.track_json.get("name", "unknown")

    # Check for duplicate in community tracks
    existing = _find_community_by_content_sha256(content_sha256)
    if existing is not None:
        return TrackUploadResponse(
            status="duplicate",
            content_sha256=content_sha256,
            name=name,
        )

    # Also check pre-hosted tracks
    if _find_prehosted_by_content_sha256(content_sha256) is not None:
        return TrackUploadResponse(
            status="duplicate",
            content_sha256=content_sha256,
            name=name,
        )

    # Write new file
    community_dir = Path(COMMUNITY_TRACKS_DIR)
    community_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    filename = f"{req.sha256_source}_{timestamp}_{content_sha256}.json"
    filepath = community_dir / filename
    filepath.write_text(json.dumps(req.track_json, indent=2), encoding="utf-8")

    return TrackUploadResponse(
        status="created",
        content_sha256=content_sha256,
        name=name,
    )


@router.get("/tracks/list", response_model=List[TrackListEntry])
async def list_tracks():
    """List all available tracks from pre-hosted and community sources."""
    entries: List[TrackListEntry] = []

    # Pre-hosted tracks
    prehosted_dir = Path(PREHOSTED_TRACKS_DIR)
    if prehosted_dir.exists():
        for f in sorted(prehosted_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                content_sha256 = compute_content_sha256(data)
                stat = f.stat()
                created_at = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()
                entries.append(TrackListEntry(
                    name=data.get("name", f.stem),
                    content_sha256=content_sha256,
                    source="prehosted",
                    created_at=created_at,
                ))
            except (json.JSONDecodeError, OSError):
                continue

    # Community tracks
    community_dir = Path(COMMUNITY_TRACKS_DIR)
    if community_dir.exists():
        # Group by content_sha256, keep oldest
        seen: dict[str, TrackListEntry] = {}
        for f in sorted(community_dir.glob("*.json"), key=lambda p: p.name):
            if f.name == ".gitkeep":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                content_sha256 = compute_content_sha256(data)
                if content_sha256 in seen:
                    continue
                stat = f.stat()
                created_at = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()
                seen[content_sha256] = TrackListEntry(
                    name=data.get("name", "unknown"),
                    content_sha256=content_sha256,
                    source="community",
                    created_at=created_at,
                )
            except (json.JSONDecodeError, OSError):
                continue
        entries.extend(seen.values())

    return entries


@router.get("/tracks/{content_sha256}")
async def get_track(content_sha256: str):
    """Get track metadata by content SHA256."""
    if not _SHA256_RE.fullmatch(content_sha256):
        raise HTTPException(status_code=400, detail="Invalid SHA256 hash")

    # Check community first (oldest entry)
    community_file = _find_community_by_content_sha256(content_sha256)
    if community_file is not None:
        data = json.loads(community_file.read_text(encoding="utf-8"))
        return {
            "name": data.get("name", "unknown"),
            "content_sha256": content_sha256,
            "source": "community",
        }

    # Check pre-hosted
    prehosted_file = _find_prehosted_by_content_sha256(content_sha256)
    if prehosted_file is not None:
        data = json.loads(prehosted_file.read_text(encoding="utf-8"))
        return {
            "name": data.get("name", prehosted_file.stem),
            "content_sha256": content_sha256,
            "source": "prehosted",
        }

    raise HTTPException(status_code=404, detail="Track not found")


@router.get("/tracks/{content_sha256}/download")
async def download_track(content_sha256: str):
    """Download full track JSON by content SHA256."""
    if not _SHA256_RE.fullmatch(content_sha256):
        raise HTTPException(status_code=400, detail="Invalid SHA256 hash")

    # Check community first
    community_file = _find_community_by_content_sha256(content_sha256)
    if community_file is not None:
        return json.loads(community_file.read_text(encoding="utf-8"))

    # Check pre-hosted
    prehosted_file = _find_prehosted_by_content_sha256(content_sha256)
    if prehosted_file is not None:
        return json.loads(prehosted_file.read_text(encoding="utf-8"))

    raise HTTPException(status_code=404, detail="Track not found")
