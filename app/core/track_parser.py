"""Parse rFactor2 .aiw (AI Waypoint) files to extract track centreline data."""

from __future__ import annotations

import re
from typing import Any


_WAYPOINT_RE = re.compile(
    r"pos\s*=\s*\(\s*"
    r"(?P<x>-?[\d.]+)\s*,\s*"
    r"(?P<y>-?[\d.]+)\s*,\s*"
    r"(?P<z>-?[\d.]+)\s*\)",
    re.IGNORECASE,
)

_TRACK_NAME_RE = re.compile(
    r"^\s*trackName\s*=\s*(.+)",
    re.IGNORECASE | re.MULTILINE,
)


def parse_aiw_text(aiw_text: str) -> dict[str, Any]:
    """Parse raw AIW text and return track JSON.

    Returns a dict with keys:
        - track_name: str (or "Unknown" if not found)
        - points: list[dict] with x, y, z floats
        - point_count: int
    """
    # Extract track name
    name_match = _TRACK_NAME_RE.search(aiw_text)
    track_name = name_match.group(1).strip() if name_match else "Unknown"

    # Extract waypoints
    points: list[dict[str, float]] = []
    for m in _WAYPOINT_RE.finditer(aiw_text):
        points.append({
            "x": float(m.group("x")),
            "y": float(m.group("y")),
            "z": float(m.group("z")),
        })

    return {
        "track_name": track_name,
        "points": points,
        "point_count": len(points),
    }
