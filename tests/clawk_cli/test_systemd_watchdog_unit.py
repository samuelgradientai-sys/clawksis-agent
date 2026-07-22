"""Generated service behavior for the opt-in systemd watchdog."""

from __future__ import annotations

from gateway.config import GatewayConfig
from clawk_cli import gateway as gateway_cli


def test_default_user_unit_keeps_simple_service_without_watchdog(monkeypatch):
    monkeypatch.setattr(gateway_cli, "load_gateway_config", GatewayConfig)

    unit = gateway_cli.generate_systemd_unit(system=False)

    assert "Type=simple" in unit
    assert "Type=notify" not in unit
    assert "NotifyAccess=" not in unit
    assert "WatchdogSec=" not in unit


def test_positive_watchdog_config_generates_notify_unit(monkeypatch):
    monkeypatch.setattr(
        gateway_cli,
        "load_gateway_config",
        lambda: GatewayConfig.from_dict({"systemd_watchdog_seconds": 120}),
        raising=False,
    )

    unit = gateway_cli.generate_systemd_unit(system=False)

    assert "Type=notify" in unit
    assert "NotifyAccess=main" in unit
    assert "WatchdogSec=120s" in unit


def test_positive_watchdog_config_generates_notify_system_unit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        gateway_cli,
        "load_gateway_config",
        lambda: GatewayConfig(systemd_watchdog_seconds=30),
    )
    monkeypatch.setattr(
        gateway_cli,
        "_system_service_identity",
        lambda _user: ("clawk", "clawk", str(tmp_path)),
    )

    unit = gateway_cli.generate_systemd_unit(system=True, run_as_user="clawk")

    assert "Type=notify" in unit
    assert "NotifyAccess=main" in unit
    assert "WatchdogSec=30s" in unit


def test_user_unit_reads_watchdog_from_config_yaml(tmp_path, monkeypatch):
    clawk_home = tmp_path / "home"
    clawk_home.mkdir()
    (clawk_home / "config.yaml").write_text(
        "gateway:\n  systemd_watchdog_seconds: 45\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWK_HOME", str(clawk_home))

    unit = gateway_cli.generate_systemd_unit(system=False)

    assert "Type=notify" in unit
    assert "NotifyAccess=main" in unit
    assert "WatchdogSec=45s" in unit


def test_system_unit_reads_watchdog_from_target_home(tmp_path, monkeypatch):
    caller_home = tmp_path / "caller"
    target_home = tmp_path / "target"
    caller_home.mkdir()
    target_home.mkdir()
    (caller_home / "config.yaml").write_text(
        "gateway:\n  systemd_watchdog_seconds: 0\n",
        encoding="utf-8",
    )
    (target_home / "config.yaml").write_text(
        "gateway:\n  systemd_watchdog_seconds: 75\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWK_HOME", str(caller_home))
    monkeypatch.setattr(
        gateway_cli,
        "_system_service_identity",
        lambda _user: ("service", "service", str(tmp_path / "account")),
    )
    monkeypatch.setattr(
        gateway_cli,
        "_clawk_home_for_target_user",
        lambda _home: str(target_home),
    )

    unit = gateway_cli.generate_systemd_unit(system=True, run_as_user="service")

    assert "Type=notify" in unit
    assert "WatchdogSec=75s" in unit


def test_managed_watchdog_override_controls_generated_unit(tmp_path, monkeypatch):
    clawk_home = tmp_path / "home"
    managed_home = tmp_path / "managed"
    clawk_home.mkdir()
    managed_home.mkdir()
    (clawk_home / "config.yaml").write_text(
        "gateway:\n  systemd_watchdog_seconds: 120\n",
        encoding="utf-8",
    )
    (managed_home / "config.yaml").write_text(
        "gateway:\n  systemd_watchdog_seconds: 0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWK_HOME", str(clawk_home))
    monkeypatch.setenv("CLAWK_MANAGED_DIR", str(managed_home))

    from clawk_cli import managed_scope

    managed_scope.invalidate_managed_cache()
    unit = gateway_cli.generate_systemd_unit(system=False)

    assert "Type=simple" in unit
    assert "WatchdogSec=" not in unit
