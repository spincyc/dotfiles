"""The protocol's mechanical steps, one function each.

Each function runs one procedure from `relay/PROTOCOL.md` and returns what
happened; none of them print, and none of them exit. A stop the protocol
names leaves as `errors.Blocked` carrying the token the user is permitted
to relay, so the caller never has to decide what a failure meant.

Nothing here rewrites published history: the only ref this package moves
is the named branch, only ever forward, and the only rebase it runs is the
one the final sync defines over the unpublished range.
"""

import re
from pathlib import Path
from typing import NamedTuple

from . import PROTOCOL_VERSION, gitcmd, identity, turnfile
from .errors import Blocked, RelayError, UsageError

# git's own wording for a missing or refused credential. Matched under the
# pinned C locale, which is why gitcmd pins it.
_CREDENTIAL_WORDS = (
    "authentication",
    "permission",
    "credential",
    "could not read username",
    "could not read password",
    "publickey",
    "access denied",
    "terminal prompts disabled",
)

_REJECTION_WORDS = (
    "rejected",
    "non-fast-forward",
    "fetch first",
    "stale info",
)

_RESULT_FIELD = re.compile(
    r"^\s*(?:[-*]\s+)?`?(?P<name>base|work)`?:\s*`?(?P<value>[^`\s]+)`?\s*$",
    re.MULTILINE,
)


class SyncResult(NamedTuple):
    """Which branch of the final sync ran, and what it moved."""

    action: str
    message: str
    before: str
    after: str
    dry_run: bool

    @property
    def moved(self) -> bool:
        return self.after != self.before


class ClaimResult(NamedTuple):
    path: str
    base: str
    retried: bool


class PrepareResult(NamedTuple):
    sync: SyncResult
    branch: str
    head: str


class PublishResult(NamedTuple):
    path: str
    head: str
    retried: bool


def is_credential_failure(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _CREDENTIAL_WORDS)


def classify_push_failure(text: str) -> str:
    """Name what a failed push actually was.

    Order matters: a hook rejection also says "rejected", and a refused
    credential also says "denied", so the most specific reading is tried
    first and the generic non-fast-forward reading last.
    """
    lowered = text.lower()
    if is_credential_failure(lowered):
        return "no-credentials"
    if "hook" in lowered:
        return "hooks-rejected"
    if any(word in lowered for word in _REJECTION_WORDS):
        return "rejected"
    return "unknown"


def head(repo: Path) -> str:
    """The full sha at HEAD."""
    found = gitcmd.value(repo, "rev-parse", "HEAD")
    if found is None:
        raise RelayError(f"cannot read HEAD in {repo}")
    return found


def _remote_ref(branch: str) -> str:
    return f"origin/{branch}"


def check_remote(repo: Path, spec: str) -> str:
    """origin must be the repository the handoff names."""
    url = gitcmd.value(repo, "remote", "get-url", "origin")
    if url is None:
        raise Blocked(
            "preflight-failed",
            f"{repo} has no remote named origin; the protocol requires one",
        )
    if not identity.same_repository(url, spec):
        raise Blocked(
            "preflight-failed",
            f"origin is {url} ({identity.normalize_remote(url)}), not "
            f"{spec} ({identity.normalize_spec(spec)}): this is not the "
            f"repository the handoff names",
        )
    return f"origin is {spec}"


def check_clean(repo: Path) -> str:
    """The tracked tree must be clean.

    Untracked files are excluded deliberately. A bare `git status
    --porcelain` reports them, so an editor's swap file or a scratch note
    would fail preflight on a checkout that has nothing uncommitted at
    all. Commit discipline -- explicit pathspecs, never `-a`, never `add
    -A` -- is what keeps an untracked file out of a commit, so untracked
    files are not what this gate is for.
    """
    result = gitcmd.run(repo, "status", "--porcelain", "--untracked-files=no")
    if not result.ok:
        raise RelayError(f"git status failed in {repo}: {result.err}")
    if result.out:
        raise Blocked(
            "preflight-failed",
            "tracked files are modified; the protocol stops here and "
            "changes nothing, so never stash, discard, or commit this "
            f"work to get past it:\n{result.out}",
        )
    return "tracked tree is clean"


