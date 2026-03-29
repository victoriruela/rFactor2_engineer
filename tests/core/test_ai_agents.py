"""Unit tests for app/core/ai_agents.py"""
import json
import logging
from pathlib import Path
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
# Jimmy provider internals
# ---------------------------------------------------------------------------

class TestJimmyProvider:
    def test_call_jimmy_api_removes_stats_block_and_outer_quotes(self, ai, mocker):
        mock_response = MagicMock()
        mock_response.text = '"<|stats|>{\"tokens\":42}<|/stats|>Respuesta limpia"'
        mock_response.raise_for_status = MagicMock()
        mock_post = mocker.patch("app.core.ai_agents.requests.post", return_value=mock_response)

        out = ai._call_jimmy_api("prompt test")

        assert out == "Respuesta limpia"
        assert mock_post.called

    @pytest.mark.asyncio
    async def test_call_llm_text_routes_to_jimmy_when_provider_is_jimmy(self, ai, mocker):
        ai._provider = "jimmy"
        mocker.patch.object(ai, "_build_prompt_text", return_value="PROMPT")
        mocker.patch.object(ai, "_call_jimmy_api", return_value="Jimmy OK")

        out = await ai._call_llm_text("X {y}", {"y": 1})

        assert out == "Jimmy OK"


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

    def test_no_reco_returns_empty_sections(self, ai):
        result = ai._format_full_setup({}, self.SETUP)
        # With no recommendations, all items have current==new, so sections are skipped
        assert result["sections"] == []

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
        reco_map = {"GENERAL": {"FuelSetting": {"new_value": "45", "reason": "Reducir peso."}}}
        result = ai._format_full_setup(reco_map, setup_with_gear)
        section = result["sections"][0]
        param_keys = [i["param_key"] for i in section["items"]]
        assert "GearXSetting" not in param_keys
        assert "FuelSetting" in param_keys


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
        assert "setup_agent_reports" in result
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


# ---------------------------------------------------------------------------
# Jimmy/T6 regression coverage: failure handling and fallback policy contract
# ---------------------------------------------------------------------------

class TestJimmyFallbackPolicyArtifact:
    def test_runtime_config_declares_retry_and_degraded_signal_contract(self):
        config_path = Path(__file__).resolve().parents[2] / "app" / "core" / "jimmy_runtime_config.v1.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        fallback = config["fallbackPolicy"]
        assert fallback["maxRetriesPerStage"] >= 1
        assert "chief_none" in fallback["retryOnFailureConditions"]
        assert "specialist_invalid_json_or_missing_items" in fallback["retryOnFailureConditions"]
        assert "driving_analysis_empty_or_too_short" in fallback["retryOnFailureConditions"]
        assert fallback["failureSignal"]["degraded"] is True
        assert fallback["failureSignal"]["reasonField"] == "fallback_reason"


