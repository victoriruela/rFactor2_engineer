"""Frontend runtime constants loaded from environment variables."""

from __future__ import annotations

import os
import tempfile

API_BASE_URL: str = os.environ.get("RF2_API_URL", "http://localhost:8000")
BROWSER_API_BASE_URL: str = os.environ.get("RF2_BROWSER_API_BASE_URL", "/api")
UPLOAD_CHUNK_SIZE: int = 16 * 1024 * 1024
ANALYSIS_REQUEST_TIMEOUT = (10, 1800)
TEMP_UPLOAD_ROOT: str = os.path.join(tempfile.gettempdir(), "rfactor2_engineer_uploads")
MAT_PREVIEW_MAX_MB: int = int(os.environ.get("RF2_FRONTEND_MAX_PREVIEW_MAT_MB", "800"))
FIXED_PARAMS_FILE: str = "app/core/fixed_params.json"
PARAM_MAPPING_FILE: str = os.path.join("app", "core", "param_mapping.json")
