"""The sidebar footer read ``vunknown`` on a checkout with no reachable release tag.

/api/status now also carries ``display_version`` (``git.<sha>`` for such a checkout), so the
footer can show which commit is running instead of the word "unknown".
"""

import pytest

from clawk_cli.version_info import VersionInfo


@pytest.fixture
def client(monkeypatch, _isolate_clawk_home):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")

    import clawk_state
    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app
    from clawk_constants import get_clawk_home

    monkeypatch.setattr(clawk_state, "DEFAULT_DB_PATH", get_clawk_home() / "state.db")
    c = TestClient(app)
    c.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return c


def test_status_reports_the_commit_when_no_release_tag_is_reachable(
    client, monkeypatch
):
    info = VersionInfo(
        "unknown", "git.abc1234", None, "abc1234" * 5 + "abcde", "main", "git"
    )
    monkeypatch.setattr("clawk_cli.web_routers.status.get_version_info", lambda: info)

    body = client.get("/api/status").json()

    assert body["version"] == "unknown"
    assert body["display_version"] == "git.abc1234"
