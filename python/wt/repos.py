"""Repository discovery and per-repository status.

Repositories are exactly the ``<owner>/<repo>`` directories of a workspace
that hold a ``.git`` entry. Anything else is left for `wt.checks` to report.

The questions here decide whether a clone may be deleted, so every one of
them distinguishes "git said no" from "git could not say".
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
    upstream: str | None = None
    answered: bool = True

    @property
    def tracking(self) -> str:
        """"ahead N behind N", or empty when the branch has no upstream."""
        if self.ahead is None or self.behind is None:
            return ""
        return f"ahead {self.ahead} behind {self.behind}"

    @property
    def state(self) -> str:
        if not self.answered:
            # A listing that printed "clean" here would be a lie the user
            # acts on; say so instead.
            return "unknown"
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
        # An unborn branch has no commit for rev-parse to resolve, but HEAD
        # still names it. Reporting "(no commits)" as though it were the
        # branch made `wt push` say a fresh clone was on the wrong branch
        # when it was on the right one.
        unborn = gitcmd.value(
            repo, "symbolic-ref", "--short", "--quiet", "HEAD"
        )
        return unborn or "(no commits)"
    if name != "HEAD":
        return name
    short = gitcmd.value(repo, "rev-parse", "--short", "HEAD") or "unknown"
    return f"detached@{short}"


def upstream(repo: Path) -> str | None:
    """The upstream of the current branch, or None when it tracks nothing.

    Which upstream a branch tracks is the fact the workspace guidance turns
    on: still on origin/main means nothing published this line of work yet.
    """
    return gitcmd.value(
        repo,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
    )


def default_branch(repo: Path) -> str | None:
    """The clone's default branch, from refs/remotes/origin/HEAD.

    Never guesses "main": a wrong default sends a rebase or a diff against a
    branch the project does not use, and no answer is easier to recover from
    than a plausible wrong one.

    The symref is verified rather than merely read. `git symbolic-ref`
    happily resolves the *text* of a symref whose target no longer exists,
    so a clone whose default branch was renamed upstream would otherwise
    keep naming the deleted branch — and `wt sync`'s own `fetch --prune` is
    what deletes it.
    """
    verified = gitcmd.value(
        repo, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/HEAD"
    )
    if not verified:
        return None
    head = gitcmd.value(
        repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"
    )
    return head.removeprefix("origin/") if head else None


def line_of_work(repo: Path, branch: str) -> str | None:
    """The revision range holding this workspace's commits, or None.

    One definition, so `log`, `push` and `sync` cannot disagree about what
    "the work in this clone" means — they did, and each was differently
    wrong about a clone on a side branch or a detached HEAD.
    """
    default = default_branch(repo)
    if default is None:
        return None
    return f"origin/{default}..{branch}"


def unpushed(repo: Path, branch: str) -> int | None:
    """Commits on `branch` that no remote has yet. None when git could not say.

    Deliberately narrower than `unpublished`: that one asks whether *any*
    local ref holds unshared work, which is the right question before
    deleting a clone and the wrong one before pushing a branch. Reading the
    wide answer as a branch answer made `wt push` publish empty branches for
    clones whose only unshared commit sat on an unrelated side branch.
    """
    if not _verifies(repo, branch):
        return None
    return _count(repo, branch, "--not", "--remotes")


def has_commits(repo: Path) -> bool:
    """True when HEAD resolves to a commit.

    A clone of a repository that has none yet is a normal state — it is what
    `gh repo create` leaves behind — and it is not the same as a clone whose
    default branch could not be determined.
    """
    return _verifies(repo, "HEAD")


def _verifies(repo: Path, revision: str) -> bool:
    return gitcmd.value(
        repo, "rev-parse", "--verify", "--quiet", revision
    ) is not None


def changes(repo: Path) -> list[str] | None:
    """Porcelain status lines, or None when git could not answer."""
    status, output = gitcmd.read(
        repo, "status", "--porcelain", "--untracked-files=normal"
    )
    if status != 0:
        return None
    return output.splitlines()


def is_dirty(repo: Path) -> bool:
    """True when the tree has changes OR git could not answer.

    A corrupt index makes `git status` exit non-zero; reading that as "no
    changes" would hand the clone to `rm -rf` with the work still in it.
    """
    lines = changes(repo)
    return lines is None or bool(lines)


def _count(repo: Path, *revisions: str) -> int | None:
    counted = gitcmd.value(repo, "rev-list", "--count", *revisions)
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
    lines = changes(repo)
    return RepoStatus(
        name=name,
        path=repo,
        branch=branch(repo),
        dirty=lines is None or bool(lines),
        ahead=ahead,
        behind=behind,
        upstream=upstream(repo),
        answered=lines is not None,
    )


def unpublished(repo: Path) -> bool | None:
    """True when local branches or tags hold commits no remote has.

    Tags are asked about together with branches because parking work on a
    local tag — `git tag wip-save` before switching away — is a habit, and a
    scan of `refs/heads` alone calls that commit saved.
    """
    counted = _count(repo, "--branches", "--tags", "--not", "--remotes")
    if counted is None:
        return None
    return counted > 0


def _head_unpublished(repo: Path) -> bool:
    """True when HEAD holds commits no remote has, or git could not say.

    A detached HEAD is not among `--branches --tags`, so an interrupted
    rebase or a bisect leaves its commits invisible to `unpublished`.
    """
    counted = _count(repo, "HEAD", "--not", "--remotes")
    if counted is not None:
        return counted > 0
    # rev-list also refuses on an unborn HEAD, which names no commit and so
    # holds nothing to lose; every other refusal is a question unanswered.
    named = gitcmd.value(repo, "rev-parse", "--verify", "--quiet", "HEAD")
    return named is not None


def _ignored_repositories(repo: Path) -> list[str] | None:
    """Ignored repository paths, or None when git could not answer."""
    status, output = gitcmd.read(
        repo,
        "ls-files",
        "-z",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
    )
    if status != 0:
        return None
    found: list[str] = []
    for entry in output.split("\0"):
        name = entry.rstrip("/")
        # Only ignored entries that are themselves clones matter, and asking
        # each one is why this must not become a recursive walk: an ignored
        # node_modules would cost more than every other check together.
        if name and (repo / name / ".git").exists():
            found.append(name)
    return sorted(found)


def ignored_repositories(repo: Path) -> list[str]:
    """Git-ignored paths inside this clone that are themselves repositories.

    A vendored checkout listed in .gitignore keeps its own commits, and the
    outer `git status` is silent about it by construction.
    """
    return _ignored_repositories(repo) or []


def unpublished_branches(repo: Path) -> list[str]:
    """Every local branch holding commits no upstream has received.

    Reporting verbs want the names; `has_unsaved_work` wants only the yes or
    no, and asks `unpublished`, which sees tags as well.
    """
    listed = gitcmd.value(
        repo,
        "for-each-ref",
        "--format=%(refname:short)%09%(upstream:short)",
        "refs/heads",
    )
    if not listed:
        return []
    unpublished: list[str] = []
    for line in listed.splitlines():
        branch, _, upstream = line.partition("\t")
        if not upstream:
            unpublished.append(branch)
            continue
        ahead = _count(repo, f"{upstream}..{branch}")
        if ahead is None or ahead > 0:
            unpublished.append(branch)
    return unpublished


def has_unsaved_work(repo: Path) -> bool:
    """True when removing this clone would lose work.

    This is the gate in front of `shutil.rmtree`, so it fails closed: every
    branch below returns True both when the answer is yes and when git could
    not give one. Only the final line, reached once every question came back
    answered and empty, returns False.
    """
    if is_dirty(repo):
        return True

    stashed = gitcmd.value(repo, "stash", "list")
    if stashed is None or stashed:
        return True

    outstanding = unpublished(repo)
    if outstanding is None or outstanding:
        return True

    if _head_unpublished(repo):
        return True

    nested = _ignored_repositories(repo)
    if nested is None or nested:
        return True

    return False
