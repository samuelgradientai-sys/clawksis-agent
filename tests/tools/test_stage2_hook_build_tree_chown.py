"""Contract test: the s6-overlay stage2 hook re-chowns the build trees under
$INSTALL_DIR (/opt/clawksis/.venv, ui-tui, node_modules) to the runtime clawk
UID whenever they are not already clawk-owned — INDEPENDENTLY of whether
$CLAWK_HOME ownership already matches.

Regression guard for the CLAWK_UID/PUID remap path broken by #35027.

`usermod -u <new> clawk` re-chowns the clawk home dir ($CLAWK_HOME ==
/opt/data) to the new UID as a side effect. #35027 gated the build-tree chown
behind `stat $CLAWK_HOME != clawk_uid`, so after any remap that stat is
already satisfied and the build-tree chown was silently skipped — leaving
.venv owned by the build-time UID (10000) and breaking:
  - lazy_deps.py `uv pip install` of platform extras (#15012, #21100)
  - the TUI esbuild rebuild into ui-tui/dist (#28851)

The fix probes the build trees directly (stat .venv) rather than $CLAWK_HOME.

The extraction + stubbed-shell-run approach mirrors
tests/tools/test_stage2_hook_toplevel_chown.py.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE2_HOOK = REPO_ROOT / "docker" / "stage2-hook.sh"


@pytest.fixture(scope="module")
def stage2_text() -> str:
    if not STAGE2_HOOK.exists():
        pytest.skip("docker/stage2-hook.sh not present in this checkout")
    return STAGE2_HOOK.read_text()


def _build_tree_block(text: str) -> str:
    """Extract the build-tree chown block: from the `venv_owner=` probe
    through the closing `fi` of the chown."""
    m = re.search(
        r"(venv_owner=\$\(stat[^\n]*\n(?:.*\n)*?fi)",
        text,
    )
    assert m, "stage2-hook.sh must contain the venv_owner-gated build-tree chown block"
    return m.group(1)


def test_build_tree_chown_not_gated_on_clawk_home(stage2_text: str) -> None:
    """The build-tree chown must NOT live inside the `if [ "$needs_chown" = true ]`
    block keyed on $CLAWK_HOME ownership — that is exactly the #35027 bug."""
    block = _build_tree_block(stage2_text)
    # The block probes the venv owner, not $CLAWK_HOME.
    assert "venv_owner" in block
    assert "$INSTALL_DIR/.venv" in block
    # All three build trees are covered.
    for tree in ("$INSTALL_DIR/.venv", "$INSTALL_DIR/ui-tui", "$INSTALL_DIR/node_modules"):
        assert tree in block, f"build-tree chown must cover {tree}"


def _run_build_tree_block(
    text: str, *, venv_owner: int, clawk_uid: int
) -> bool:
    """Run the extracted build-tree block with `stat`, `id`, and `chown`
    stubbed. Returns True iff the block attempted the recursive chown."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")
    block = _build_tree_block(text)

    with tempfile.TemporaryDirectory() as d:
        dpath = Path(d)
        log = dpath / "chown.log"
        # Stubs:
        #   stat -c %u <path>  -> echo the simulated venv owner
        #   id -u clawk       -> handled via actual_clawk_uid var below
        #   chown ...          -> record that it fired
        script = (
            "set -eu\n"
            f'INSTALL_DIR="/opt/clawksis"\n'
            f'actual_clawk_uid={clawk_uid}\n'
            f'stat() {{ echo {venv_owner}; }}\n'
            f'chown() {{ echo fired >> "{log}"; }}\n'
            + block
        )
        script_path = dpath / "harness.sh"
        script_path.write_text(script)
        proc = subprocess.run([bash, str(script_path)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        return log.exists() and "fired" in log.read_text()


def test_chown_fires_when_venv_owner_differs(stage2_text: str) -> None:
    """The #35027 regression scenario: after a remap $CLAWK_HOME already
    matches the new UID, but the venv is still owned by the build-time UID
    (10000). The build-tree chown MUST still fire."""
    fired = _run_build_tree_block(stage2_text, venv_owner=10000, clawk_uid=4242)
    assert fired, (
        "build-tree chown must fire when the venv is not owned by the runtime "
        "clawk UID, regardless of $CLAWK_HOME ownership (#35027 regression)"
    )


def test_chown_skipped_when_venv_already_owned(stage2_text: str) -> None:
    """Idempotency: once the venv is clawk-owned, the recursive chown is
    skipped on subsequent boots."""
    fired = _run_build_tree_block(stage2_text, venv_owner=4242, clawk_uid=4242)
    assert not fired, (
        "build-tree chown must be skipped when the venv already matches the "
        "runtime clawk UID (avoid expensive recursive chown on every restart)"
    )


def test_chown_skipped_for_default_uid(stage2_text: str) -> None:
    """No remap: venv owned by the default build UID (10000) and clawk is
    still 10000 — nothing to do."""
    fired = _run_build_tree_block(stage2_text, venv_owner=10000, clawk_uid=10000)
    assert not fired
