"""A thin git runner.

`read` captures output for inspection and never raises on a failing command;
`stream` lets git write straight to the terminal, which is what the fan-out
verbs want.
"""

import os
import shutil
import subprocess
from pathlib import Path

GIT = "git"


def available() -> bool:
    return shutil.which(GIT) is not None


def _parsed_env() -> dict[str, str]:
    """Everything `read` returns is parsed, so pin git's messages to C.

    Under a translated locale a caller matching on git's own wording — as
    the `git clean` reader does — silently sees nothing at all.
    """
    return {**os.environ, "LC_ALL": "C", "LANGUAGE": ""}


def read(repo: Path, *args: str) -> tuple[int, str]:
    """Run git in repo and return (exit status, stripped stdout)."""
    result = subprocess.run(
        [GIT, "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        env=_parsed_env(),
    )
    return result.returncode, result.stdout.strip()


def value(repo: Path, *args: str) -> str | None:
    """Return git's stdout, or None when the command failed."""
    status, output = read(repo, *args)
    return output if status == 0 else None


def stream(repo: Path, args: list[str]) -> int:
    """Run git in repo with its output attached to this process."""
    return subprocess.run([GIT, "-C", str(repo), *args], check=False).returncode
