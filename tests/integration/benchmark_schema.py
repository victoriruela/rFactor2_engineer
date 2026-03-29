"""Schema and fixture loader scaffold for Jimmy benchmark cases.

This module is intentionally minimal for T1.
It defines the case structure and light validation needed by a future benchmark harness.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, TypedDict


class RubricExpectations(TypedDict):
    telemetry_specificity_min: int
    causal_quality_min: int
    actionability_min: int
    consistency_min: int


class BenchmarkCase(TypedDict):
    case_id: str
    description: str
    circuit_name: str
    telemetry_summary: str
    setup_data: Dict[str, Dict[str, str]]
    session_stats: Dict[str, object]
    fixed_params: List[str]
    expected_focus_sections: List[str]
    rubric_expectations: RubricExpectations


REQUIRED_KEYS = {
    "case_id",
    "description",
    "circuit_name",
    "telemetry_summary",
    "setup_data",
    "session_stats",
    "fixed_params",
    "expected_focus_sections",
    "rubric_expectations",
}


def validate_case_shape(case_data: Dict[str, object]) -> None:
    """Raise ValueError if a benchmark case misses any required key."""
    missing = sorted(REQUIRED_KEYS - set(case_data.keys()))
    if missing:
        raise ValueError(f"Benchmark case is missing required keys: {', '.join(missing)}")


def load_benchmark_case(case_path: Path) -> BenchmarkCase:
    """Load and shape-check one benchmark case fixture."""
    with case_path.open("r", encoding="utf-8") as fixture_file:
        case_data = json.load(fixture_file)
    validate_case_shape(case_data)
    return case_data  # type: ignore[return-value]


def discover_benchmark_cases(fixtures_dir: Path) -> List[Path]:
    """Return sorted benchmark case files, excluding the template."""
    return sorted(
        path
        for path in fixtures_dir.glob("case_*.json")
        if path.name != "case_template.json"
    )
