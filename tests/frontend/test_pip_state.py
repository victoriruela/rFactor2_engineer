"""Tests for the PIP (Picture-in-Picture) state management logic."""

import sys
from unittest.mock import MagicMock

# Mock streamlit before importing the module under test
_st_mock = MagicMock()
_st_mock.session_state = {}
_st_mock.file_uploader.return_value = None
_st_mock.sidebar.__enter__ = lambda s: s
_st_mock.sidebar.__exit__ = lambda *a: False
sys.modules.setdefault("streamlit", _st_mock)
sys.modules.setdefault("streamlit.components", MagicMock())
sys.modules.setdefault("streamlit.components.v1", MagicMock())

from frontend.streamlit_app import (  # noqa: E402
    PIP_DEFAULT_STATE,
    PIP_STATE_FULLSCREEN,
    PIP_STATE_HIDDEN,
    PIP_STATE_MAP_REPLACE,
    PIP_STATE_MINI,
    PIP_VALID_STATES,
    pip_css,
    pip_get_previous_state,
    pip_get_state,
    pip_render_cockpit_container,
    pip_restore_from_fullscreen,
    pip_restore_from_hidden,
    pip_transition,
)


class TestPipGetState:
    def test_default_state_when_empty(self):
        session = {}
        assert pip_get_state(session) == PIP_DEFAULT_STATE

    def test_returns_stored_state(self):
        session = {"pip_state": PIP_STATE_FULLSCREEN}
        assert pip_get_state(session) == PIP_STATE_FULLSCREEN

    def test_invalid_state_returns_default(self):
        session = {"pip_state": "nonexistent"}
        assert pip_get_state(session) == PIP_DEFAULT_STATE

    def test_all_valid_states_recognized(self):
        for state in PIP_VALID_STATES:
            session = {"pip_state": state}
            assert pip_get_state(session) == state


class TestPipGetPreviousState:
    def test_default_previous_when_empty(self):
        session = {}
        assert pip_get_previous_state(session) == PIP_STATE_MINI

    def test_returns_stored_previous(self):
        session = {"pip_previous_state": PIP_STATE_MAP_REPLACE}
        assert pip_get_previous_state(session) == PIP_STATE_MAP_REPLACE

    def test_hidden_previous_falls_back_to_mini(self):
        """Hidden is not a valid 'previous visible' state."""
        session = {"pip_previous_state": PIP_STATE_HIDDEN}
        assert pip_get_previous_state(session) == PIP_STATE_MINI

    def test_invalid_previous_falls_back_to_mini(self):
        session = {"pip_previous_state": "garbage"}
        assert pip_get_previous_state(session) == PIP_STATE_MINI


