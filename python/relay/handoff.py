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
from .errors import Blocked, RelayError

# Every generated token in a launch handoff is held to this, so that no
# shell metacharacter can appear in a conforming line. The launcher checks
# it again on the way in: the shell has already parsed by then, but a line
# that does not conform is not one this protocol emitted, and acting on it
# would be acting on something else.
TOKEN = re.compile(r"\A[A-Za-z0-9._/@-]+\Z")
SHA = re.compile(r"\A[0-9a-f]{40}\Z")
BRIEF_PATH = re.compile(
    r"\A\.agent/runs/(?P<run>[^/]+)/(?P<turn>\d{3})-brief\.md\Z"
)


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

    __slots__ = (
        "path",
        "run",
        "turn",
        "claim",
        "branch",
        "protocol",
        "body",
    )

    def __init__(
        self,
        path: str,
        run: str,
        turn: str,
        claim: str,
        branch: str,
        protocol: str,
        body: str = "",
    ) -> None:
        self.path = path
        self.run = run
        self.turn = turn
        self.claim = claim
        self.branch = branch
        self.protocol = protocol
        self.body = body

    @property
    def result_path(self) -> str:
        """Where this turn's result belongs, by the protocol's layout."""
        return f".agent/runs/{self.run}/{self.claim}-result.md"


def find_brief(paths: list[str]) -> re.Match[str]:
    """The one brief a commit published, among the paths it touched.

    A brief is committed on its own, so exactly one match is the normal
    case. Zero means the pinned commit is not a brief commit; more than one
    means the planner broke the single-writer rule, and guessing which of
    them was meant would start the executor on the wrong turn.

    The match comes back rather than the path, so the caller reads the run
    and turn the filename carries without matching it a second time.
    """
    briefs = [
        matched
        for matched in (BRIEF_PATH.match(path) for path in paths)
        if matched is not None
    ]
    if not briefs:
        raise RelayError(
            "the pinned commit publishes no brief; a launch handoff names "
            "the commit a brief was committed in"
        )
    if len(briefs) > 1:
        raise RelayError(
            "the pinned commit publishes more than one brief: "
            + " ".join(sorted(matched.string for matched in briefs))
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
    paths = [
        line.strip() for line in (listed or "").splitlines() if line.strip()
    ]
    matched = find_brief(paths)
    path = matched.string
    text = gitcmd.value(repo, "show", f"{sha}:{path}")
    if text is None:
        raise RelayError(f"cannot read {path} at {sha}")
    fields, body, problems = turnfile.parse(text)
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
        # The same stop, and the same token, that `relay --protocol` gives
        # for the same disagreement. It is not one the blocked channel
        # names, so it is reported here rather than carried to a planner
        # whose table cannot explain it.
        raise Blocked(
            "protocol-mismatch",
            f"the run asks for {found['protocol']} and this build implements "
            f"{PROTOCOL_VERSION}; two parties on different rule sets must "
            f"not proceed",
        )
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
        body=body.strip(),
    )


BASE_PLACEHOLDER = "<the base= that prepare printed>"


def result_front_matter(brief: Brief, agent: str) -> str:
    """The result's front matter, with every value the turn already knows.

    Only `base` is missing, because only the sync that precedes the result
    can say what it is. Everything else was settled when the turn was
    claimed, so an executor deriving it again is an executor with something
    to get wrong — and a turn file is permanent history, immutable once it
    reaches origin, so getting it wrong is not correctable in place.
    """
    return turnfile.render(
        [
            ("protocol", brief.protocol),
            ("run", brief.run),
            ("turn", brief.claim),
            ("role", "executor"),
            ("agent", agent),
            ("branch", brief.branch),
            ("base", BASE_PLACEHOLDER),
            ("answers", brief.path),
        ]
    )


def publish_commands(
    brief: Brief, pointer: Pointer, agent: str, tool: bool
) -> str:
    """The exact way this turn is published, with every value filled in.

    Two commands and the file between them. `relay prepare` must run after
    the work is committed and before the result is written, because the
    shas it prints are the ones the result records and a sync would destroy
    an earlier reading of them; `relay publish` commits and pushes the
    result and the work together.
    """
    if not tool:
        # The protocol's steps are normative and executable by hand, and a
        # missing accelerator is not a blocker. Naming the sections beats
        # paraphrasing them: the paraphrase is what drifts.
        return (
            f"The `relay` command is not installed here, so follow Final "
            f"sync and Executor rules in the protocol by hand, write "
            f"{brief.result_path}, and push the work and the result "
            f"together. Say in the result that you did the steps by hand."
        )
    return (
        f"  relay prepare --protocol {brief.protocol} "
        f"--branch {brief.branch} \\\n"
        f"      --brief {pointer.sha} --brief-path {brief.path}\n"
        f"\n"
        f"Write {brief.result_path} opening with exactly this front matter, "
        f"the one placeholder taken from what prepare printed:\n"
        f"\n"
        f"{result_front_matter(brief, agent)}"
        f"\n"
        f"Then the body, in the order the protocol's Turn file format "
        f"section gives for a result: status:, work: (from prepare's "
        f"work=), needs: unless complete, files touched grouped by intent, "
        f"each check run and its outcome, decisions and deviations, open "
        f"questions. Never report a check you did not run. Then:\n"
        f"\n"
        f"  relay publish --protocol {brief.protocol} "
        f"--branch {brief.branch} \\\n"
        f"      --result {brief.result_path}"
    )


def prompt(
    brief: Brief,
    pointer: Pointer,
    clone: str,
    agent: str = "unknown",
    tool: bool = True,
) -> str:
    """What to open the executor with, for the brief at that commit.

    Every mechanical step is either already done or spelled as an exact
    command: what is left is the work, which is the brief's to say and
    nothing here summarises. Prose that an executor has to turn back into
    commands is the part that gets improvised, so there is none of it.
    """
    return (
        f"You are the executor in a {brief.protocol} run, in this "
        f"workspace's clone of {pointer.repository} at `{clone}`.\n"
        f"\n"
        f"Everything the protocol puts before the work is done: the "
        f"checkout is initialized on {brief.branch}, preflight passed, and "
        f"turn {brief.claim} is claimed and published. Do not repeat any of "
        f"it, and do not read anything else from the run tree.\n"
        f"\n"
        f"Your brief is {brief.path}, pinned at {pointer.sha}, and this is "
        f"it verbatim:\n"
        f"\n"
        f"{_quoted(brief.body)}\n"
        f"\n"
        f"Execute it. When the work is committed, publish the turn with "
        f"exactly this and nothing improvised:\n"
        f"\n"
        f"{publish_commands(brief, pointer, agent, tool)}\n"
        f"\n"
        f"If you are blocked, print `relay blocked {brief.run} "
        f"{brief.claim} <token>` with the protocol's token for the "
        f"condition, and stop. The rules are at {PROTOCOL_URL}; the brief "
        f"above and the commands here are the whole of this turn."
    )


def _quoted(body: str) -> str:
    """The brief, marked off so its own text cannot read as instruction."""
    fence = "-" * 60
    return f"{fence}\n{body}\n{fence}"