def check_no_operation(repo: Path) -> str:
    """No rebase or merge may be half-finished."""
    for ref in ("REBASE_HEAD", "MERGE_HEAD"):
        if gitcmd.succeeds(repo, "rev-parse", "-q", "--verify", ref):
            raise Blocked(
                "preflight-failed",
                f"{ref} exists, so a rebase or merge is in progress; "
                f"finish or abort it by hand before starting a turn",
            )
    return "no rebase or merge in progress"


def fetch(repo: Path) -> str:
    """`git fetch origin`, with a missing credential named as such."""
    result = gitcmd.run(repo, "fetch", "origin")
    if result.ok:
        return "fetched origin"
    if is_credential_failure(result.err):
        raise Blocked(
            "no-credentials",
            f"git fetch origin failed for want of credentials:\n"
            f"{result.err}",
        )
    raise Blocked(
        "preflight-failed", f"git fetch origin failed:\n{result.err}"
    )


def check_branch(repo: Path, branch: str) -> str:
    current = gitcmd.value(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if current != branch:
        raise Blocked(
            "preflight-failed",
            f"HEAD is on {current!r}, not {branch!r}; only the workspace "
            f"initialization may change branches, and only before the "
            f"turn is claimed",
        )
    return f"HEAD is on {branch}"


def check_brief_published(repo: Path, branch: str, sha: str) -> str:
    remote = _remote_ref(branch)
    if not gitcmd.succeeds(repo, "merge-base", "--is-ancestor", sha, remote):
        raise Blocked(
            "preflight-failed",
            f"{sha} is not an ancestor of {remote}; a pinned sha that "
            f"`git show` can read proves only that the object exists "
            f"locally, and this one is not on the named branch",
        )
    return f"{sha} is on {remote}"


def check_not_stale(repo: Path, branch: str) -> str:
    """HEAD must already carry everything origin published."""
    remote = _remote_ref(branch)
    if gitcmd.succeeds(repo, "merge-base", "--is-ancestor", remote, "HEAD"):
        return f"{remote} is an ancestor of HEAD"
    if gitcmd.succeeds(repo, "merge-base", "--is-ancestor", "HEAD", remote):
        raise Blocked(
            "preflight-failed",
            f"HEAD is behind {remote} and carries nothing of its own, so "
            f"this is a pure fast-forward and it is fixable: run `relay "
            f"sync --branch {branch}`, then run preflight again",
        )
    raise Blocked(
        "preflight-failed",
        f"HEAD and {remote} have diverged: this checkout holds commits "
        f"origin does not, on a base origin has moved past. That is "
        f"unfinished work from an earlier turn, not something preflight "
        f"may reconcile for you; report it",
    )


def preflight(repo: Path, spec: str, branch: str, brief: str) -> list[str]:
    """The preflight the executor runs every turn, in the protocol's order.

    Stops at the first failure, so the report names the first thing that
    was actually wrong rather than every consequence of it.
    """
    done = [check_remote(repo, spec), check_clean(repo), fetch(repo)]
    done.append(check_branch(repo, branch))
    done.append(check_brief_published(repo, branch, brief))
    done.append(check_no_operation(repo))
    done.append(check_not_stale(repo, branch))
    return done


def initialize(repo: Path, spec: str, branch: str) -> list[str]:
    """The one branch change the protocol permits, before any claim."""
    done = [
        check_remote(repo, spec),
        check_clean(repo),
        check_no_operation(repo),
        fetch(repo),
    ]
    remote = _remote_ref(branch)
    if not gitcmd.succeeds(
        repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}"
    ):
        raise Blocked(
            "preflight-failed",
            f"refs/remotes/{remote} does not exist after fetching; the "
            f"handoff names a branch origin does not carry",
        )
    done.append(f"{remote} exists")
    current = gitcmd.value(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if current == branch:
        done.append(f"HEAD already names {branch}; no branch change")
        return done
    local = gitcmd.succeeds(
        repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"
    )
    if not local:
        result = gitcmd.run(repo, "switch", "--track", remote)
        if not result.ok:
            raise Blocked(
                "preflight-failed",
                f"git switch --track {remote} failed:\n"
                f"{result.err or result.out}",
            )
        done.append(f"switched to a new {branch} tracking {remote}")
        return done
    upstream = gitcmd.value(
        repo, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"
    )
    if upstream != remote:
        raise Blocked(
            "preflight-failed",
            f"local {branch} tracks {upstream or 'nothing'}, not {remote}; "
            f"this is a hard stop, because retargeting, resetting, or "
            f"recreating that branch is not something the handoff "
            f"authorizes",
        )
    result = gitcmd.run(repo, "switch", branch)
    if not result.ok:
        raise Blocked(
            "preflight-failed",
            f"git switch {branch} failed:\n{result.err or result.out}",
        )
    done.append(f"switched to {branch}, which tracks {remote}")
    return done


def _abort_rebase(repo: Path, before: str, failure: gitcmd.Completed) -> None:
    """Undo a conflicted rebase and prove the checkout is back."""
    gitcmd.run(repo, "rebase", "--abort")
    now = gitcmd.value(repo, "rev-parse", "HEAD")
    if now != before:
        raise RelayError(
            f"the rebase failed and `git rebase --abort` did not restore "
            f"HEAD: it was {before} and is now {now or 'unreadable'}. This "
            f"checkout is not in the state relay found it in; resolve that "
            f"by hand before running anything else here"
        )
    raise Blocked(
        "sync-conflict",
        f"the rebase conflicted; it has been aborted and HEAD is back at "
        f"{before}. Resolve the conflict deliberately, in your own "
        f"commits only:\n{failure.err or failure.out}",
    )


def sync(repo: Path, branch: str, dry_run: bool = False) -> SyncResult:
    """The protocol's final sync: reconcile without destroying history.

    A rebase is a rewrite, so one runs only when the branch has actually
    diverged, and never over commits origin already carries. `--dry-run`
    still fetches -- reading remote refs moves no local work -- because
    naming the path from stale refs would be naming the wrong one.
    """
    remote = _remote_ref(branch)
    before = head(repo)
    fetch(repo)
    if not gitcmd.succeeds(
        repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}"
    ):
        raise Blocked(
            "preflight-failed",
            f"refs/remotes/{remote} does not exist after fetching; there "
            f"is nothing to synchronize against",
        )
    if gitcmd.succeeds(repo, "merge-base", "--is-ancestor", remote, "HEAD"):
        # Already synchronized. Any merge ancestry here is intentional and
        # a rebase would flatten it, so this branch does nothing at all.
        return SyncResult(
            "synchronized",
            "synchronized: no rebase needed",
            before,
            before,
            dry_run,
        )
    if gitcmd.succeeds(repo, "merge-base", "--is-ancestor", "HEAD", remote):
        if dry_run:
            return SyncResult(
                "fast-forward", "fast-forward", before, before, True
            )
        result = gitcmd.run(repo, "merge", remote, "--ff-only")
        if not result.ok:
            raise RelayError(
                f"git merge {remote} --ff-only failed although HEAD is an "
                f"ancestor of {remote}:\n{result.err or result.out}"
            )
        return SyncResult(
            "fast-forward", "fast-forward", before, head(repo), False
        )
    merges = gitcmd.value(
        repo, "rev-list", "--merges", "HEAD", f"^{remote}"
    )
    if merges:
        # The unpublished range carries deliberate merges; replaying it
        # flat would throw that ancestry away.
        action = "rebase --rebase-merges"
        arguments = ("rebase", "--rebase-merges", remote)
    else:
        action = "rebase"
        arguments = ("rebase", remote)
    if dry_run:
        return SyncResult(action, action, before, before, True)
    result = gitcmd.run(repo, *arguments)
    if not result.ok:
        _abort_rebase(repo, before, result)
    return SyncResult(action, action, before, head(repo), False)


