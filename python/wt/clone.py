"""Clone-spec parsing and cloning.

Whatever form the spec takes, the clone lands at ``<owner>/<repo>`` inside the
workspace, on the workspace branch. Bare ``owner/repo`` specs go through gh
when it is installed, so private repositories work without a separate
credential setup.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import branches, scratch
from .errors import WtError
from .names import is_safe_component


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


def parse(spec: str) -> CloneSpec:
    """Read owner/repo, https://host/owner/repo(.git) or git@host:owner/repo."""
    url: str | None = None
    if "://" in spec:
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
        return False
    if target.exists():
        raise WtError(
            f"clone target exists and is not a repository: {target}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    if spec.url is None and shutil.which("gh"):
        command = ["gh", "repo", "clone", spec.name, str(target)]
    else:
        command = ["git", "clone", "--", spec.clone_url(forge), str(target)]

    if subprocess.run(command, check=False).returncode != 0:
        raise WtError(f"clone failed: {spec.name}")
    if not branches.checkout(target, branch):
        raise WtError(
            f"cloned {spec.name}, but it would not go on branch {branch}"
        )
    # Local, never committed: transient files go under .scratch here, and a
    # clone that hides them cannot be mistaken for one holding work.
    scratch.ensure_exclude(target)
    return True
