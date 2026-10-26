"""Deleting a symlink from the dashboard Files page removes the LINK, never what it points at.

The listing used to report a link at its resolved target path and the delete route resolved
the final component too, so trashing a symlinked folder rmtree'd the real directory it pointed
to, while a dangling link (shown with its own trash button) could not be deleted at all (404).
"""

import pytest
from starlette.testclient import TestClient

from clawk_cli import web_server


@pytest.fixture
def files_client(monkeypatch, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("CLAWK_DASHBOARD_FILES_ROOT", str(root))
    prev_auth = getattr(web_server.app.state, "auth_required", None)
    web_server.app.state.auth_required = False
    client = TestClient(web_server.app)
    client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
    try:
        yield client, root.resolve()
    finally:
        client.close()
        web_server.app.state.auth_required = prev_auth


def _entry(client, root, name):
    listing = client.get("/api/files", params={"path": str(root)})
    assert listing.status_code == 200, listing.text
    return next(e for e in listing.json()["entries"] if e["name"] == name)


def test_deleting_a_symlinked_folder_keeps_the_folder_it_points_to(files_client):
    client, root = files_client
    project = root / "project"
    project.mkdir()
    (project / "keep.txt").write_text("precious", encoding="utf-8")
    try:
        (root / "project-link").symlink_to(project, target_is_directory=True)
    except OSError:
        pytest.skip("filesystem does not allow symlinks")

    entry = _entry(client, root, "project-link")
    assert entry["is_symlink"] is True and entry["is_directory"] is True

    response = client.request(
        "DELETE", "/api/files", json={"path": entry["path"], "recursive": True}
    )

    assert response.status_code == 200, response.text
    assert not (root / "project-link").is_symlink()
    assert (project / "keep.txt").read_text(encoding="utf-8") == "precious"


def test_a_dangling_symlink_can_be_deleted(files_client):
    client, root = files_client
    try:
        (root / "dangling").symlink_to(root / "gone")
    except OSError:
        pytest.skip("filesystem does not allow symlinks")

    entry = _entry(client, root, "dangling")
    response = client.request("DELETE", "/api/files", json={"path": entry["path"]})

    assert response.status_code == 200, response.text
    assert not (root / "dangling").is_symlink()