def _commit(repo: Path, relative: str, message: str) -> None:
    """Commit exactly one path, by pathspec.

    Never `-a` and never `add -A`: the protocol forbids committing a path
    the brief did not put in scope, and a pathspec is the only spelling
    that cannot pick one up by accident.
    """
    staged = gitcmd.run(repo, "add", "--", relative)
    if not staged.ok:
        raise RelayError(
            f"git add -- {relative} failed:\n{staged.err or staged.out}"
        )
    result = gitcmd.run(
        repo, "commit", "--quiet", "-m", message, "--", relative
    )
    if result.ok:
        return
    text = f"{result.err}\n{result.out}"
    if "hook" in text.lower():
        raise Blocked(
            "hooks-rejected",
            f"a commit hook rejected {relative}:\n{text.strip()}",
        )
    raise RelayError(
        f"git commit of {relative} failed:\n{text.strip()}"
    )


def _push(repo: Path, branch: str) -> gitcmd.Completed:
    return gitcmd.run(repo, "push", "origin", branch)


def _blocked_push(failure: gitcmd.Completed, detail: str) -> Blocked:
    kind = classify_push_failure(f"{failure.err}\n{failure.out}")
    token = kind if kind in ("no-credentials", "hooks-rejected") else (
        "push-rejected"
    )
    return Blocked(token, f"{detail}:\n{failure.err or failure.out}")


