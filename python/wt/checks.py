"""The environment and layout sanity check.

Returns results instead of printing them, so other scripts can reuse the same
checks and decide for themselves what a warning is worth.
"""

import os
import shutil
from dataclasses import dataclass

from . import repos, workspaces
from .config import KNOWN_AGENTS, Config

OK = "ok"
WARN = "warn"
FAIL = "MISSING"


@dataclass(frozen=True)
class CheckResult:
    level: str
    message: str

    @property
    def failed(self) -> bool:
        return self.level == FAIL


def _commands(config: Config) -> list[CheckResult]:
    results = [
        CheckResult(OK, "git")
        if shutil.which("git")
        else CheckResult(FAIL, "git is required")
    ]

    found_agent = False
    for agent in KNOWN_AGENTS:
        if shutil.which(agent):
            found_agent = True
            results.append(CheckResult(OK, f"{agent} agent available"))
        else:
            results.append(
                CheckResult(WARN, f"{agent} agent is not installed")
            )
    if not found_agent:
        results.append(
            CheckResult(FAIL, "no agent installed; wt cannot launch anything")
        )

    if shutil.which(config.agent):
        results.append(CheckResult(OK, f"default agent WT_AGENT={config.agent}"))
    else:
        results.append(
            CheckResult(FAIL, f"default agent is not installed: {config.agent}")
        )

    if shutil.which("gh"):
        results.append(CheckResult(OK, "gh available for owner/repo clones"))
    else:
        results.append(
            CheckResult(WARN, f"gh missing; owner/repo clones use {config.forge}")
        )
    return results


def _limits(config: Config) -> list[CheckResult]:
    if config.max_agents <= 0:
        return [
            CheckResult(
                FAIL,
                f"WT_MAX_AGENTS is not a positive integer: "
                f"{config.max_agents_raw}",
            )
        ]
    return [CheckResult(OK, f"WT_MAX_AGENTS={config.max_agents}")]


def _root(config: Config) -> list[CheckResult]:
    root = config.root
    if not root.exists():
        return [CheckResult(WARN, f"workspace root does not exist yet: {root}")]
    if root.is_symlink():
        return [CheckResult(FAIL, f"workspace root is a symlink: {root}")]
    if not root.is_dir():
        return [CheckResult(FAIL, f"workspace root is not a directory: {root}")]
    if root.stat().st_uid != os.getuid():
        return [CheckResult(FAIL, f"workspace root is not owned by you: {root}")]
    return [CheckResult(OK, f"workspace root {root}")]


def _layout(config: Config) -> list[CheckResult]:
    results: list[CheckResult] = []
    found = workspaces.listing(config)
    for workspace in found:
        directory = workspace.path
        if not (directory / "AGENTS.md").exists():
            results.append(
                CheckResult(WARN, f"{workspace.name} has no guidance file")
            )
        if (directory / ".git").exists():
            results.append(
                CheckResult(FAIL, f"{workspace.name} is itself a repository")
            )
        for owner in sorted(
            entry for entry in directory.iterdir() if entry.is_dir()
        ):
            if (owner / ".git").exists():
                results.append(
                    CheckResult(
                        FAIL,
                        f"{workspace.name}/{owner.name} is a repository, not "
                        f"an owner directory",
                    )
                )
        for name in workspace.repo_names():
            if repos.discover(directory / name):
                results.append(
                    CheckResult(
                        FAIL, f"{workspace.name}/{name} nests a repository"
                    )
                )
                continue
            # A repository that has left the workspace branch is a warning,
            # not a failure: a rebase or a review checkout is legitimate.
            on = repos.branch(directory / name)
            if on != workspace.branch:
                results.append(
                    CheckResult(
                        WARN,
                        f"{workspace.name}/{name} is on {on}, not "
                        f"{workspace.branch}",
                    )
                )
    plural = "" if len(found) == 1 else "s"
    results.append(CheckResult(OK, f"{len(found)} workspace{plural}"))
    return results


def run(config: Config) -> list[CheckResult]:
    """Every check, in report order."""
    results = _commands(config) + _limits(config)
    root_results = _root(config)
    results += root_results
    if root_results[0].level == OK:
        results += _layout(config)
    return results


def failed(results: list[CheckResult]) -> bool:
    return any(result.failed for result in results)
