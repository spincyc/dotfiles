"""The workspace branch.

Every clone in a workspace works on one branch named after the workspace
slug, so the commits of one line of work are recognisable in whichever
repository they land in.

A fresh branch is made to track the remote branch the clone arrived on. That
keeps `wt status` and `wt sync` meaningful before anything is pushed, keeps
`wt rm` able to tell saved work from unsaved, and makes a bare `git push`
refuse rather than send the work to the default branch: publishing is
deliberately `git push -u origin <branch>`.
"""

from pathlib import Path

from . import gitcmd


def name(prefix: str, slug: str) -> str:
    """The branch the clones of one workspace work on."""
    return f"{prefix}/{slug}"


def _verifies(repo: Path, revision: str) -> bool:
    value = gitcmd.value(repo, "rev-parse", "--verify", "--quiet", revision)
    return value is not None


def checkout(repo: Path, branch: str) -> bool:
    """Put a freshly cloned repo on branch. False when git refused."""
    if _verifies(repo, f"refs/remotes/origin/{branch}"):
        # Earlier work on this slug is already published; continue it.
        status, _ = gitcmd.read(repo, "checkout", branch)
        return status == 0

    # An empty clone has nothing to branch from, but the unborn branch is
    # still the right place for its first commit.
    landed = gitcmd.value(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if landed in (None, "HEAD") or not _verifies(repo, "HEAD"):
        status, _ = gitcmd.read(repo, "checkout", "-b", branch)
        return status == 0

    status, _ = gitcmd.read(
        repo, "checkout", "-b", branch, "--track", f"origin/{landed}"
    )
    return status == 0
