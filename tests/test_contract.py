"""The agent contract: the strict audit, every example, and every command's output schema"""

import io
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from py_yfinance.cli import app

APP = "py_yfinance.cli:app"
ROOT = Path(__file__).resolve().parents[1]


def treaty(*argv: str) -> subprocess.CompletedProcess[str]:
    found = shutil.which("treaty", path=str(Path(sys.executable).parent))
    assert found is not None, "treaty is not installed in this environment"
    return subprocess.run([found, *argv], cwd=ROOT, capture_output=True, text=True)


def test_the_strict_audit_passes() -> None:
    done = treaty("audit", APP, "--strict", "--format", "plain")
    assert done.returncode == 0, done.stdout + done.stderr


def app_examples() -> list[str]:
    commands = app.manifest()["commands"]
    builtins = {path.value for path in app.builtins}
    return [
        example["command"]
        for name, command in commands.items()
        if name not in builtins
        for example in command.get("examples", [])
    ]


@pytest.mark.parametrize("example", app_examples())
def test_an_example_parses(example: str) -> None:
    argv = shlex.split(example)[1:]
    out = io.StringIO()
    code = app.run([*argv, "--validate-only"], stdout=out, stderr=io.StringIO(), env={})
    assert code == 0, out.getvalue()


def test_every_command_declares_its_output() -> None:
    builtins = {path.value for path in app.builtins}
    for name, command in app.manifest()["commands"].items():
        if name not in builtins:
            assert command["output_schema"], name