class TestPipTransition:
    def test_mini_to_hidden(self):
        session = {"pip_state": PIP_STATE_MINI}
        result = pip_transition(session, PIP_STATE_HIDDEN)
        assert result == PIP_STATE_HIDDEN
        assert session["pip_state"] == PIP_STATE_HIDDEN
        assert session["pip_previous_state"] == PIP_STATE_MINI

    def test_mini_to_fullscreen(self):
        session = {"pip_state": PIP_STATE_MINI}
        result = pip_transition(session, PIP_STATE_FULLSCREEN)
        assert result == PIP_STATE_FULLSCREEN
        assert session["pip_previous_state"] == PIP_STATE_MINI

    def test_mini_to_map_replace(self):
        session = {"pip_state": PIP_STATE_MINI}
        result = pip_transition(session, PIP_STATE_MAP_REPLACE)
        assert result == PIP_STATE_MAP_REPLACE
        assert session["pip_previous_state"] == PIP_STATE_MINI

    def test_map_replace_to_hidden_tracks_previous(self):
        session = {"pip_state": PIP_STATE_MAP_REPLACE}
        pip_transition(session, PIP_STATE_HIDDEN)
        assert session["pip_previous_state"] == PIP_STATE_MAP_REPLACE

    def test_hidden_to_fullscreen_does_not_overwrite_previous(self):
        """When transitioning from hidden, the previous visible state
        should NOT be overwritten with 'hidden'."""
        session = {
            "pip_state": PIP_STATE_HIDDEN,
            "pip_previous_state": PIP_STATE_MAP_REPLACE,
        }
        pip_transition(session, PIP_STATE_FULLSCREEN)
        # Previous should still be map_replace, not hidden
        assert session["pip_previous_state"] == PIP_STATE_MAP_REPLACE

    def test_fullscreen_to_mini_does_not_overwrite_previous(self):
        session = {
            "pip_state": PIP_STATE_FULLSCREEN,
            "pip_previous_state": PIP_STATE_MAP_REPLACE,
        }
        pip_transition(session, PIP_STATE_MINI)
        assert session["pip_previous_state"] == PIP_STATE_MAP_REPLACE

    def test_invalid_target_state_is_noop(self):
        session = {"pip_state": PIP_STATE_MINI}
        result = pip_transition(session, "invalid_state")
        assert result == PIP_STATE_MINI
        assert session["pip_state"] == PIP_STATE_MINI

    def test_transition_from_default_empty_session(self):
        session = {}
        result = pip_transition(session, PIP_STATE_FULLSCREEN)
        assert result == PIP_STATE_FULLSCREEN
        assert session["pip_state"] == PIP_STATE_FULLSCREEN
        # Previous should be mini (the default)
        assert session["pip_previous_state"] == PIP_STATE_MINI


class TestPipRestoreFromHidden:
    def test_restore_to_previous_mini(self):
        session = {
            "pip_state": PIP_STATE_HIDDEN,
            "pip_previous_state": PIP_STATE_MINI,
        }
        result = pip_restore_from_hidden(session)
        assert result == PIP_STATE_MINI
        assert session["pip_state"] == PIP_STATE_MINI

    def test_restore_to_previous_map_replace(self):
        session = {
            "pip_state": PIP_STATE_HIDDEN,
            "pip_previous_state": PIP_STATE_MAP_REPLACE,
        }
        result = pip_restore_from_hidden(session)
        assert result == PIP_STATE_MAP_REPLACE

    def test_restore_with_no_previous_defaults_to_mini(self):
        session = {"pip_state": PIP_STATE_HIDDEN}
        result = pip_restore_from_hidden(session)
        assert result == PIP_STATE_MINI


class TestPipRestoreFromFullscreen:
    def test_restore_to_previous_mini(self):
        session = {
            "pip_state": PIP_STATE_FULLSCREEN,
            "pip_previous_state": PIP_STATE_MINI,
        }
        result = pip_restore_from_fullscreen(session)
        assert result == PIP_STATE_MINI

    def test_restore_to_previous_map_replace(self):
        session = {
            "pip_state": PIP_STATE_FULLSCREEN,
            "pip_previous_state": PIP_STATE_MAP_REPLACE,
        }
        result = pip_restore_from_fullscreen(session)
        assert result == PIP_STATE_MAP_REPLACE


class TestPipCss:
    def test_css_contains_all_state_classes(self):
        css = pip_css()
        assert ".pip-mini" in css
        assert ".pip-hidden" in css
        assert ".pip-map-replace" in css
        assert ".pip-fullscreen" in css
        assert ".pip-container" in css

    def test_css_contains_control_buttons(self):
        css = pip_css()
        assert ".pip-controls" in css
        assert ".pip-btn" in css
        assert ".pip-restore-btn" in css

    def test_css_has_transitions(self):
        css = pip_css()
        assert "transition" in css