def claim_path(run: str, turn: str) -> str:
    return f".agent/runs/{run}/{turn}-claim.md"


def claim(
    repo: Path, run: str, turn: str, branch: str, agent: str
) -> ClaimResult:
    """Claim the turn number by publishing `<nnn>-claim.md`.

    The claim push is what narrows a duplicate paste, so a rejection is
    interrogated rather than retried blindly: a claim already at origin
    means the turn is owned and the work must not be redone, while a ref
    that merely moved is a race worth one retry.
    """
    if not turnfile.TURN.match(turn):
        raise UsageError(f"turn {turn!r} is not a three-digit number")
    check_branch(repo, branch)
    relative = claim_path(run, turn)
    path = repo / relative
    if path.exists():
        raise RelayError(
            f"{relative} already exists; a published turn file is "
            f"immutable, so relay will not overwrite one. If this turn is "
            f"yours and unpublished, deal with it deliberately"
        )
    base = head(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    front = turnfile.render(
        [
            ("protocol", PROTOCOL_VERSION),
            ("run", run),
            ("turn", turn),
            ("role", "executor"),
            ("agent", agent),
            ("branch", branch),
            ("base", base),
        ]
    )
    path.write_text(
        f"{front}\nClaiming turn {turn} of run {run} on {branch}.\n",
        encoding="utf-8",
    )
    _commit(repo, relative, f"relay: claim {run} {turn}")
    pushed = _push(repo, branch)
    if pushed.ok:
        return ClaimResult(relative, base, False)
    if classify_push_failure(f"{pushed.err}\n{pushed.out}") != "rejected":
        raise _blocked_push(pushed, f"pushing the claim of turn {turn}")
    fetch(repo)
    if gitcmd.succeeds(
        repo, "cat-file", "-e", f"{_remote_ref(branch)}:{relative}"
    ):
        raise Blocked(
            "claim-replay",
            f"{relative} already exists at {_remote_ref(branch)}: turn "
            f"{turn} is already owned. Stop without redoing the work. The "
            f"local claim commit is unpublished and must not be pushed",
        )
    synced = sync(repo, branch)
    retried = _push(repo, branch)
    if retried.ok:
        return ClaimResult(relative, head(repo), True)
    raise _blocked_push(
        retried,
        f"the claim push was rejected, {_remote_ref(branch)} had only "
        f"moved ({synced.action}), and the one permitted retry was "
        f"rejected too",
    )


def prepare(
    repo: Path, branch: str, brief: str, brief_path: str
) -> PrepareResult:
    """Sync, then prove the pinned brief still byte-matches origin.

    A rewrite of a file the executor is not touching applies cleanly and
    silently, so a rebase conflict is no evidence either way: the blob is
    compared directly instead.
    """
    result = sync(repo, branch)
    remote = _remote_ref(branch)
    pinned = gitcmd.value(
        repo, "rev-parse", "--verify", f"{brief}:{brief_path}"
    )
    if pinned is None:
        raise Blocked(
            "brief-unreadable",
            f"cannot read {brief_path} at {brief}; a pinned sha that no "
            f"longer resolves means the branch was rewritten while the run "
            f"was open. Stop and report; do not guess at a replacement",
        )
    published = gitcmd.value(
        repo, "rev-parse", "--verify", f"{remote}:{brief_path}"
    )
    if published is None:
        raise Blocked(
            "brief-mutated",
            f"{brief_path} does not exist at {remote}, although the brief "
            f"was pinned at {brief}",
        )
    if pinned != published:
        raise Blocked(
            "brief-mutated",
            f"{brief_path} at {remote} is blob {published}, not the "
            f"pinned {pinned}: the brief has been rewritten since it was "
            f"handed over. That is the protocol violation to report",
        )
    return PrepareResult(result, branch, head(repo))


def _result_shas(repo: Path, relative: str) -> tuple[str, str]:
    """The `base:` and `work:` a result file records.

    Front matter first, then the body: the protocol puts `base:` in the
    front matter and `work:` in the result body, and a file that carries
    both in the front matter is still answering the same question.
    """
    text = (repo / relative).read_text(encoding="utf-8")
    fields, body, _ = turnfile.parse(text)
    found = turnfile.mapping(fields)
    for match in _RESULT_FIELD.finditer(body):
        found.setdefault(match.group("name"), match.group("value"))
    missing = [name for name in ("base", "work") if name not in found]
    if missing:
        raise RelayError(
            f"{relative} records no {' or '.join(missing)}; a result names "
            f"the commit it was written against and the work it published"
        )
    return found["base"], found["work"]


def _work_head(repo: Path, relative: str) -> str:
    """The commit a rewritten result file should now name.

    Once the result is committed, HEAD is the result commit itself, and
    the shas the result records are those of the work underneath it.
    """
    current = head(repo)
    newest = gitcmd.value(repo, "rev-list", "-1", "HEAD", "--", relative)
    if newest == current:
        parent = gitcmd.value(repo, "rev-parse", "--verify", "HEAD^")
        if parent is not None:
            return parent
    return current


def _check_shas(
    branch: str, expected: str, base: str, work: str, relative: str
) -> None:
    wanted = f"{branch}@{expected}"
    if base == expected and work in (wanted, "none"):
        return
    raise Blocked(
        "stale-shas",
        f"{relative} records base: {base} and work: {work}, which no "
        f"longer name this checkout. Rewrite them as base: {expected} and "
        f"work: {wanted}, then publish again",
    )


def publish(repo: Path, branch: str, relative: str) -> PublishResult:
    """Commit and push the result, refusing to publish one that lies."""
    check_branch(repo, branch)
    if not (repo / relative).is_file():
        raise UsageError(f"{relative} is not a file in {repo}")
    current = head(repo)
    base, work = _result_shas(repo, relative)
    _check_shas(branch, current, base, work, relative)
    _commit(repo, relative, f"relay: result {relative}")
    pushed = _push(repo, branch)
    if pushed.ok:
        return PublishResult(relative, current, False)
    if classify_push_failure(f"{pushed.err}\n{pushed.out}") != "rejected":
        raise _blocked_push(pushed, f"pushing {relative}")
    synced = sync(repo, branch)
    if synced.moved:
        corrected = _work_head(repo, relative)
        raise Blocked(
            "stale-shas",
            f"the push was rejected and the sync ({synced.action}) moved "
            f"the branch, so the shas in {relative} no longer name its "
            f"base. Rewrite them as base: {corrected} and work: "
            f"{branch}@{corrected}, amend the unpublished result commit, "
            f"and publish again rather than pushing a result that lies",
        )
    retried = _push(repo, branch)
    if retried.ok:
        return PublishResult(relative, current, True)
    raise _blocked_push(
        retried,
        f"the push of {relative} was rejected and the one permitted "
        f"retry was rejected too",
    )
