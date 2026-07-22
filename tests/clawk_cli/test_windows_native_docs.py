from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("website/docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    assert "%LOCALAPPDATA%\\clawk\\clawksis-agent\\venv\\Scripts" in doc
    assert (
        "Get-Command clawk        # should print C:\\Users\\<you>\\AppData\\Local\\clawk\\clawksis-agent\\venv\\Scripts\\clawk.exe"
        in doc
    )
    assert '$clawkBin = "$InstallDir\\venv\\Scripts"' in install
