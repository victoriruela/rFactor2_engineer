"""Centralized runtime settings for backend services."""

from __future__ import annotations

import os

DATA_DIR = os.getenv("RF2_DATA_DIR", "data")
UPLOAD_CHUNK_SIZE = int(os.getenv("RF2_UPLOAD_CHUNK_SIZE", str(16 * 1024 * 1024)))
MAX_AI_TELEMETRY_CHARS = int(os.getenv("RF2_MAX_AI_TELEMETRY_CHARS", "15000"))
MAX_TELEMETRY_COLUMNS = int(os.getenv("RF2_MAX_TELEMETRY_COLUMNS", "100"))
AI_SAMPLES_PER_LAP = int(os.getenv("RF2_AI_SAMPLES_PER_LAP", "50"))
MAP_MAX_POINTS = int(os.getenv("RF2_MAP_MAX_POINTS", "5000"))
CHUNK_STALE_HOURS = int(os.getenv("RF2_CHUNK_STALE_HOURS", "24"))
ANALYSIS_TMP_STALE_HOURS = int(os.getenv("RF2_ANALYSIS_TMP_STALE_HOURS", "6"))
