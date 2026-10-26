"""``dashboard_open``: the dashboard chat's agent takes the user to the page that shows its work."""

import json

import pytest

from tools import dashboard_open_tool as dot
from tools import desktop_ui


@pytest.fixture(autouse=True)
def _reset_emitter():
    desktop_ui.set_emitter(None)
    yield
    desktop_ui.set_emitter(None)


def _capture():
    calls = []
    desktop_ui.set_emitter(lambda sid, event, payload: calls.append((event, payload)))
    return calls


def test_page_emits_its_route():
    calls = _capture()

    out = json.loads(dot.dashboard_open_tool(page=" Cron "))

    assert out == {"success": True, "path": "/cron"}
    assert calls == [("dashboard.navigate", {"path": "/cron"})]


def test_skill_opens_its_mini_dashboard():
    calls = _capture()

    out = json.loads(dot.dashboard_open_tool(skill="kronos"))

    assert out["path"] == "/skills/dashboards/kronos"
    assert calls == [("dashboard.navigate", {"path": "/skills/dashboards/kronos"})]


@pytest.mark.parametrize(
    "kwargs",
    [{"page": "nowhere"}, {"page": ""}, {"skill": "../config"}, {"skill": "a/b"}],
)
def test_unknown_targets_emit_nothing(kwargs):
    calls = _capture()

    out = json.loads(dot.dashboard_open_tool(**kwargs))

    assert "error" in out
    assert calls == []


def test_without_a_dashboard_client_it_says_so():
    out = json.loads(dot.dashboard_open_tool(page="cron"))

    assert "web dashboard" in out["error"]


class TestSessionGating:
    def test_dashboard_session_carries_it(self):
        from tui_gateway.agent_factory import _gui_surface_toolsets

        assert {"project", "dashboard_ui"} <= _gui_surface_toolsets("dashboard")

    @pytest.mark.parametrize("platform", ["desktop", "tui", "telegram", "cli"])
    def test_other_surfaces_do_not(self, platform):
        from toolsets import session_disabled_toolsets
        from tui_gateway.agent_factory import _gui_surface_toolsets

        assert "dashboard_ui" not in _gui_surface_toolsets(platform)
        assert "dashboard_ui" in session_disabled_toolsets(None, platform)

    def test_desktop_keeps_its_own_surface(self):
        from tui_gateway.agent_factory import _gui_surface_toolsets

        assert _gui_surface_toolsets("desktop") == {"project", "desktop_ui", "catalog"}

    def test_dashboard_tool_list_has_it_and_no_desktop_panes(self):
        from model_tools import get_tool_definitions
        from toolsets import session_disabled_toolsets

        names = {
            tool["function"]["name"]
            for tool in get_tool_definitions(
                enabled_toolsets=["dashboard_ui", "desktop_ui"],
                disabled_toolsets=session_disabled_toolsets(None, "dashboard"),
                quiet_mode=True,
                skip_tool_search_assembly=True,
            )
        }

        assert "dashboard_open" in names


def test_dashboard_prompt_teaches_the_tool_it_carries():
    from agent.system_prompt import _default_platform_hint
    from toolsets import TOOLSETS

    hint = _default_platform_hint("dashboard")

    assert "dashboard_open" in hint
    assert "dashboard_open" in TOOLSETS["dashboard_ui"]["tools"]
