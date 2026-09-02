"""The launch handoff: a run pointer, and the prompt derived from it.

`relay-v6` lets a planner emit one command the user runs directly, instead
of a session to start and a prompt to paste into it. The command carries no
prose — a workspace, a branch, a repository, and the commit the brief was
published in — and everything else is read back out of the brief's own front
matter at that commit. This module is that reading: the pointer's grammar,
the search for the brief the commit published, and the prompt composed from
what it says.

The composition lives here rather than in the launcher because it is
protocol knowledge: which document to read, what to initialize, which turn
to claim. A launcher supplies a workspace and a clone.
"""

import re
from pathlib import Path

from . import PROTOCOL_URL, PROTOCOL_VERSION, gitcmd, turnfile
from .errors import RelayError

# Every generated token in a launch handoff is held to this, so that no
# shell metacharacter can appear in a conforming line. The launcher checks
# it again on the way in: the shell has already parsed by then, but a line
# that does not conform is not one this protocol emitted, and acting on it
# would be acting on something else.
TOKEN = re.compile(r"\A[A-Za-z0-9._/@-]+\Z")
SHA = re.compile(r"\A[0-9a-f]{40}\Z")
BRIEF_PATH = re.compile(r"\A\.agent/runs/(?P<run>[^/]+)/(?P<turn>\d{3})-brief\.md\Z")


class Pointer:
    """A `<owner>/<repo>@<sha>` run pointer, already checked."""

    __slots__ = ("repository", "sha")

    def __init__(self, repository: str, sha: str) -> None:
        self.repository = repository
        self.sha = sha

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Pointer({self.repository!r}, {self.sha!r})"


def parse_pointer(value: str) -> Pointer:
    """Read `<owner>/<repo>@<40-hex sha>`, refusing anything else."""
    repository, separator, sha = value.rpartition("@")
    if not separator:
        raise RelayError(
            f"a run pointer is <owner>/<repo>@<sha>, not: {value}"
        )
    if not TOKEN.match(repository) or "/" not in repository:
        raise RelayError(f"not a usable repository: {repository}")
    if not SHA.match(sha):
        raise RelayError(
            f"a brief is pinned by its full 40-character sha, not: {sha}"
        )
    return Pointer(repository=repository, sha=sha)


class Brief:
    """What the brief at a pinned commit says about its own run."""

    __slots__ = ("path", "run", "turn", "claim", "branch", "protocol")

    def __init__(
        self,
        path: str,
        run: str,
        turn: str,
        claim: str,
        branch: str,
        protocol: str,
    ) -> None:
        self.path = path
        self.run = run
        self.turn = turn
        self.claim = claim
        self.branch = branch
        self.protocol = protocol


def find_brief(paths: list[str]) -> str:
    """The one brief a commit published, among the paths it touched.

    A brief is committed on its own, so exactly one match is the normal
    case. Zero means the pinned commit is not a brief commit; more than one
    means the planner broke the single-writer rule, and guessing which of
    them was meant would start the executor on the wrong turn.
    """
    briefs = [path for path in paths if BRIEF_PATH.match(path)]
    if not briefs:
        raise RelayError(
            "the pinned commit publishes no brief; a launch handoff names "
            "the commit a brief was committed in"
        )
    if len(briefs) > 1:
        raise RelayError(
            "the pinned commit publishes more than one brief: "
            + " ".join(sorted(briefs))
        )
    return briefs[0]


def read_brief(repo: Path, sha: str) -> Brief:
    """Find and read the brief the pinned commit published.

    The front matter is the authority for the run, the turn and the branch.
    Nothing here is inferred from the pointer or from the filename beyond
    locating the file, and the two are cross-checked so a mismatch is
    reported rather than reconciled.
    """
    if not gitcmd.succeeds(repo, "cat-file", "-e", f"{sha}^{{commit}}"):
        raise RelayError(f"the checkout does not have commit {sha}")
    listed = gitcmd.value(repo, "show", "--name-only", "--format=", sha)
    paths = [line.strip() for line in (listed or "").splitlines() if line.strip()]
    path = find_brief(paths)
    text = gitcmd.value(repo, "show", f"{sha}:{path}")
    if text is None:
        raise RelayError(f"cannot read {path} at {sha}")
    fields, _, problems = turnfile.parse(text)
    if problems:
        location, message = problems[0]
        raise RelayError(f"{path} is not a turn file: {location}: {message}")
    found = turnfile.mapping(fields)
    missing = [
        name
        for name in ("protocol", "run", "turn", "branch")
        if not found.get(name)
    ]
    if missing:
        raise RelayError(
            f"{path} names no " + ", ".join(missing) + " in its front matter"
        )
    if found["protocol"] != PROTOCOL_VERSION:
        raise RelayError(
            f"the run asks for {found['protocol']} and this build implements "
            f"{PROTOCOL_VERSION}; two parties on different rule sets must "
            f"not proceed"
        )
    matched = BRIEF_PATH.match(path)
    assert matched is not None  # find_brief only returns matching paths
    if found["run"] != matched.group("run"):
        raise RelayError(
            f"{path} says it belongs to run {found['run']}, and its path "
            f"says {matched.group('run')}"
        )
    if found["turn"] != matched.group("turn"):
        raise RelayError(
            f"{path} says it is turn {found['turn']}, and its path says "
            f"{matched.group('turn')}"
        )
    return Brief(
        path=path,
        run=found["run"],
        turn=found["turn"],
        # The executor claims the next turn number after the brief's, and
        # three digits are the field width for the life of a run.
        claim=f"{int(found['turn']) + 1:03d}",
        branch=found["branch"],
        protocol=found["protocol"],
    )


def prompt(brief: Brief, pointer: Pointer, clone: str) -> str:
    """What to open the executor with, for the brief at that commit.

    It says where the rules are, where the brief is, and which turn to
    claim, and nothing about the work: the brief is the authority for that,
    and a launcher that summarised it would be a second, unpinned brief.
    """
    return (
        f"You are the executor in a {brief.protocol} run. Read "
        f"{PROTOCOL_URL} completely before acting; it is self-sufficient "
        f"and it governs over anything below.\n"
        f"\n"
        f"Run {brief.run}, on branch {brief.branch}, in this workspace's "
        f"clone of {pointer.repository} at `{clone}`, which was cloned onto "
        f"that branch. Initialize it as the protocol permits, run preflight, "
        f"then read the brief with `git show {pointer.sha}:{brief.path}`, "
        f"claim turn {brief.claim}, and execute that brief.\n"
        f"\n"
        f"Read nothing else from the run tree. If you are blocked, print "
        f"the one blocked-channel line the protocol specifies and stop."
    )
