"""Unit tests for app/core/ai_agents.py"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.ai_agents import (
    AIAngineer,
    _compute_change_pct,
    _extract_numeric,
)


# ---------------------------------------------------------------------------
# Pure-function tests (no LLM, no Ollama)
# ---------------------------------------------------------------------------

class TestExtractNumeric:
    def test_simple_integer(self):
        assert _extract_numeric("223 N/mm") == 223.0

    def test_float(self):
        assert _extract_numeric("3.14 bar") == 3.14

    def test_negative(self):
        assert _extract_numeric("-3.2 °") == -3.2

    def test_no_numeric(self):
        assert _extract_numeric("abc") is None

    def test_empty_string(self):
        assert _extract_numeric("") is None

    def test_pure_number(self):
        assert _extract_numeric("42") == 42.0


class TestComputeChangePct:
    def test_increase(self):
        result = _compute_change_pct("100", "112.5")
        assert result == "(+12.5%)"

    def test_decrease(self):
        result = _compute_change_pct("100", "90")
        assert result == "(-10.0%)"

    def test_no_change_returns_none(self):
        assert _compute_change_pct("100", "100") is None

    def test_zero_base_returns_nuevo(self):
        assert _compute_change_pct("0", "5") == "(nuevo)"

    def test_zero_to_zero_returns_none(self):
        assert _compute_change_pct("0", "0") is None

    def test_non_numeric_returns_none(self):
        assert _compute_change_pct("abc", "100") is None

    def test_values_with_units(self):
        # Should extract numeric part from both sides
        result = _compute_change_pct("100 N/mm", "110 N/mm")
        assert result == "(+10.0%)"


# ---------------------------------------------------------------------------
# AIAngineer fixtures — patches Ollama to avoid real connections
# ---------------------------------------------------------------------------

@pytest.fixture
def ai(mocker, tmp_path):
    """AIAngineer instance with mocked Ollama and mapping file in tmp_path."""
    mocker.patch("app.core.ai_agents._ensure_ollama_running", return_value=True)
    mocker.patch("app.core.ai_agents.ChatOllama")
    # Point mapping_path to a non-existent file in tmp_path so tests are isolated
    engineer = AIAngineer()
    engineer.mapping_path = str(tmp_path / "param_mapping.json")
    engineer.mapping = {"sections": {}, "parameters": {}}
    return engineer


@pytest.fixture
def ai_with_mapping(mocker, tmp_path):
    """AIAngineer with a pre-loaded mapping file."""
    mocker.patch("app.core.ai_agents._ensure_ollama_running", return_value=True)
    mocker.patch("app.core.ai_agents.ChatOllama")
    mapping = {
        "sections": {"FRONTLEFT": "Neumático Delantero Izquierdo"},
        "parameters": {"CamberSetting": "Caída (Camber)"},
    }
    mapping_file = tmp_path / "param_mapping.json"
    mapping_file.write_text(json.dumps(mapping), encoding="utf-8")
    engineer = AIAngineer()
    engineer.mapping_path = str(mapping_file)
    engineer.mapping = mapping
    return engineer


# ---------------------------------------------------------------------------
# Instance initialisation tests
# ---------------------------------------------------------------------------

class TestAIAngineersInit:
    def test_empty_mapping_when_file_missing(self, mocker, tmp_path):
        mocker.patch("app.core.ai_agents._ensure_ollama_running", return_value=True)
        mocker.patch("app.core.ai_agents.ChatOllama")
        eng = AIAngineer()
        eng.mapping_path = str(tmp_path / "nonexistent.json")
        eng.mapping = eng._load_mapping()
        assert eng.mapping == {"sections": {}, "parameters": {}}

    def test_loads_mapping_from_file(self, mocker, tmp_path):
        mocker.patch("app.core.ai_agents._ensure_ollama_running", return_value=True)
        mocker.patch("app.core.ai_agents.ChatOllama")
        mapping = {"sections": {"X": "Y"}, "parameters": {"A": "B"}}
        f = tmp_path / "param_mapping.json"
        f.write_text(json.dumps(mapping), encoding="utf-8")
        eng = AIAngineer()
        eng.mapping_path = str(f)
        loaded = eng._load_mapping()
        assert loaded == mapping


# ---------------------------------------------------------------------------
# _clean_value
# ---------------------------------------------------------------------------

class TestCleanValue:
    def test_strips_inline_comment(self, ai):
        assert ai._clean_value("223//N/mm") == "N/mm"

    def test_no_comment(self, ai):
        assert ai._clean_value("100") == "100"

    def test_multiple_slashes_splits_on_first(self, ai):
        # "a//b//c" → "b//c" (only first split)
        assert ai._clean_value("a//b//c") == "b//c"


# ---------------------------------------------------------------------------
# _get_friendly_name
# ---------------------------------------------------------------------------

class TestGetFriendlyName:
    def test_found_parameter(self, ai_with_mapping):
        assert ai_with_mapping._get_friendly_name("CamberSetting") == "Caída (Camber)"

    def test_not_found_falls_back_to_key(self, ai_with_mapping):
        assert ai_with_mapping._get_friendly_name("UnknownParam") == "UnknownParam"

    def test_found_section(self, ai_with_mapping):
        assert ai_with_mapping._get_friendly_name("FRONTLEFT", "section") == "Neumático Delantero Izquierdo"


# ---------------------------------------------------------------------------
# _build_current_setup_summary
# ---------------------------------------------------------------------------

class TestBuildCurrentSetupSummary:
    SETUP = {
        "GENERAL": {"FuelSetting": "50//L"},
        "SUSPENSION": {"SpringSetting": "100//N/mm", "Gear1Setting": "1"},
        "BASIC": {"SomeParam": "ignored"},
        "LEFTFENDER": {"FenderParam": "ignored"},
        "RIGHTFENDER": {"FenderParam": "ignored"},
    }

    def test_skips_basic_and_fenders(self, ai):
        summary = ai._build_current_setup_summary(self.SETUP)
        assert "BASIC" not in summary
        assert "LEFTFENDER" not in summary
        assert "RIGHTFENDER" not in summary

    def test_includes_normal_sections(self, ai):
        summary = ai._build_current_setup_summary(self.SETUP)
        assert "GENERAL" in summary
        assert "SUSPENSION" in summary

    def test_skips_gear_settings(self, ai):
        summary = ai._build_current_setup_summary(self.SETUP)
        assert "Gear1Setting" not in summary

    def test_includes_non_gear_params(self, ai):
        summary = ai._build_current_setup_summary(self.SETUP)
        assert "SpringSetting" in summary


# ---------------------------------------------------------------------------
# _format_full_setup
# ---------------------------------------------------------------------------

class TestFormatFullSetup:
    SETUP = {
        "GENERAL": {"FuelSetting": "50//L"},
        "SUSPENSION": {"SpringSetting": "100//N/mm"},
    }

    def test_no_reco_returns_current_and_no_change_reason(self, ai):
        result = ai._format_full_setup({}, self.SETUP)
        sections = {s["section_key"]: s for s in result["sections"]}
        item = sections["GENERAL"]["items"][0]
        assert item["current"] == "L"
        assert item["new"] == "L"
        assert "Sin cambios" in item["reason"]

    def test_reco_applied_with_change_pct(self, ai):
        # Recommendations carry clean numeric values (no // comment syntax)
        reco_map = {
            "SUSPENSION": {
                "SpringSetting": {"new_value": "110", "reason": "Needs stiffer spring."}
            }
        }
        # Current value "100//N/mm" is _clean_value'd to "N/mm" by the formatter,
        # and recommendation "110" stays "110"; change pct computed from numeric parts.
        result = ai._format_full_setup(reco_map, self.SETUP)
        sections = {s["section_key"]: s for s in result["sections"]}
        item = next(i for i in sections["SUSPENSION"]["items"] if i["param_key"] == "SpringSetting")
        assert "110" in item["new"]
        assert "stiffer" in item["reason"]

    def test_skips_gear_settings(self, ai):
        setup_with_gear = {"GENERAL": {"GearXSetting": "1", "FuelSetting": "50//L"}}
        result = ai._format_full_setup({}, setup_with_gear)
        section = result["sections"][0]
        param_keys = [i["param_key"] for i in section["items"]]
        assert "GearXSetting" not in param_keys


# ---------------------------------------------------------------------------
# analyze() — async, full pipeline mocked
# ---------------------------------------------------------------------------

class TestAnalyze:
    SETUP = {
        "GENERAL": {"FuelSetting": "50//L"},
        "SUSPENSION": {"SpringSetting": "100//N/mm"},
    }

    @pytest.mark.asyncio
    async def test_returns_expected_keys(self, ai, mocker):
        # Patch update_mappings to be a no-op
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())

        # Patch the driving chain call
        mock_chain_result = "Análisis de conducción simulado."
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_chain_result)
        mocker.patch("app.core.ai_agents.PromptTemplate.from_template", return_value=MagicMock())
        mocker.patch.object(
            ai, "_get_json_from_llm",
            new=AsyncMock(return_value={
                "items": [],
                "summary": "Sin cambios.",
                "full_setup": {"sections": []},
                "chief_reasoning": "Todo bien.",
            })
        )

        # Simulate LLM chain for driving analysis
        mock_llm = MagicMock()
        mock_llm.__or__ = MagicMock(return_value=mock_chain)
        ai.llm = mock_llm

        # Patch PromptTemplate | llm | parser chain
        fake_chain = MagicMock()
        fake_chain.ainvoke = AsyncMock(return_value="Análisis conducción.")
        with patch("app.core.ai_agents.PromptTemplate") as mock_pt:
            mock_pt.from_template.return_value.__or__ = MagicMock(return_value=fake_chain)
            result = await ai.analyze(
                telemetry_summary="telemetry data",
                setup_data=self.SETUP,
                circuit_name="Test Circuit",
                session_stats={"total_laps": 3},
            )

        assert "driving_analysis" in result
        assert "setup_analysis" in result
        assert "full_setup" in result
        assert "agent_reports" in result
        assert "chief_reasoning" in result

    @pytest.mark.asyncio
    async def test_accepts_driving_telemetry_summary_kwarg(self, ai, mocker):
        """analyze() must accept driving_telemetry_summary without raising."""
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_get_json_from_llm", new=AsyncMock(return_value={
            "items": [], "summary": ".", "full_setup": {"sections": []}, "chief_reasoning": "."
        }))
        fake_chain = MagicMock()
        fake_chain.ainvoke = AsyncMock(return_value="Análisis.")
        with patch("app.core.ai_agents.PromptTemplate") as mock_pt:
            mock_pt.from_template.return_value.__or__ = MagicMock(return_value=fake_chain)
            result = await ai.analyze(
                telemetry_summary="FULL telemetry",
                setup_data=self.SETUP,
                driving_telemetry_summary="DRIVING ONLY telemetry",
            )
        assert "driving_analysis" in result


# ---------------------------------------------------------------------------
# TestAnalyzeDrivingTelemetryFilter — driving_telemetry_summary routing
# ---------------------------------------------------------------------------

class TestAnalyzeDrivingTelemetryFilter:
    """Verify that driving_telemetry_summary overrides the full summary for the driving agent."""

    SETUP = {"GENERAL": {"FuelSetting": "50//L"}}

    def _make_capturing_chain(self, captured: dict):
        """Return a fake LangChain chain that captures ainvoke inputs."""
        async def capture_invoke(inputs):
            captured.update(inputs)
            return "Análisis."

        fake_chain = MagicMock()
        fake_chain.ainvoke = AsyncMock(side_effect=capture_invoke)
        # prompt | llm | parser: each | step must keep returning fake_chain
        fake_chain.__or__ = MagicMock(return_value=fake_chain)
        return fake_chain

    @pytest.mark.asyncio
    async def test_driving_summary_sent_to_driving_prompt(self, ai, mocker):
        """When driving_telemetry_summary is provided, it is used in the DRIVING_PROMPT invocation."""
        captured = {}
        fake_chain = self._make_capturing_chain(captured)

        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_get_json_from_llm", new=AsyncMock(return_value={
            "items": [], "summary": ".", "full_setup": {"sections": []}, "chief_reasoning": "."
        }))

        with patch("app.core.ai_agents.PromptTemplate") as mock_pt:
            mock_pt.from_template.return_value.__or__ = MagicMock(return_value=fake_chain)
            await ai.analyze(
                telemetry_summary="FULL telemetry",
                setup_data=self.SETUP,
                driving_telemetry_summary="DRIVING ONLY telemetry",
            )

        assert captured.get("telemetry_summary") == "DRIVING ONLY telemetry"

    @pytest.mark.asyncio
    async def test_full_summary_used_when_driving_summary_is_none(self, ai, mocker):
        """When driving_telemetry_summary is omitted, the full telemetry_summary is used."""
        captured = {}
        fake_chain = self._make_capturing_chain(captured)

        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_get_json_from_llm", new=AsyncMock(return_value={
            "items": [], "summary": ".", "full_setup": {"sections": []}, "chief_reasoning": "."
        }))

        with patch("app.core.ai_agents.PromptTemplate") as mock_pt:
            mock_pt.from_template.return_value.__or__ = MagicMock(return_value=fake_chain)
            await ai.analyze(
                telemetry_summary="FULL telemetry",
                setup_data=self.SETUP,
                # driving_telemetry_summary NOT passed → defaults to None
            )

        assert captured.get("telemetry_summary") == "FULL telemetry"