class TestAnalyzeJimmyFailureShapes:
    SETUP = {
        "GENERAL": {"FuelSetting": "50//L"},
        "SUSPENSION": {"SpringSetting": "100//N/mm"},
    }

    @pytest.mark.asyncio
    async def test_chief_none_falls_back_to_specialists_without_crash(self, ai, mocker):
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(return_value="Conduccion OK"))

        specialist_report = {
            "items": [
                {
                    "parameter": "SpringSetting",
                    "new_value": "110",
                    "reason": "Ajuste de prueba para fallback.",
                }
            ],
            "summary": "Especialista con recomendacion.",
        }
        mocker.patch.object(
            ai,
            "_get_json_from_llm",
            new=AsyncMock(side_effect=[specialist_report, specialist_report, None]),
        )

        result = await ai.analyze(
            telemetry_summary="telemetry",
            setup_data=self.SETUP,
            provider="jimmy",
        )

        assert result["driving_analysis"] == "Conduccion OK"
        assert "Consolidacion del Ingeniero Jefe" in result["chief_reasoning"]
        assert len(result["agent_reports"]) == 2
        assert "summary" in result["agent_reports"][0]

        sections = {s["section_key"]: s for s in result["full_setup"]["sections"]}
        suspension_item = next(i for i in sections["SUSPENSION"]["items"] if i["param_key"] == "SpringSetting")
        assert suspension_item["new"].startswith("110")

    @pytest.mark.asyncio
    async def test_chief_asymmetry_is_harmonized_and_setup_reports_match(self, ai, mocker):
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(return_value="Conduccion OK"))

        setup = {
            "FRONTLEFT": {"CamberSetting": "-3.0"},
            "FRONTRIGHT": {"CamberSetting": "-3.0"},
        }
        specialist_empty = {"items": [], "summary": "Sin cambios"}
        chief_report = {
            "full_setup": {
                "sections": [
                    {
                        "name": "FRONTLEFT",
                        "items": [
                            {
                                "parameter": "CamberSetting",
                                "new_value": "-3.2",
                                "reason": "Ajuste lado izquierdo.",
                            }
                        ],
                    },
                    {
                        "name": "FRONTRIGHT",
                        "items": [
                            {
                                "parameter": "CamberSetting",
                                "new_value": "-3.6",
                                "reason": "Ajuste lado derecho.",
                            }
                        ],
                    },
                ]
            },
            "chief_reasoning": "Consolidación por simetría.",
        }

        mocker.patch.object(
            ai,
            "_get_json_from_llm",
            new=AsyncMock(side_effect=[specialist_empty, specialist_empty, chief_report]),
        )

        result = await ai.analyze(
            telemetry_summary="telemetry",
            setup_data=setup,
            provider="ollama",
        )

        sections = {s["section_key"]: s for s in result["full_setup"]["sections"]}
        fl = next(i for i in sections["FRONTLEFT"]["items"] if i["param_key"] == "CamberSetting")
        fr = next(i for i in sections["FRONTRIGHT"]["items"] if i["param_key"] == "CamberSetting")
        assert fl["new"].startswith("-3.2")
        assert fr["new"].startswith("-3.2")

        setup_reports = {r["name"]: r for r in result["setup_agent_reports"]}
        fl_report = setup_reports["FRONTLEFT"]["items"][0]
        fr_report = setup_reports["FRONTRIGHT"]["items"][0]
        assert fl_report["new_value"] == "-3.2"
        assert fr_report["new_value"] == "-3.2"

    @pytest.mark.asyncio
    async def test_internal_placeholder_reason_is_sanitized_to_specialist_reason(self, ai, mocker):
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(return_value="Conduccion OK"))

        specialist_report = {
            "items": [
                {
                    "parameter": "SpringSetting",
                    "new_value": "110",
                    "reason": "El muelle actual se comprime demasiado en apoyo y pierde estabilidad de plataforma.",
                }
            ],
            "summary": "Se ajusta muelle para mejorar apoyo.",
        }
        chief_report = {
            "full_setup": {
                "sections": [
                    {
                        "name": "SUSPENSION",
                        "items": [
                            {
                                "parameter": "SpringSetting",
                                "new_value": "110",
                                "reason": "COPIA AQUI LA RAZON INTEGRA DEL ESPECIALISTA SI ACEPTAS SIN CAMBIOS...",
                            }
                        ],
                    }
                ]
            },
            "chief_reasoning": "OBLIGATORIO: Valoracion global...",
        }

        mocker.patch.object(
            ai,
            "_get_json_from_llm",
            new=AsyncMock(side_effect=[specialist_report, specialist_report, chief_report]),
        )

        result = await ai.analyze(
            telemetry_summary="telemetry",
            setup_data=self.SETUP,
            provider="jimmy",
        )

        sections = {s["section_key"]: s for s in result["full_setup"]["sections"]}
        suspension_item = next(i for i in sections["SUSPENSION"]["items"] if i["param_key"] == "SpringSetting")
        assert "COPIA AQUI" not in suspension_item["reason"]
        assert "muelle actual" in suspension_item["reason"].lower()

        reports = {r["name"]: r for r in result["setup_agent_reports"]}
        report_reason = reports["SUSPENSION"]["items"][0]["reason"]
        assert "COPIA AQUI" not in report_reason
        assert "muelle actual" in report_reason.lower()
        assert "OBLIGATORIO:" not in result["chief_reasoning"]

    @pytest.mark.asyncio
    async def test_partial_chief_output_preserves_specialist_changes(self, ai, mocker):
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(return_value="Conduccion OK"))

        specialist_report = {
            "items": [
                {
                    "parameter": "SpringSetting",
                    "new_value": "110",
                    "reason": "Muelle demasiado blando en apoyo medio.",
                }
            ],
            "summary": "Cambio en muelle.",
        }
        chief_report = {
            "full_setup": {"sections": []},
            "chief_reasoning": "Analisis global sin nuevos cambios.",
        }

        mocker.patch.object(
            ai,
            "_get_json_from_llm",
            new=AsyncMock(side_effect=[specialist_report, specialist_report, chief_report]),
        )

        result = await ai.analyze(
            telemetry_summary="telemetry",
            setup_data=self.SETUP,
            provider="jimmy",
        )

        sections = {s["section_key"]: s for s in result["full_setup"]["sections"]}
        suspension_item = next(i for i in sections["SUSPENSION"]["items"] if i["param_key"] == "SpringSetting")
        assert suspension_item["new"].startswith("110")
        assert result.get("fallback_reason") == "chief_no_items"

    @pytest.mark.asyncio
    async def test_invalid_specialist_reports_are_ignored_without_crashing(self, ai, mocker):
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(return_value="Conduccion OK"))

        chief_report = {
            "full_setup": {"sections": []},
            "chief_reasoning": "Fallback controlado por JSON invalido de especialistas.",
        }
        mocker.patch.object(
            ai,
            "_get_json_from_llm",
            new=AsyncMock(side_effect=[None, {"items": "no_es_lista"}, chief_report]),
        )

        result = await ai.analyze(
            telemetry_summary="telemetry",
            setup_data=self.SETUP,
            provider="jimmy",
        )

        assert result["driving_analysis"] == "Conduccion OK"
        assert len(result["agent_reports"]) == 1
        report = result["agent_reports"][0]
        assert report["name"] == "SUSPENSION"
        assert report["items"] == []
        assert report["summary"] == ""
        assert "friendly_name" in report  # now always present
        assert "Fallback controlado" in result["chief_reasoning"]
        assert isinstance(result["full_setup"]["sections"], list)

    @pytest.mark.asyncio
    async def test_specialist_report_normalization_accepts_alt_keys(self, ai, mocker):
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(return_value="Conduccion OK"))

        specialist_report_alt = {
            "recomendaciones": [
                {
                    "parametro": "SpringSetting",
                    "nuevo_valor": "112",
                    "motivo": "Mejor apoyo en salida.",
                }
            ],
            "resumen": "Se propone endurecer un punto el muelle.",
        }
        mocker.patch.object(
            ai,
            "_get_json_from_llm",
            new=AsyncMock(side_effect=[specialist_report_alt, specialist_report_alt, None]),
        )

        result = await ai.analyze(
            telemetry_summary="telemetry",
            setup_data=self.SETUP,
            provider="jimmy",
        )

        assert len(result["agent_reports"]) == 2
        first_report = result["agent_reports"][0]
        assert first_report["summary"]
        assert first_report["items"][0]["parameter"] == "SpringSetting"
        assert first_report["items"][0]["new_value"] == "112"

    @pytest.mark.asyncio
    async def test_driving_analysis_exception_returns_controlled_message(self, ai, mocker):
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(side_effect=RuntimeError("jimmy down")))
        mocker.patch.object(
            ai,
            "_get_json_from_llm",
            new=AsyncMock(return_value={"full_setup": {"sections": []}, "chief_reasoning": "ok"}),
        )

        result = await ai.analyze(
            telemetry_summary="telemetry",
            setup_data=self.SETUP,
            provider="jimmy",
        )

        assert result["driving_analysis"] == "No se pudo obtener el análisis de conducción."
        assert "full_setup" in result

    @pytest.mark.asyncio
    async def test_logs_diagnostic_context_for_chief_none_without_specialist_reasoning(self, ai, mocker, caplog):
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(return_value="Conduccion OK"))

        specialist_without_reason = {
            "items": [{"parameter": "SpringSetting", "new_value": "110", "reason": ""}],
            "summary": "sin razonamiento",
        }
        mocker.patch.object(
            ai,
            "_get_json_from_llm",
            new=AsyncMock(side_effect=[specialist_without_reason, specialist_without_reason, None]),
        )

        with caplog.at_level(logging.INFO, logger="app.core.ai_agents"):
            result = await ai.analyze(
                telemetry_summary="telemetry",
                setup_data=self.SETUP,
                provider="jimmy",
            )

        assert result.get("degraded") is True
        # When chief returns None, the secondary fallback fires with reason "chief_no_items"
        assert result.get("fallback_reason") == "chief_no_items"
        assert "event=analysis_completed" in caplog.text
        assert 'fallback_reason="chief_no_items"' in caplog.text
        assert "specialist_reasons=0" in caplog.text
        assert "chief_present=false" in caplog.text

    @pytest.mark.asyncio
    async def test_jimmy_provider_truncates_telemetry_for_specialists(self, ai, mocker):
        """Jimmy's 8K context can't handle large telemetry — verify it gets truncated."""
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(return_value="Conduccion OK"))

        captured_inputs = []

        async def capturing_get_json(prompt, inputs, **kwargs):
            captured_inputs.append(inputs.copy())
            return None

        mocker.patch.object(ai, "_get_json_from_llm", new=AsyncMock(side_effect=capturing_get_json))

        big_telemetry = "x" * 10_000
        await ai.analyze(
            telemetry_summary=big_telemetry,
            setup_data=self.SETUP,
            provider="jimmy",
        )

        from app.core.ai_agents import JIMMY_MAX_TELEMETRY_CHARS
        specialist_calls = [c for c in captured_inputs if "section_name" in c]
        for call in specialist_calls:
            assert len(call["telemetry_summary"]) <= JIMMY_MAX_TELEMETRY_CHARS + 100

    @pytest.mark.asyncio
    async def test_fallback_resolves_friendly_param_names_to_internal(self, ai, mocker):
        """Specialist reports using friendly param names must map to internal names in setup."""
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(return_value="Conduccion OK"))

        # Set up a friendly→internal mapping
        ai.mapping["parameters"]["SpringSetting"] = "Muelle (Spring)"

        specialist_report = {
            "items": [
                {"parameter": "Muelle (Spring)", "new_value": "115", "reason": "Ajuste."}
            ],
            "summary": "Cambio de muelle.",
        }
        mocker.patch.object(
            ai,
            "_get_json_from_llm",
            new=AsyncMock(side_effect=[specialist_report, specialist_report, None]),
        )

        result = await ai.analyze(
            telemetry_summary="telemetry",
            setup_data=self.SETUP,
            provider="jimmy",
        )

        sections = {s["section_key"]: s for s in result["full_setup"]["sections"]}
        suspension_items = sections["SUSPENSION"]["items"]
        spring_item = next(i for i in suspension_items if i["param_key"] == "SpringSetting")
        assert spring_item["new"].startswith("115")

    @pytest.mark.asyncio
    async def test_chief_item_alt_keys_are_applied_to_setup(self, ai, mocker):
        mocker.patch.object(ai, "update_mappings", new=AsyncMock())
        mocker.patch.object(ai, "_call_llm_text", new=AsyncMock(return_value="Conduccion OK"))

        specialist_report = {"items": [], "summary": "sin cambios especialistas"}
        chief_report_alt_keys = {
            "full_setup": {
                "sections": [
                    {
                        "name": "SUSPENSION",
                        "items": [
                            {
                                "parametro": "SpringSetting",
                                "newValue": "112",
                                "motivo": "Compensar falta de soporte en apoyo medio.",
                            }
                        ],
                    }
                ]
            },
            "chief_reasoning": "Aplicando ajuste de muelle por balance global.",
        }

        mocker.patch.object(
            ai,
            "_get_json_from_llm",
            new=AsyncMock(side_effect=[specialist_report, specialist_report, chief_report_alt_keys]),
        )

        result = await ai.analyze(
            telemetry_summary="telemetry",
            setup_data=self.SETUP,
            provider="jimmy",
        )

        sections = {s["section_key"]: s for s in result["full_setup"]["sections"]}
        suspension_item = next(i for i in sections["SUSPENSION"]["items"] if i["param_key"] == "SpringSetting")
        assert suspension_item["new"].startswith("112")
        assert "soporte" in suspension_item["reason"].lower()

