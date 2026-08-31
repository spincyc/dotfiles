"""The environment and layout sanity check.

Returns results instead of printing them, so other scripts can reuse the same
checks and decide for themselves what a warning is worth.

Nothing here may raise on a broken layout: `wt check` exists to report one,
and a traceback in place of a report is the one failure mode this command
cannot afford.
"""

import os
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from . import gitcmd, guidance, repos, slots, workspaces
from .config import KNOWN_AGENTS, Config
from .errors import WtError


class Level(StrEnum):
    """How much a result matters.

    A member's value is its own name, not a display label: a caller
    comparing against `Level.FAIL` and a caller printing `result.level` have
    to see the same thing. `cli.py` owns whatever label the report prints.
    """

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    level: Level
    message: str

    @property
    def failed(self) -> bool:
        return self.level == Level.FAIL


def _commands(config: Config) -> list[CheckResult]:
    results = [
        CheckResult(Level.OK, "git")
        if shutil.which("git")
        else CheckResult(Level.FAIL, "git is required")
    ]

    # Only the configured agent can fail this check. wt launches that one and
    # no other, so a machine that has chosen a third agent is not broken for
    # lacking claude; the previous rule failed such a setup and then reported
    # the very same agent as ok two lines later.
    if shutil.which(config.agent):
        results.append(
            CheckResult(Level.OK, f"default agent WT_AGENT={config.agent}")
        )
    else:
        results.append(
            CheckResult(
                Level.FAIL, f"default agent is not installed: {config.agent}"
            )
        )

    # The others are still worth naming, because `wt <agent> <workspace>`
    # can launch any of them, but their absence is news, not a fault.
    for agent in KNOWN_AGENTS:
        if agent == config.agent:
            continue
        results.append(
            CheckResult(Level.OK, f"{agent} agent available")
            if shutil.which(agent)
            else CheckResult(Level.WARN, f"{agent} agent is not installed")
        )

    if shutil.which("gh"):
        results.append(
            CheckResult(Level.OK, "gh available for owner/repo clones")
        )
    else:
        results.append(
            CheckResult(
                Level.WARN,
                f"gh missing; owner/repo clones use {config.forge}",
            )
        )
    return results


def _agents(config: Config) -> list[CheckResult]:
    """Report the running agents, and fail on a registry nothing can read.

    An unreadable registry is not an empty one: every verb that deletes a
    workspace asks it which trees are occupied, and an answer of "none" is
    the one that deletes a workspace out from under a live agent.
    """
    try:
        running = slots.SlotPool(config.agents_dir).running()
    except (OSError, WtError) as error:
        # The refusal already names the directory and the reason, in the same
        # words the verbs that stop on it use.
        return [CheckResult(Level.FAIL, str(error))]
    plural = "" if len(running) == 1 else "s"
    return [CheckResult(Level.OK, f"{len(running)} agent{plural} running")]


def _root(config: Config) -> list[CheckResult]:
    root = config.root
    if not root.exists():
        return [
            CheckResult(
                Level.WARN, f"workspace root does not exist yet: {root}"
            )
        ]
    if root.is_symlink():
        return [
            CheckResult(Level.FAIL, f"workspace root is a symlink: {root}")
        ]
    if not root.is_dir():
        return [
            CheckResult(
                Level.FAIL, f"workspace root is not a directory: {root}"
            )
        ]
    try:
        owner = root.stat().st_uid
    except OSError as error:
        return [
            CheckResult(Level.FAIL, f"workspace root cannot be read: {error}")
        ]
    if owner != os.getuid():
        return [
            CheckResult(
                Level.FAIL, f"workspace root is not owned by you: {root}"
            )
        ]
    return [CheckResult(Level.OK, f"workspace root {root}")]


