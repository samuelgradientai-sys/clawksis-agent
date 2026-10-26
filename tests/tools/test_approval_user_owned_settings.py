"""Mi Chrome's switches belong to the user, never to the agent.

Contract: ``browser.my_chrome.*`` (the on/off switch and "ask me before paying") is changed by
the user in the dashboard or their own terminal. A terminal command from the agent that would
change it — ``clawk config set/unset``, wrapped or obfuscated, or a request to the dashboard's
settings route — is refused like an ``approvals.deny`` match: under every approval mode and
under yolo, with a message telling the agent not to retry. Reading the config and other settings
are untouched.
"""

from __future__ import annotations

import pytest

from tools import approval as mod
from tools import approval_context, approval_floors

CHANGES = [
    "clawk config set browser.my_chrome.confirm_payments false",
    "clawk config set browser.my_chrome.enabled true",
    "clawk config unset browser.my_chrome.confirm_payments",
    "CLAWK_HOME=/srv/p clawk config set browser.my_chrome.confirm_payments false",
    "bash -lc 'clawk config set browser.my_chrome.confirm_payments false'",
    'clawk config set browser.my_chrome.confirm_pa""yments false',
    "~/.local/bin/clawk config set browser.my_chrome.confirm_payments false",
    "curl -X PUT -d '{\"confirm_payments\":false}' http://127.0.0.1:9119/api/my-chrome/settings",
]


@pytest.fixture
def approvals(monkeypatch):
    for var in (
        "CLAWK_YOLO_MODE",
        "CLAWK_GATEWAY_SESSION",
        "CLAWK_CRON_SESSION",
        "CLAWK_INTERACTIVE",
    ):
        monkeypatch.delenv(var, raising=False)
    config = {"mode": "manual", "deny": []}
    monkeypatch.setattr(approval_context, "_get_approval_config", lambda: config)

    def set_mode(mode: str, yolo: bool) -> None:
        config["mode"] = mode
        monkeypatch.setattr(mod, "_YOLO_MODE_FROZEN", yolo)

    return set_mode


@pytest.mark.parametrize(
    ("mode", "yolo"), [("manual", False), ("off", False), ("manual", True)]
)
def test_the_agent_cannot_change_mi_chrome_settings_even_under_yolo(
    approvals, mode, yolo
):
    approvals(mode, yolo)
    for command in CHANGES:
        result = mod.check_all_command_guards(command, "local")
        assert result["approved"] is False and result.get("user_deny") is True, (
            command,
            result,
        )
        assert (
            "belong to the user" in result["message"]
            and "Do NOT retry" in result["message"]
        )


def test_reading_config_and_other_settings_are_untouched(approvals):
    approvals("manual", False)
    for command in (
        "clawk config show",
        "grep my_chrome ~/.clawksis/config.yaml",
        "clawk config set browser.cdp_url ws://127.0.0.1:9222",
        "curl http://127.0.0.1:9119/api/my-chrome/status",
    ):
        assert approval_floors._match_user_deny_rule(command) is None, command