class TestPipRenderCockpitContainer:
    def test_mini_state_has_controls(self):
        html = pip_render_cockpit_container(PIP_STATE_MINI)
        assert "pip-mini" in html
        assert "pip-controls" in html
        assert "pip_transition" in html

    def test_hidden_state_has_restore_button(self):
        html = pip_render_cockpit_container(PIP_STATE_HIDDEN)
        assert "pip-restore-btn" in html
        assert "restore_hidden" in html

    def test_hidden_state_hides_content(self):
        html = pip_render_cockpit_container(PIP_STATE_HIDDEN)
        assert 'display:none;' in html

    def test_fullscreen_state_has_backdrop(self):
        html = pip_render_cockpit_container(PIP_STATE_FULLSCREEN)
        assert "pip-fullscreen-backdrop" in html
        assert "pip-fullscreen" in html
        assert "restore_fullscreen" in html

    def test_map_replace_state(self):
        html = pip_render_cockpit_container(PIP_STATE_MAP_REPLACE)
        assert "pip-map-replace" in html
        # Should have shrink-to-mini button
        assert "mini" in html

    def test_custom_cockpit_content(self):
        custom = lambda: '<canvas id="cockpit"></canvas>'  # noqa: E731
        html = pip_render_cockpit_container(PIP_STATE_MINI, cockpit_html_func=custom)
        assert '<canvas id="cockpit"></canvas>' in html

    def test_placeholder_when_no_func(self):
        html = pip_render_cockpit_container(PIP_STATE_MINI)
        assert "3D Cockpit (loading...)" in html

    def test_mini_has_all_transition_buttons(self):
        html = pip_render_cockpit_container(PIP_STATE_MINI)
        # Should have: map_replace (up arrow), fullscreen, hidden (minimize)
        assert "map_replace" in html
        assert "fullscreen" in html
        assert "hidden" in html

    def test_map_replace_has_all_transition_buttons(self):
        html = pip_render_cockpit_container(PIP_STATE_MAP_REPLACE)
        assert "mini" in html
        assert "fullscreen" in html
        assert "hidden" in html


class TestPipRoundTrip:
    """Integration-style tests for full state transition sequences."""

    def test_mini_to_hidden_and_restore(self):
        session = {"pip_state": PIP_STATE_MINI}
        pip_transition(session, PIP_STATE_HIDDEN)
        assert pip_get_state(session) == PIP_STATE_HIDDEN
        pip_restore_from_hidden(session)
        assert pip_get_state(session) == PIP_STATE_MINI

    def test_map_replace_to_fullscreen_to_restore(self):
        session = {"pip_state": PIP_STATE_MAP_REPLACE}
        pip_transition(session, PIP_STATE_FULLSCREEN)
        assert pip_get_state(session) == PIP_STATE_FULLSCREEN
        pip_restore_from_fullscreen(session)
        assert pip_get_state(session) == PIP_STATE_MAP_REPLACE

    def test_mini_to_map_to_hidden_to_restore_goes_back_to_map(self):
        session = {"pip_state": PIP_STATE_MINI}
        pip_transition(session, PIP_STATE_MAP_REPLACE)
        pip_transition(session, PIP_STATE_HIDDEN)
        assert pip_get_state(session) == PIP_STATE_HIDDEN
        pip_restore_from_hidden(session)
        assert pip_get_state(session) == PIP_STATE_MAP_REPLACE

    def test_full_cycle(self):
        session = {}
        assert pip_get_state(session) == PIP_STATE_MINI

        pip_transition(session, PIP_STATE_MAP_REPLACE)
        assert pip_get_state(session) == PIP_STATE_MAP_REPLACE

        pip_transition(session, PIP_STATE_FULLSCREEN)
        assert pip_get_state(session) == PIP_STATE_FULLSCREEN

        pip_restore_from_fullscreen(session)
        assert pip_get_state(session) == PIP_STATE_MAP_REPLACE

        pip_transition(session, PIP_STATE_HIDDEN)
        assert pip_get_state(session) == PIP_STATE_HIDDEN

        pip_restore_from_hidden(session)
        assert pip_get_state(session) == PIP_STATE_MAP_REPLACE

        pip_transition(session, PIP_STATE_MINI)
        assert pip_get_state(session) == PIP_STATE_MINI