def _branch(repo: Path, expected: str, label: str) -> list[CheckResult]:
    """What to say about the branch one clone is on.

    `repos.branch` answers with a sentence-ready name for a listing, which
    means its `(no commits)` sentinel reads as a branch name here: a clone
    `wt` had just made was reported as having left the branch it was in fact
    on. Ask git for the symbolic ref instead, and let an unborn branch be its
    own message.
    """
    on = gitcmd.value(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    if on is None:
        # Detached, or git could not answer at all; repos.branch words both,
        # and neither is the workspace branch.
        return [
            CheckResult(
                Level.WARN,
                f"{label} is on {repos.branch(repo)}, not {expected}",
            )
        ]
    # A repository that has left the workspace branch is a warning, not a
    # failure: a rebase or a review checkout is legitimate.
    if on != expected:
        return [CheckResult(Level.WARN, f"{label} is on {on}, not {expected}")]
    if gitcmd.value(repo, "rev-parse", "--verify", "--quiet", "HEAD") is None:
        return [
            CheckResult(
                Level.OK, f"{label} is on {expected}, with no commits yet"
            )
        ]
    return []


def _workspace(workspace: workspaces.Workspace) -> list[CheckResult]:
    directory = workspace.path
    results: list[CheckResult] = []

    if (directory / ".git").exists():
        results.append(
            CheckResult(Level.FAIL, f"{workspace.name} is itself a repository")
        )

    # The layout rules live in one place now. Deriving them a second time
    # here is how `wt check` and `wt sweep` came to disagree about what may
    # legitimately sit in a workspace.
    try:
        inventory = workspaces.inventory(workspace)
    except (OSError, WtError) as error:
        return results + [
            CheckResult(
                Level.FAIL, f"{workspace.name} cannot be inspected: {error}"
            )
        ]

    if not inventory.readable:
        # The sweep refuses this workspace outright, so a check that merely
        # warned would disagree with the verb that acts on it — and would
        # go on advising a `wt new` that cannot write there either.
        return results + [
            CheckResult(Level.FAIL, f"{workspace.name} cannot be read")
        ]

    missing = sorted(
        name
        for name in guidance.FILENAMES
        if not ((directory / name).exists() or (directory / name).is_symlink())
    )
    if missing:
        results.append(
            CheckResult(
                Level.WARN,
                f"{workspace.name} is missing {', '.join(missing)}; "
                f"wt new {workspace.name} writes them back",
            )
        )

    for owner in inventory.owners:
        # An owner directory holding clones is never a stray, so testing
        # only strays lost this case entirely: what surfaced instead was the
        # `.git` entry, downgraded to a warning that advised moving it under
        # .scratch, where `wt tidy` would then delete it.
        if (directory / owner / ".git").exists():
            results.append(
                CheckResult(
                    Level.FAIL,
                    f"{workspace.name}/{owner} is a repository, not an "
                    f"owner directory",
                )
            )

    for stray in inventory.strays:
        if (directory / stray / ".git").exists():
            results.append(
                CheckResult(
                    Level.FAIL,
                    f"{workspace.name}/{stray} is a repository, not an "
                    f"owner directory",
                )
            )
        elif stray.rpartition("/")[2].startswith("."):
            results.append(
                CheckResult(
                    Level.WARN,
                    f"{workspace.name}/{stray} belongs to no clone",
                )
            )
        else:
            results.append(
                CheckResult(
                    Level.WARN,
                    f"{workspace.name}/{stray} belongs to no clone; move it "
                    f"under .scratch or remove it",
                )
            )

    for name in inventory.nested:
        results.append(
            CheckResult(
                Level.FAIL, f"{workspace.name}/{name} nests a repository"
            )
        )

    nested = set(inventory.nested)
    for name in inventory.clones:
        if name in nested:
            continue
        results += _branch(
            directory / name, workspace.branch, f"{workspace.name}/{name}"
        )
    return results


def _projects(config: Config) -> list[CheckResult]:
    """Report a project directory wt cannot read.

    `listing` tolerates an unreadable directory by returning nothing, which
    is right for a verb that must not crash and wrong as a report: an
    unreadable project made `wt ls` say "No workspaces" and `wt check` pass,
    while the workspaces under it were simply invisible.
    """
    results: list[CheckResult] = []
    try:
        entries = sorted(config.root.iterdir(), key=lambda item: item.name)
    except OSError:
        return results
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        try:
            list(entry.iterdir())
        except OSError as error:
            results.append(
                CheckResult(
                    Level.FAIL,
                    f"project {entry.name} cannot be read: {error.strerror}",
                )
            )
    return results


def _layout(config: Config) -> list[CheckResult]:
    results: list[CheckResult] = _projects(config)
    try:
        found = workspaces.listing(config)
    except OSError as error:
        return [
            CheckResult(
                Level.FAIL, f"workspace root cannot be listed: {error}"
            )
        ]
    for workspace in found:
        results += _workspace(workspace)
    plural = "" if len(found) == 1 else "s"
    results.append(CheckResult(Level.OK, f"{len(found)} workspace{plural}"))
    return results


def run(config: Config) -> list[CheckResult]:
    """Every check, in report order."""
    results = _commands(config)
    root_results = _root(config)
    results += root_results
    if root_results[0].level is Level.OK:
        # The registry lives under the root, so there is nothing to say about
        # it until the root itself checks out.
        results += _agents(config) + _layout(config)
    return results


def failed(results: list[CheckResult]) -> bool:
    return any(result.failed for result in results)
