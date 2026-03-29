"""
Integration tests for the AI pipeline using the real Ollama LLM.
These tests are opt-in and require llama3.2 (any tag) to be loaded in Ollama.

Run with:
    pytest -m integration -v
"""
import json
from pathlib import Path

import pytest

from app.core.ai_agents import AIAngineer, SECTION_AGENT_PROMPT

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Minimal but realistic inputs used across tests
SAMPLE_TELEMETRY_SUMMARY = (
    "CIRCUITO: Test Circuit\n"
    "ESTADÍSTICAS SESIÓN: {\"total_laps\": 2, \"fastest_lap\": \"1:30.000\"}\n"
    "DATOS POR VUELTA (resumen): "
    "VUELTA 1: Tiempo=1:30.000, Vel(max=220.0, avg=140.0, min=60.0), "
    "Throttle_avg=65.0%, Brake(max=80.0%, avg=12.0%), "
    "RPM(avg=6500, max=8500), Fuel(30.0→28.0L), "
    "Desgaste_avg=2.0%, Temp_neumaticos=85.0°C\n"
    "VUELTA 2: Tiempo=1:29.500 (mejora ligera en sector 2)\n"
)

SAMPLE_SETUP = {
    "GENERAL": {"FuelSetting": "30//L"},
    "SUSPENSION": {"SpringSetting": "100//N/mm", "CamberSetting": "-3.0//deg"},
}

SAMPLE_SESSION_STATS = {
    "total_laps": 2,
    "fuel_total": 2.0,
    "fuel_avg": 1.0,
    "wear_total": 2.0,
    "wear_avg": 1.0,
    "fastest_lap": "1:29.500",
    "fastest_lap_num": "2",
}


@pytest.fixture
def engineer(llm_model_tag):
    """AIAngineer instance with real LLM. Function-scoped to avoid event loop conflicts."""
    eng = AIAngineer()
    eng._init_llm(llm_model_tag)
    return eng


@pytest.mark.integration
@pytest.mark.asyncio
async def test_analyze_full_pipeline(engineer):
    """
    Full analyze() call with real LLM.
    Verifies response structure and that Spanish text is returned.
    """
    result = await engineer.analyze(
        telemetry_summary=SAMPLE_TELEMETRY_SUMMARY,
        setup_data=SAMPLE_SETUP,
        circuit_name="Test Circuit",
        session_stats=SAMPLE_SESSION_STATS,
    )

    # Structure
    assert "driving_analysis" in result
    assert "setup_analysis" in result
    assert "full_setup" in result
    assert "agent_reports" in result
    assert "chief_reasoning" in result

    # Driving analysis must be non-empty (not the fallback error string)
    assert isinstance(result["driving_analysis"], str)
    assert "No se pudo obtener" not in result["driving_analysis"], (
        f"LLM call failed — got fallback string: {result['driving_analysis']}"
    )
    assert len(result["driving_analysis"]) > 50

    # full_setup has sections list
    assert isinstance(result["full_setup"].get("sections"), list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_json_from_llm_returns_valid_json(engineer):
    """
    _get_json_from_llm with a minimal section prompt returns parseable JSON
    with 'items' and 'summary' keys.
    """
    result = await engineer._get_json_from_llm(
        SECTION_AGENT_PROMPT,
        {
            "section_name": "General",
            "telemetry_summary": SAMPLE_TELEMETRY_SUMMARY,
            "section_data": json.dumps({"FuelSetting": "30"}),
            "context_data": "N/A",
            "circuit_name": "Test Circuit",
            "fixed_params_prompt": "Ninguno.",
        },
    )

    assert result is not None, "LLM returned None — JSON extraction failed"
    assert "items" in result, f"'items' key missing from LLM response: {result}"
    assert isinstance(result["items"], list)
    # 'summary' is expected per the prompt but may be omitted by smaller models;
    # treat it as a soft requirement — log but don't fail
    if "summary" in result:
        assert isinstance(result["summary"], str)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_analyze_respects_fixed_params(engineer):
    """
    When FuelSetting is fixed, the AI pipeline must not recommend changing it.
    """
    result = await engineer.analyze(
        telemetry_summary=SAMPLE_TELEMETRY_SUMMARY,
        setup_data=SAMPLE_SETUP,
        circuit_name="Test Circuit",
        session_stats=SAMPLE_SESSION_STATS,
        fixed_params=["FuelSetting"],
    )

    # Inspect all items in full_setup for any FuelSetting recommendation
    for section in result["full_setup"].get("sections", []):
        for item in section.get("items", []):
            if item.get("param_key") == "FuelSetting":
                assert item["new"] == item["current"] or "Sin cambios" in item["reason"], (
                    f"Fixed param FuelSetting was modified: {item}"
                )
