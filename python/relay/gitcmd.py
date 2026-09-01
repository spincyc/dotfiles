"""A thin git runner.

`run` captures both streams and never raises on a failing command, because
every decision in this package is made from what git said rather than from
whether it exited zero. `value` and `succeeds` are the two shapes that
account for nearly every call site.

Every entry point goes through `GIT` and `_parsed_env`: a second spelling
of the executable or an unpinned locale is how a caller ends up reading a
different git than the rest of the tool does.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

GIT = "git"


class Completed(NamedTuple):
    """One git invocation: its status and both of its streams."""

    status: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.status == 0


def available() -> bool:
    return shutil.which(GIT) is not None


def _parsed_env() -> dict[str, str]:
    """The environment every git in this package runs under.

    Three hazards. Under a translated locale a caller matching on git's
    own wording -- as the push and fetch classifiers here do -- silently
    sees nothing at all. An inherited GIT_DIR, GIT_WORK_TREE, or
    GIT_INDEX_FILE, as set inside a hook or a `git rebase --exec`,
    overrides `-C` entirely, so relay would inspect and commit to whatever
    repository invoked it. And a terminal prompt for credentials has
    nobody to answer it here: relay runs under an agent, so a missing
    credential must come back as a failure this package can report as
    `no-credentials` rather than as a session that hangs forever.
    """
    environment = {
        **os.environ,
        "LC_ALL": "C",
        "LANGUAGE": "",
        "GIT_TERMINAL_PROMPT": "0",
    }
    for inherited in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        environment.pop(inherited, None)
    return environment


def run(repo: Path, *args: str) -> Completed:
    """Run git in repo and return its status and stripped output."""
    result = subprocess.run(
        [GIT, "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=_parsed_env(),
    )
    return Completed(
        result.returncode,
        result.stdout.strip(),
        result.stderr.strip(),
    )


def value(repo: Path, *args: str) -> str | None:
    """Return git's stdout, or None when the command failed."""
    result = run(repo, *args)
    return result.out if result.ok else None


def succeeds(repo: Path, *args: str) -> bool:
    """True when git exited zero; the output is not wanted."""
    return run(repo, *args).ok


def toplevel(start: Path) -> Path | None:
    """The working tree root containing start, or None."""
    found = value(start, "rev-parse", "--show-toplevel")
    return Path(found) if found else None
