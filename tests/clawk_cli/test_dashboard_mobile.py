"""`clawk dashboard mobile`: a phone-ready address for the dashboard without weakening it.

The dashboard stays on loopback with the login gate forced; the command either reuses the
domain already published, or routes Tailscale's private HTTPS name to it. systemd, Tailscale
and the network are faked here; what is pinned is what the command writes and runs.
"""

import argparse
import subprocess

import pytest

from clawk_cli import dashboard_mobile as dm
from clawk_cli import dashboard_service as ds

TS_STATUS = {"BackendState": "Running", "Self": {"DNSName": "vps.tail1234.ts.net."}}


def _args(**kw):
    return argparse.Namespace(
        **{"port": 9119, "tailscale": False, "domain": None, **kw}
    )


def test_tailscale_name_comes_from_a_logged_in_status():
    assert dm.tailscale_host(TS_STATUS) == "vps.tail1234.ts.net"
    assert dm.tailscale_host({**TS_STATUS, "BackendState": "NeedsLogin"}) is None
    assert dm.tailscale_host(None) is None


def test_published_hosts_merge_public_url_and_domain_mode_without_duplicates():
    env = {"CLAWK_DASHBOARD_PUBLIC_HOST": "panel.example.com, vps.tail1234.ts.net"}
    assert dm.published_hosts(env, "https://Panel.example.com/") == [
        "panel.example.com",
        "vps.tail1234.ts.net",
    ]
    assert dm.published_hosts({}, "") == []


def test_without_a_front_door_it_explains_the_two_safe_options(monkeypatch, capsys):
    monkeypatch.setattr(ds, "_existing_domain_env", dict)
    monkeypatch.setattr(dm, "_public_url", lambda: "")
    monkeypatch.setattr(
        ds, "_install_unit", lambda *a: pytest.fail("must not touch systemd")
    )

    dm.cmd_dashboard_mobile(_args())

    out = capsys.readouterr().out
    assert "clawk dashboard mobile --tailscale" in out
    assert "clawk dashboard mobile --domain" in out


def test_a_published_domain_is_printed_with_the_login_hint(monkeypatch, capsys):
    monkeypatch.setattr(
        ds,
        "_existing_domain_env",
        lambda: {"CLAWK_DASHBOARD_PUBLIC_HOST": "panel.example.com"},
    )
    monkeypatch.setattr(dm, "_public_url", lambda: "")
    monkeypatch.setattr(dm, "_login_configured", lambda: False)
    shown = []
    monkeypatch.setattr(dm, "print_qr", lambda url: shown.append(url) or True)

    dm.cmd_dashboard_mobile(_args())

    out = capsys.readouterr().out
    assert shown == ["https://panel.example.com"]
    assert "https://panel.example.com" in out and "clawk dashboard password" in out


@pytest.fixture
def fake_tailscale(monkeypatch):
    calls = {"unit": None, "run": []}
    monkeypatch.setattr(dm, "_tailscale_exe", lambda: "/usr/bin/tailscale")
    monkeypatch.setattr(dm, "_tailscale_status", lambda exe: TS_STATUS)
    monkeypatch.setattr(ds, "_require_linux_systemd_root", lambda label: None)
    monkeypatch.setattr(
        ds,
        "_existing_domain_env",
        lambda: {"CLAWK_DASHBOARD_PUBLIC_HOST": "panel.example.com"},
    )
    monkeypatch.setattr(dm, "_unit_bind_host", lambda: "127.0.0.1")
    monkeypatch.setattr(
        ds,
        "_install_unit",
        lambda host, port, env: calls.update(unit=(host, port, env)),
    )
    monkeypatch.setattr(ds, "_probe_http", lambda port, host_header=None: True)
    monkeypatch.setattr(dm, "_login_configured", lambda: True)
    monkeypatch.setattr(dm, "print_qr", lambda url: True)
    return calls


def test_tailscale_routes_its_private_https_name_to_the_gated_dashboard(
    fake_tailscale, monkeypatch, capsys
):
    def run(cmd, **kw):
        fake_tailscale["run"].append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(dm.subprocess, "run", run)

    dm.cmd_dashboard_mobile(_args(tailscale=True))

    host, port, env = fake_tailscale["unit"]
    assert (host, port) == ("127.0.0.1", 9119)
    assert env == {
        "CLAWK_DASHBOARD_FORCE_GATE": "1",
        "CLAWK_DASHBOARD_PUBLIC_HOST": "panel.example.com,vps.tail1234.ts.net",
    }
    assert fake_tailscale["run"] == [
        ["/usr/bin/tailscale", "serve", "--bg", "--https=443", "http://127.0.0.1:9119"]
    ]
    assert "https://vps.tail1234.ts.net" in capsys.readouterr().out


def test_a_failed_tailscale_serve_says_how_to_enable_https(
    fake_tailscale, monkeypatch, capsys
):
    monkeypatch.setattr(
        dm.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(
            cmd, 1, "", "HTTPS is not enabled"
        ),
    )

    with pytest.raises(SystemExit):
        dm.cmd_dashboard_mobile(_args(tailscale=True))

    assert "HTTPS Certificates" in capsys.readouterr().out


def test_the_home_screen_manifest_is_reachable_before_login():
    from clawk_cli.dashboard_auth.middleware import _path_is_public

    assert _path_is_public("/manifest.json")
