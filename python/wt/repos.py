"""Repository discovery and per-repository status.

Repositories are exactly the ``<owner>/<repo>`` directories of a workspace
that hold a ``.git`` entry. Anything else is left for `wt.checks` to report.
"""

from dataclasses import dataclass
from pathlib import Path

from . import gitcmd


@dataclass(frozen=True)
class RepoStatus:
    """What a workspace listing needs to know about one clone."""

    name: str
    path: Path
    branch: str
    dirty: bool
    ahead: int | None
    behind: int | None

    @property
    def tracking(self) -> str:
        """"ahead N behind N", or empty when the branch has no upstream."""
        if self.ahead is None or self.behind is None:
            return ""
        return f"ahead {self.ahead} behind {self.behind}"

    @property
    def state(self) -> str:
        return "dirty" if self.dirty else "clean"


def _sorted_dirs(parent: Path) -> list[Path]:
    try:
        entries = [
            entry
            for entry in parent.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        ]
    except OSError:
        return []
    return sorted(entries, key=lambda entry: entry.name)


def discover(workspace_dir: Path) -> list[str]:
    """Return sorted "owner/repo" names for every clone in the workspace."""
    found: list[str] = []
    for owner in _sorted_dirs(workspace_dir):
        for repo in _sorted_dirs(owner):
            if (repo / ".git").exists():
                found.append(f"{owner.name}/{repo.name}")
    return found


def branch(repo: Path) -> str:
    name = gitcmd.value(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if name is None:
        return "(no commits)"
    if name != "HEAD":
        return name
    short = gitcmd.value(repo, "rev-parse", "--short", "HEAD") or "unknown"
    return f"detached@{short}"


def is_dirty(repo: Path) -> bool:
    porcelain = gitcmd.value(
        repo, "status", "--porcelain", "--untracked-files=normal"
    )
    return bool(porcelain)


def _count(repo: Path, revision_range: str) -> int | None:
    counted = gitcmd.value(repo, "rev-list", "--count", revision_range)
    if counted is None:
        return None
    try:
        return int(counted)
    except ValueError:
        return None


def ahead_behind(repo: Path) -> tuple[int | None, int | None]:
    """Commits ahead of and behind the upstream, or (None, None)."""
    ahead = _count(repo, "@{upstream}..HEAD")
    if ahead is None:
        return None, None
    return ahead, _count(repo, "HEAD..@{upstream}")


def status(workspace_dir: Path, name: str) -> RepoStatus:
    repo = workspace_dir / name
    ahead, behind = ahead_behind(repo)
    return RepoStatus(
        name=name,
        path=repo,
        branch=branch(repo),
        dirty=is_dirty(repo),
        ahead=ahead,
        behind=behind,
    )


def has_unsaved_work(repo: Path) -> bool:
    """True when removing the workspace would lose work.

    A branch with no upstream counts as unsaved: nothing has received it.
    """
    if is_dirty(repo):
        return True
    if gitcmd.value(repo, "stash", "list"):
        return True
    ahead = _count(repo, "@{upstream}..HEAD")
    return ahead is None or ahead > 0
