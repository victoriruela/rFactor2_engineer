"""Parser for rFactor2 .AIW (AI Waypoint) files.

Extracts waypoint positions and track widths, producing a JSON-compatible
dict suitable for 3D track rendering.

AIW coordinate system: X=east, Y=up (elevation), Z=south.
Output mapping: x=AIW_X, y=AIW_Z, z=AIW_Y  (so z is always elevation).
"""

import re
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form

router = APIRouter(prefix="/tracks", tags=["tracks"])

# Regex for float tuples inside parentheses
_FLOAT = r"-?\d*\.?\d+"
_POS_RE = re.compile(
    rf"wp_pos=\(\s*({_FLOAT})\s*,\s*({_FLOAT})\s*,\s*({_FLOAT})\s*\)"
)
_WIDTH_RE = re.compile(
    rf"wp_width=\(\s*({_FLOAT})\s*,\s*({_FLOAT})\s*,\s*{_FLOAT}\s*,\s*{_FLOAT}\s*\)"
)


def parse_aiw(file_content: str, track_name: str = "Unknown") -> dict:
    """Parse an AIW file and return a track-data dict.

    Parameters
    ----------
    file_content : str
        Full text content of the .aiw file.
    track_name : str, optional
        Human-readable track name (default ``"Unknown"``).

    Returns
    -------
    dict
        ``{"name": str, "source": "aiw", "points": [...]}``.
        Each point has keys ``x``, ``y``, ``z``, ``width_left``,
        ``width_right`` (all floats).
    """
    positions = _POS_RE.findall(file_content)
    widths = _WIDTH_RE.findall(file_content)

    points: list[dict] = []
    for i, (aiw_x, aiw_y, aiw_z) in enumerate(positions):
        if i < len(widths):
            w_left, w_right = float(widths[i][0]), float(widths[i][1])
        else:
            w_left, w_right = 0.0, 0.0

        points.append(
            {
                "x": float(aiw_x),
                "y": float(aiw_z),   # AIW_Z -> our y (horizontal)
                "z": float(aiw_y),   # AIW_Y -> our z (elevation)
                "width_left": w_left,
                "width_right": w_right,
            }
        )

    return {
        "name": track_name,
        "source": "aiw",
        "points": points,
    }


# ---------- FastAPI endpoint ----------


@router.post("/parse-aiw")
async def parse_aiw_endpoint(
    file: UploadFile = File(...),
    track_name: Optional[str] = Form("Unknown"),
):
    """Accept an uploaded .aiw file and return parsed track JSON."""
    content = (await file.read()).decode("utf-8", errors="replace")
    return parse_aiw(content, track_name=track_name or "Unknown")
