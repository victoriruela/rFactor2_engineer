"""Pydantic schemas for API contracts."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel


class UploadInitRequest(BaseModel):
    filename: str


class AnalysisResponse(BaseModel):
    circuit_data: Dict[str, Any]
    issues_on_map: List[Dict[str, Any]]
    driving_analysis: str
    setup_analysis: str
    full_setup: Dict[str, Any]
    session_stats: Dict[str, Any]
    laps_data: List[Dict[str, Any]]
    agent_reports: List[Dict[str, Any]] = []
    setup_agent_reports: List[Dict[str, Any]] = []
    telemetry_summary_sent: str = ""
    chief_reasoning: str = ""
    llm_provider: str = ""
    llm_model: str = ""
