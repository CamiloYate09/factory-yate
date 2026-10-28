import subprocess
import sys

from factory import __version__


def test_version_cli():
    out = subprocess.run(
        [sys.executable, "-m", "factory", "--version"], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == f"factory {__version__}"
