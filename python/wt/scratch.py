"""The `.scratch` convention and the transient files it names.

Everything an agent leaves behind that is not going into a commit belongs
under a `.scratch` directory: the workspace root for anything that is not
about one repository, and the top of a clone for anything that is. Naming
transient files is what makes deleting them safe, and it keeps them from
looking like work: an untracked file is otherwise indistinguishable from an
edit someone forgot to commit.

Each clone excludes `.scratch/` in `.git/info/exclude` rather than in a
committed `.gitignore`. The convention is `wt`'s, so it costs the cloned
repository nothing, and the exclusion is what keeps scratch files from
dirtying a clone and blocking `wt clean`.
"""

import os
import shutil
from pathlib import Path

from . import gitcmd
from .errors import WtError

NAME = ".scratch"
EXCLUDE_LINE = ".scratch/"
_EXCLUDE_NOTE = "# wt: transient files live under .scratch"
# git clean announces each path it removes, or would remove, this way.
_REMOVAL_PREFIXES = ("Removing ", "Would remove ")


def exclude_file(repo: Path) -> Path | None:
    """The clone's local exclude file, or None when repo is not a clone.

    Anchored on the work-tree root, because `git rev-parse` climbs out of a
    directory that is not a repository: answering for an enclosing
    repository would write into a clone this workspace does not own. The
    common directory, not the git directory, is the one a linked worktree
    actually reads its excludes from.
    """
    top = gitcmd.value(repo, "rev-parse", "--show-toplevel")
    if top is None:
        return None
    try:
        if Path(top).resolve() != repo.resolve():
            return None
    except OSError:
        return None
    common = gitcmd.value(repo, "rev-parse", "--git-common-dir")
    if common is None:
        return None
    # git resolves a relative answer against its working directory, which is
    # repo itself; joining an absolute one simply replaces the left side.
    return repo / common / "info" / "exclude"


def excluded(repo: Path) -> bool:
    """True when this clone already keeps .scratch out of Git."""
    path = exclude_file(repo)
    if path is None or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return any(line.strip() == EXCLUDE_LINE for line in text.splitlines())


def ensure_exclude(repo: Path) -> bool:
    """Exclude .scratch from Git locally. True when the line was added."""
    path = exclude_file(repo)
    if path is None or excluded(repo):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        path.read_text(encoding="utf-8", errors="replace")
        if path.is_file()
        else ""
    )
    separator = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{separator}{_EXCLUDE_NOTE}\n{EXCLUDE_LINE}\n")
    return True


def present(parent: Path) -> bool:
    """True when parent holds a .scratch entry worth removing."""
    candidate = parent / NAME
    return candidate.is_symlink() or candidate.exists()


def remove(path: Path) -> None:
    """Delete one transient path without following it out of the workspace."""
    if path.is_symlink() or not path.is_dir():
        path.unlink()
        return
    if path.stat().st_uid != os.getuid():
        raise WtError(f"not removing a path owned by someone else: {path}")
    shutil.rmtree(path)


def tracked(repo: Path) -> list[str]:
    """The paths under .scratch that Git already tracks.

    Excluding a path does not untrack it, so a repository that committed
    something under .scratch would quietly go dirty if tidying deleted it.
    """
    listed = gitcmd.value(repo, "ls-files", "--", NAME)
    return listed.splitlines() if listed else []


def clean_ignored(repo: Path, dry_run: bool = False) -> list[str]:
    """Remove every Git-ignored path in the clone, or list what would go.

    Only ignored paths are touched: tracked files and untracked files that
    nothing ignores are exactly the ones that might still be work. Nested
    repositories are left where they are; git skips them without -ff, and
    reaching into one is not this command's business.
    """
    status, output = gitcmd.read(
        repo,
        # Unquoted paths so the report matches the filesystem, and .scratch
        # named outright so a dry run sees the same ignore set as the real
        # run does after the exclusion is written.
        "-c",
        "core.quotePath=false",
        "clean",
        "-Xdn" if dry_run else "-Xdf",
        "-e",
        EXCLUDE_LINE,
    )
    if status != 0:
        raise WtError(f"git clean failed in {repo}")
    removed: list[str] = []
    for line in output.splitlines():
        for prefix in _REMOVAL_PREFIXES:
            if line.startswith(prefix):
                path = line[len(prefix) :]
                # .scratch is reported on its own, ignored or not.
                if path.split("/")[0] != NAME:
                    removed.append(path)
                break
    return removed
