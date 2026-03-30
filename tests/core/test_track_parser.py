"""Tests for the AIW track parser."""

import pytest

from app.core.track_parser import parse_aiw_text


SAMPLE_AIW = """\
[Header]
trackName = Spa-Francorchamps GP
numberOfWaypoints = 3

[Waypoint]
trackType = 0
pos = (123.456, 10.0, -789.012)

[Waypoint]
trackType = 0
pos = (234.567, 11.5, -890.123)

[Waypoint]
trackType = 0
pos = (345.678, 12.0, -901.234)
"""


class TestParseAIWText:
    def test_extracts_track_name(self):
        result = parse_aiw_text(SAMPLE_AIW)
        assert result["track_name"] == "Spa-Francorchamps GP"

    def test_extracts_all_waypoints(self):
        result = parse_aiw_text(SAMPLE_AIW)
        assert result["point_count"] == 3
        assert len(result["points"]) == 3

    def test_waypoint_coordinates(self):
        result = parse_aiw_text(SAMPLE_AIW)
        first = result["points"][0]
        assert first["x"] == pytest.approx(123.456)
        assert first["y"] == pytest.approx(10.0)
        assert first["z"] == pytest.approx(-789.012)

    def test_empty_input_returns_zero_points(self):
        result = parse_aiw_text("")
        assert result["point_count"] == 0
        assert result["points"] == []
        assert result["track_name"] == "Unknown"

    def test_no_track_name_returns_unknown(self):
        aiw = "[Waypoint]\npos = (1.0, 2.0, 3.0)\n"
        result = parse_aiw_text(aiw)
        assert result["track_name"] == "Unknown"
        assert result["point_count"] == 1

    def test_case_insensitive_pos_match(self):
        aiw = "POS = ( 1.0 , 2.0 , 3.0 )\n"
        result = parse_aiw_text(aiw)
        assert result["point_count"] == 1

    def test_negative_coordinates(self):
        aiw = "pos=(-100.5, -200.3, -300.1)\n"
        result = parse_aiw_text(aiw)
        assert result["point_count"] == 1
        pt = result["points"][0]
        assert pt["x"] == pytest.approx(-100.5)
        assert pt["y"] == pytest.approx(-200.3)
        assert pt["z"] == pytest.approx(-300.1)
