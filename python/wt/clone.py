"""Clone-spec parsing and cloning.

Whatever form the spec takes, the clone lands at ``<owner>/<repo>`` inside the
workspace, on the workspace branch. Bare ``owner/repo`` specs go through gh
when it is installed, so private repositories work without a separate
credential setup, and a path on this disk is cloned from where it is: seeding
a workspace from a canonical checkout is both legitimate and far faster than
going back to the forge.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import branches, gitcmd, scratch
from .errors import WtError
from .names import is_safe_component

# A spec that starts one of these ways names the filesystem, not a forge.
_LOCAL_PREFIXES = ("/", "./", "../", "~")


@dataclass(frozen=True)
class CloneSpec:
    """Where a repository comes from and where it belongs."""

    owner: str
    repo: str
    url: str | None

    @property
    def name(self) -> str:
        return f"{self.owner}/{self.repo}"

    def clone_url(self, forge: str) -> str:
        return self.url or f"{forge.rstrip('/')}/{self.name}.git"


def _local_path(spec: str) -> str:
    """Expand a local spec to one absolute path that means one repository.

    `~` and a relative path are both read against this process, so they are
    settled here rather than left for git to resolve somewhere else. The
    result is normalised lexically, the way the shell reads `..`, so that a
    path like ../telos still names an owner directory that exists.
    """
    expanded = os.path.expanduser(spec)
    return os.path.normpath(os.path.abspath(expanded))


def with_owner(spec: CloneSpec, owner: str) -> CloneSpec:
    """The same source, filed under a different owner.

    The owner is otherwise the second-to-last path component, which is right
    for a forge spec and a guess for a local path: `~/mirror/telos` and
    `~/git/spincyc/telos` are the same repository filed under two owners,
    and only the caller knows which one they meant.
    """
    if not is_safe_component(owner):
        raise WtError(f"not a usable owner: {owner}")
    return CloneSpec(owner=owner, repo=spec.repo, url=spec.url)


def parse(spec: str) -> CloneSpec:
    """Read a local path, owner/repo, https://host/owner/repo(.git) or SSH.

    A local path becomes the clone URL itself. Treating it as a bare
    forge spec — which is what keeping only its last two components amounts
    to — quietly clones a different repository of the same name from the
    network, at a different commit and without any of the local branches.
    """
    url: str | None = None
    if spec.startswith(_LOCAL_PREFIXES):
        url = _local_path(spec)
        tail = url
    elif "://" in spec:
        url = spec
        tail = spec.split("://", 1)[1].partition("/")[2]
    elif "@" in spec and ":" in spec.split("@", 1)[1]:
        url = spec
        tail = spec.split(":", 1)[1]
    elif "/" in spec:
        tail = spec
    else:
        raise WtError(f"cannot derive owner/repo from: {spec}")

    parts = [part for part in tail.rstrip("/").split("/") if part]
    if len(parts) < 2:
        raise WtError(f"cannot derive owner/repo from: {spec}")
    owner, repo = parts[-2], parts[-1]
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    if not is_safe_component(owner) or not is_safe_component(repo):
        raise WtError(f"cannot derive owner/repo from: {spec}")
    return CloneSpec(owner=owner, repo=repo, url=url)


def into(
    workspace_dir: Path, spec: CloneSpec, forge: str, branch: str
) -> bool:
    """Clone spec into the workspace. False when it was already there.

    An existing clone keeps whatever branch it is on; moving a checkout
    someone may be working in is not this command's business.
    """
    target = workspace_dir / spec.owner / spec.repo
    if (target / ".git").exists():
        # Same name, possibly a different repository: saying "ok" about a
        # clone that came from somewhere else tells the caller they have
        # what they asked for when they do not.
        here = gitcmd.value(target, "remote", "get-url", "origin")
        wanted = spec.clone_url(forge)
        if here is not None and here != wanted and spec.url is not None:
            raise WtError(
                f"{spec.name} is already here, from {here}, not {wanted}"
            )
        return False
    if target.exists():
        raise WtError(
            f"clone target exists and is not a repository: {target}"
        )

    owner_made = not target.parent.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    if spec.url is None and shutil.which("gh"):
        command = ["gh", "repo", "clone", spec.name, str(target)]
        failed = subprocess.run(command, check=False).returncode != 0
    else:
        failed = gitcmd.run(
            ["clone", "--", spec.clone_url(forge), str(target)]
        ) != 0
    if failed:
        if owner_made:
            # An empty owner directory is a stray, and a stray pins the
            # workspace against `wt sweep` and `wt rm` for good.
            try:
                target.parent.rmdir()
            except OSError:
                pass
        raise WtError(f"clone failed: {spec.name}")
    if not branches.checkout(target, branch):
        raise WtError(
            f"cloned {spec.name}, but it would not go on branch {branch}"
        )
    # Local, never committed: transient files go under .scratch here, and a
    # clone that hides them cannot be mistaken for one holding work. Bounded
    # by the workspace, because a clone of a linked worktree would otherwise
    # write the exclusion into the canonical repository it came from.
    scratch.ensure_exclude(target, root=workspace_dir)
    return True
