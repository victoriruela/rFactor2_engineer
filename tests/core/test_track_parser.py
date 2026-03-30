"""Unit tests for AIW track parser — written BEFORE implementation (TDD)."""

import os
import pytest

from app.core.track_parser import parse_aiw

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
SAMPLE_AIW = os.path.join(FIXTURES_DIR, "sample.aiw")


@pytest.fixture
def sample_content():
    with open(SAMPLE_AIW, "r") as f:
        return f.read()


# ---------- parse_aiw basic contract ----------


def test_parse_aiw_returns_dict(sample_content):
    result = parse_aiw(sample_content)
    assert isinstance(result, dict)


def test_parse_aiw_has_required_keys(sample_content):
    result = parse_aiw(sample_content)
    assert "name" in result
    assert "source" in result
    assert "points" in result


def test_parse_aiw_source_is_aiw(sample_content):
    result = parse_aiw(sample_content)
    assert result["source"] == "aiw"


def test_parse_aiw_default_track_name(sample_content):
    result = parse_aiw(sample_content)
    assert result["name"] == "Unknown"


def test_parse_aiw_custom_track_name(sample_content):
    result = parse_aiw(sample_content, track_name="Spa")
    assert result["name"] == "Spa"


# ---------- waypoint extraction ----------


def test_parse_aiw_extracts_all_waypoints(sample_content):
    result = parse_aiw(sample_content)
    assert len(result["points"]) == 7


def test_parse_aiw_point_has_required_fields(sample_content):
    result = parse_aiw(sample_content)
    point = result["points"][0]
    for key in ("x", "y", "z", "width_left", "width_right"):
        assert key in point, f"Missing key: {key}"


# ---------- coordinate mapping ----------
# AIW: X=east, Y=up, Z=south
# Output: x=AIW_X, y=AIW_Z, z=AIW_Y (elevation)


def test_parse_aiw_coordinate_mapping_first_point(sample_content):
    """First waypoint: wp_pos=(100.5, 25.3, 200.7)
    Expected: x=100.5, y=200.7, z=25.3
    """
    result = parse_aiw(sample_content)
    p = result["points"][0]
    assert p["x"] == pytest.approx(100.5)
    assert p["y"] == pytest.approx(200.7)
    assert p["z"] == pytest.approx(25.3)


def test_parse_aiw_negative_coordinates(sample_content):
    """Sixth waypoint: wp_pos=(-150.0, 23.9, -250.8)
    Expected: x=-150.0, y=-250.8, z=23.9
    """
    result = parse_aiw(sample_content)
    p = result["points"][5]
    assert p["x"] == pytest.approx(-150.0)
    assert p["y"] == pytest.approx(-250.8)
    assert p["z"] == pytest.approx(23.9)


# ---------- width extraction ----------


def test_parse_aiw_width_first_point(sample_content):
    """First waypoint: wp_width=(5.0, 5.0, 8.0, 8.0)
    width_left = first value, width_right = second value.
    """
    result = parse_aiw(sample_content)
    p = result["points"][0]
    assert p["width_left"] == pytest.approx(5.0)
    assert p["width_right"] == pytest.approx(5.0)


def test_parse_aiw_width_third_point(sample_content):
    """Third waypoint: wp_width=(6.0, 5.5, 9.0, 8.5)"""
    result = parse_aiw(sample_content)
    p = result["points"][2]
    assert p["width_left"] == pytest.approx(6.0)
    assert p["width_right"] == pytest.approx(5.5)


# ---------- edge cases ----------


def test_parse_aiw_empty_string():
    result = parse_aiw("")
    assert result["points"] == []


def test_parse_aiw_no_waypoints():
    result = parse_aiw("[Header]\nsome_key=some_value\n")
    assert result["points"] == []


def test_parse_aiw_mismatched_pos_width():
    """If there are more wp_pos than wp_width, widths default to 0."""
    content = "[Waypoint]\nwp_pos=(1.0, 2.0, 3.0)\n"
    result = parse_aiw(content)
    assert len(result["points"]) == 1
    p = result["points"][0]
    assert p["width_left"] == pytest.approx(0.0)
    assert p["width_right"] == pytest.approx(0.0)


def test_parse_aiw_values_are_floats(sample_content):
    result = parse_aiw(sample_content)
    for p in result["points"]:
        assert isinstance(p["x"], float)
        assert isinstance(p["y"], float)
        assert isinstance(p["z"], float)
        assert isinstance(p["width_left"], float)
        assert isinstance(p["width_right"], float)
