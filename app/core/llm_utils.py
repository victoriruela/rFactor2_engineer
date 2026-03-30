"""Ollama / LLM utility functions shared across the AI pipeline."""

from __future__ import annotations

import os
import re
import subprocess
import time

import requests

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL_TAG: str = os.getenv("OLLAMA_MODEL", "llama3.2:latest")

JIMMY_API_URL: str = os.getenv("JIMMY_API_URL", "https://chatjimmy.ai/api/chat")
JIMMY_MODEL_TAG: str = "llama3.1-8B"
JIMMY_STATS_RE: re.Pattern = re.compile(r"<\|stats\|>.*?<\|/stats\|>", re.DOTALL)
JIMMY_RUNTIME_CONFIG_PATH: str = "app/core/jimmy_runtime_config.v1.json"
# Jimmy llama3.1-8B has ~8K token context; keep total prompt well under that.
JIMMY_MAX_TELEMETRY_CHARS: int = 4_000

# Sections related to tyre/suspension analysed together
TIRE_SUSP_SECTIONS: frozenset = frozenset(
    {"FRONTLEFT", "FRONTRIGHT", "REARLEFT", "REARRIGHT", "SUSPENSION"}
)

# ---------------------------------------------------------------------------
# Ollama process management
# ---------------------------------------------------------------------------


def _find_ollama_exe() -> str | None:
    """Locate the Ollama executable in known paths."""
    candidates = [
        "ollama",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"),
    ]
    for candidate in candidates:
        if candidate == "ollama" or os.path.isfile(candidate):
            try:
                subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
                return candidate
            except Exception:
                continue
    return None


def _ensure_ollama_running() -> bool:
    """Start the Ollama server if it is not already reachable."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    print("Ollama no está corriendo. Intentando arrancar...")
    ollama_exe = _find_ollama_exe()
    if not ollama_exe:
        print("ADVERTENCIA: ollama no está instalado en el sistema.")
        return False

    try:
        subprocess.Popen(
            [ollama_exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        for _ in range(15):
            time.sleep(1)
            try:
                r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
                if r.status_code == 200:
                    print("Ollama arrancado correctamente.")
                    return True
            except Exception:
                pass
    except FileNotFoundError:
        print("ADVERTENCIA: no se pudo arrancar ollama.")
    return False


def list_available_models(base_url: str | None = None, api_key: str | None = None) -> list[str]:
    """Return the list of models available in Ollama (local or remote).

    Args:
        base_url: Ollama base URL. Uses ``OLLAMA_BASE_URL`` env var when *None*.
        api_key: Bearer token for authentication (Ollama Cloud or remote endpoint).
    """
    effective_url = base_url or OLLAMA_BASE_URL
    headers: dict = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if not base_url:
        _ensure_ollama_running()
    try:
        r = requests.get(f"{effective_url}/api/tags", headers=headers, timeout=5)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def _extract_numeric(val_str: str) -> float | None:
    """Extract the first numeric value from a string.

    Examples::

        >>> _extract_numeric("223 N/mm")
        223.0
        >>> _extract_numeric("-3 °")
        -3.0
    """
    val_str = str(val_str).strip()
    m = re.match(r"^([+-]?\d+\.?\d*)", val_str)
    if m:
        return float(m.group(1))
    return None


def _compute_change_pct(current_clean: str, new_clean: str) -> str | None:
    """Compute a human-readable percentage change string.

    Returns ``'(+12.5%)'``, ``'(-5.0%)'``, ``'(nuevo)'``, or *None* when
    the values cannot be compared numerically.
    """
    curr_num = _extract_numeric(current_clean)
    new_num = _extract_numeric(new_clean)
    if curr_num is None or new_num is None:
        return None
    if curr_num == new_num:
        return None
    if curr_num == 0:
        return "(nuevo)" if new_num != 0 else None
    pct = ((new_num - curr_num) / abs(curr_num)) * 100
    sign = "+" if pct > 0 else ""
    return f"({sign}{pct:.1f}%)"
