import json
from pathlib import Path

import pytest

from scripts.benchmark_prompt_matrix import (
    _compute_coverage_rate,
    _load_prompt_matrix,
    _percentile_ms,
    compute_run_metrics,
    extract_first_json_object,
    is_non_empty_driving_analysis,
    strip_jimmy_artifacts,
)


def test_strip_jimmy_artifacts_removes_stats_and_wrapping_quotes():
    raw = '"respuesta valida<|stats|>{\"tokens\":42}<|/stats|>"'
    assert strip_jimmy_artifacts(raw) == "respuesta valida"


def test_extract_first_json_object_parses_embedded_json():
    raw = "texto previo {\"items\": [{\"parameter\": \"X\"}], \"summary\": \"ok\"} texto"
    parsed = extract_first_json_object(raw)
    assert parsed is not None
    assert parsed["summary"] == "ok"


def test_extract_first_json_object_handles_trailing_comma():
    raw = "{\"items\": [], \"summary\": \"ok\",}"
    parsed = extract_first_json_object(raw)
    assert parsed is not None
    assert parsed["items"] == []


def test_is_non_empty_driving_analysis_rules():
    assert not is_non_empty_driving_analysis("")
    assert not is_non_empty_driving_analysis("No se pudo obtener el analisis de conduccion.")
    assert not is_non_empty_driving_analysis("corto")
    assert is_non_empty_driving_analysis("A" * 80)


def test_compute_coverage_rate_expected_sections():
    expected = ["SUSPENSION", "FRONTLEFT", "FRONTRIGHT"]
    covered = {"SUSPENSION": 2, "FRONTRIGHT": 1}
    assert _compute_coverage_rate(expected, covered) == pytest.approx(2 / 3)


def test_percentile_ms_linear_interpolation():
    values = [100.0, 120.0, 160.0, 200.0]
    assert _percentile_ms(values, 0.95) == pytest.approx(194.0)


def test_compute_run_metrics_aggregates_all_fields():
    case_results = [
        {
            "case_id": "case_1",
            "specialist_total": 2,
            "specialist_valid": 2,
            "chief_valid": True,
            "driving_analysis_non_empty": True,
            "latency_ms": 1000.0,
            "coverage_rate": 1.0,
        },
        {
            "case_id": "case_2",
            "specialist_total": 2,
            "specialist_valid": 1,
            "chief_valid": False,
            "driving_analysis_non_empty": False,
            "latency_ms": 2000.0,
            "coverage_rate": 0.5,
        },
    ]

    metrics = compute_run_metrics(case_results)

    assert metrics["json_validity_rate"] == pytest.approx(4 / 6)
    assert metrics["driving_analysis_non_empty_rate"] == pytest.approx(0.5)
    assert metrics["recommendation_coverage_by_section"]["average"] == pytest.approx(0.75)
    assert metrics["latency_ms"]["average"] == pytest.approx(1500.0)
    assert metrics["latency_ms"]["p95"] == pytest.approx(1950.0)
    assert metrics["qualitative_rubric"]["status"] == "pending_manual_scoring"


def test_load_prompt_matrix_validates_and_normalizes(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    payload = {
        "runs": [
            {
                "run_id": "r1",
                "prompt_variant": "baseline",
                "systemPrompt": "system",
                "topK": 4,
                "temperature": 0.2,
                "metadata": {"owner": "qa"},
            }
        ]
    }
    matrix_path.write_text(json.dumps(payload), encoding="utf-8")

    runs = _load_prompt_matrix(matrix_path)
    assert len(runs) == 1
    assert runs[0]["run_id"] == "r1"
    assert runs[0]["temperature"] == pytest.approx(0.2)


def test_load_prompt_matrix_rejects_invalid_topk(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    payload = {
        "runs": [
            {
                "run_id": "bad",
                "prompt_variant": "baseline",
                "systemPrompt": "",
                "topK": 0,
                "temperature": 0.1,
                "metadata": {},
            }
        ]
    }
    matrix_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        _load_prompt_matrix(matrix_path)
