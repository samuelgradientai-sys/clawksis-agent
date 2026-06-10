"""Contract test: the s6-overlay stage2 hook and main-wrapper reject an

unsupported `docker run --user <arbitrary-uid>:<gid>` start with actionable

guidance, while still allowing:



  - root start (id -u == 0)

  - `--user <clawk-uid>` (the supported non-root start, #34648 / #34837)



Background: in the tini era `docker run --user $(id -u):$(id -g)` was used to

make container-written files match the host user. Under s6-overlay this can't

work — the bootstrap (UID remap, volume/build-tree chown, config seeding) needs

root, and the baked image dirs are owned by the clawk build UID, so an

arbitrary pinned UID can't write them (EACCES on a bind mount, hard crash on a

named volume). The supported path is root start + CLAWK_UID/CLAWK_GID (or the

PUID/PGID aliases), which remaps the clawk user and chowns the volume.



The guard fires only when the current UID is neither root NOR the clawk UID,

so the #34648 `--user 10000:10000` case (pinning to the clawk UID itself) is

unaffected.



Extraction + stubbed-shell-run mirrors

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

MAIN_WRAPPER = REPO_ROOT / "docker" / "main-wrapper.sh"


def _read(p: Path) -> str:

    if not p.exists():
        pytest.skip(f"{p} not present in this checkout")

    return p.read_text()


def _guard_block(text: str) -> str:
    """Extract the `cur_uid=...; if [ ... ]; then ... exit 1; fi` guard."""

    m = re.search(
        r"(cur_uid=\"\$\(id -u\)\"\nif \[ \"\$cur_uid\" != 0 \](?:.*\n)*?fi)",
        text,
    )

    assert m, "expected the --user guard block (cur_uid + non-root/non-clawk check)"

    return m.group(1)


@pytest.mark.parametrize("path", [STAGE2_HOOK, MAIN_WRAPPER])
def test_guard_present_and_mentions_remediation(path: Path) -> None:

    text = _read(path)

    block = _guard_block(text)

    # Must check non-root AND non-clawk-uid (so --user 10000:10000 is allowed).

    assert '"$cur_uid" != 0' in block

    assert '"$cur_uid" != "$(id -u clawk)"' in block

    assert "exit 1" in block

    # Must point users at the supported env vars.

    assert "CLAWK_UID" in block and "CLAWK_GID" in block

    assert "PUID" in block and "PGID" in block


def _run_guard(
    text: str, *, cur_uid: int, clawk_uid: int = 10000
) -> subprocess.CompletedProcess:
    """Run the extracted guard with `id` stubbed. Returns the completed process

    (rc 1 + stderr message when rejected, rc 0 when allowed through)."""

    bash = shutil.which("bash")

    if bash is None:
        pytest.skip("bash not available")

    block = _guard_block(text)

    with tempfile.TemporaryDirectory() as d:
        script = (
            "set -e\n"
            # Stub `id`: `id -u` -> cur_uid; `id -u clawk` -> clawk_uid.
            f'id() {{ if [ "$2" = clawk ]; then echo {clawk_uid}; else echo {cur_uid}; fi; }}\n'
            + block
            + "\necho GUARD_PASSED\n"  # only reached when the guard allows through
        )

        sp = Path(d) / "h.sh"

        sp.write_text(script)

        return subprocess.run([bash, str(sp)], capture_output=True, text=True)


def test_arbitrary_user_uid_is_rejected() -> None:
    """An arbitrary host UID (1000), neither root nor clawk, is rejected."""

    for text in (_read(STAGE2_HOOK), _read(MAIN_WRAPPER)):
        proc = _run_guard(text, cur_uid=1000, clawk_uid=10000)

        assert proc.returncode == 1, f"expected rejection, got rc={proc.returncode}"

        assert "not supported" in proc.stderr

        assert "GUARD_PASSED" not in proc.stdout


def test_root_start_passes() -> None:
    """Root start (uid 0) is never blocked."""

    for text in (_read(STAGE2_HOOK), _read(MAIN_WRAPPER)):
        proc = _run_guard(text, cur_uid=0, clawk_uid=10000)

        assert proc.returncode == 0, proc.stderr

        assert "GUARD_PASSED" in proc.stdout


def test_user_pinned_to_clawk_uid_passes() -> None:
    """`--user 10000:10000` (the clawk UID itself) is the supported non-root

    start from #34648 / #34837 and must NOT be blocked."""

    for text in (_read(STAGE2_HOOK), _read(MAIN_WRAPPER)):
        proc = _run_guard(text, cur_uid=10000, clawk_uid=10000)

        assert proc.returncode == 0, proc.stderr

        assert "GUARD_PASSED" in proc.stdout


def test_user_pinned_to_remapped_clawk_uid_passes() -> None:
    """After a CLAWK_UID remap the clawk UID is e.g. 4242; a container pinned

    to that same UID must still pass (cur_uid == clawk_uid)."""

    for text in (_read(STAGE2_HOOK), _read(MAIN_WRAPPER)):
        proc = _run_guard(text, cur_uid=4242, clawk_uid=4242)

        assert proc.returncode == 0, proc.stderr

        assert "GUARD_PASSED" in proc.stdout
