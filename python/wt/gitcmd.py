"""A thin git runner.

`read` captures output for inspection and never raises on a failing command;
`stream` lets git write straight to the terminal, which is what the fan-out
verbs want. `popen` sits between them for a reader that must see each line as
git writes it, and `run` is for the one command with no repository to run in.

Every entry point goes through `GIT` and, wherever the output is parsed,
`_parsed_env`: a second spelling of the executable or an unpinned locale is
how a caller ends up reading a different git than the rest of the tool does.
"""

import os
import shutil
import subprocess
from pathlib import Path

GIT = "git"


def available() -> bool:
    return shutil.which(GIT) is not None


def _parsed_env() -> dict[str, str]:
    """The environment every git in this package runs under.

    Two hazards, both of which make git answer about something other than
    the repository it was handed. Under a translated locale a caller
    matching on git's own wording — as the `git clean` reader does —
    silently sees nothing at all. And an inherited GIT_DIR or GIT_WORK_TREE,
    as set inside a hook or a `git rebase --exec`, overrides `-C` entirely,
    so wt would inspect and clean whatever repository invoked it.
    """
    environment = {**os.environ, "LC_ALL": "C", "LANGUAGE": ""}
    for inherited in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        environment.pop(inherited, None)
    return environment


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


def popen(repo: Path, *args: str) -> subprocess.Popen[str]:
    """Start git in repo with its stdout piped, line buffered, under C.

    A caller that reads the pipe as it fills can account for work git has
    already done when git later fails: waiting for the whole command to
    finish throws that account away along with the output.
    """
    return subprocess.Popen(
        [GIT, "-C", str(repo), *args],
        text=True,
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_parsed_env(),
    )


def stream(repo: Path, args: list[str]) -> int:
    """Run git in repo with its output attached to this process."""
    return subprocess.run([GIT, "-C", str(repo), *args], check=False).returncode


def run(args: list[str], quiet: bool = False) -> int:
    """Run git outside any repository, under the pinned C locale.

    Cloning has no repository to run in, which is exactly the case that
    tempts a caller into its own bare `git`. quiet sends both streams to
    DEVNULL so a script importing wt can clone without unsuppressable
    chatter.
    """
    sink = subprocess.DEVNULL if quiet else None
    return subprocess.run(
        [GIT, *args],
        stdout=sink,
        stderr=sink,
        check=False,
        env=_parsed_env(),
    ).returncode
