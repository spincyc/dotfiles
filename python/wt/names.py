"""Workspace-name normalisation and path safety.

Names become directories, so they are held to a conservative charset and
anything that could escape the workspace root is refused here rather than at
the filesystem. The slug also becomes part of a Git branch name, so the
reference rules are enforced here too.
"""

import os
import re
from pathlib import Path

from . import gitcmd
from .errors import WtError

SAFE_COMPONENT = re.compile(r"\A[A-Za-z0-9._-]+\Z")
RESERVED = frozenset({".", ".."})
# What Git will not have anywhere in a reference name, quite apart from the
# charset a workspace name is already held to.
_REF_FORBIDDEN = frozenset(
    " ~^:?*[\\" + "".join(chr(code) for code in range(0x20)) + chr(0x7F)
)


def is_safe_component(value: str) -> bool:
    """True when value is usable as a path component and in a branch name."""
    if value in RESERVED or value.startswith("-"):
        return False
    # Git refuses a reference component that starts or ends with a dot or
    # ends in .lock, and every slug becomes one.
    if value.startswith(".") or value.endswith(".") or value.endswith(".lock"):
        return False
    return bool(SAFE_COMPONENT.match(value))


def valid_branch(name: str) -> bool:
    """True when name is usable as a Git branch.

    Asks Git whenever it can, because the reference rules are Git's and a
    copy of them here would drift. The local rules stand in only when git is
    not installed, and are deliberately the stricter reading: refusing a
    workable name costs a rename, accepting an unusable one costs a
    workspace that nothing can be checked out into.
    """
    if not name or name.startswith("-"):
        # An argument beginning with a dash never reaches git as a name.
        return False
    if gitcmd.available():
        checked = ["check-ref-format", "--branch", name]
        return gitcmd.run(checked, quiet=True) == 0
    if name.startswith("/") or name.endswith("/") or name.endswith("."):
        return False
    if ".." in name or "@{" in name or name == "@":
        return False
    if any(char in _REF_FORBIDDEN for char in name):
        return False
    return all(
        part and not part.startswith(".") and not part.endswith(".lock")
        for part in name.split("/")
    )


def normalize_workspace(value: str, project: str | None) -> str:
    """Turn "slug" or "project/slug" into "project/slug"."""
    trimmed = value.rstrip("/")
    parts = trimmed.split("/")
    if len(parts) == 1:
        if not project:
            raise WtError(
                f"name the project: <project>/{trimmed} "
                f"(or set WT_PROJECT)"
            )
        parts = [project, parts[0]]
    if len(parts) != 2 or not all(is_safe_component(part) for part in parts):
        raise WtError(f"not a usable workspace name: {value}")
    # Whether the name makes a usable *branch* is asked at creation, not
    # here: this function also resolves workspaces that already exist, and a
    # rule applied on the way in would strand any directory that predates
    # it — `wt ls` would show it while every named verb refused it.
    return "/".join(parts)


def split_workspace(name: str) -> tuple[str, str]:
    """Split a normalised workspace name into project and slug."""
    project, _, slug = name.partition("/")
    return project, slug


def workspace_from_path(path: Path, root: Path) -> str | None:
    """Return the workspace containing path, or None when it is outside."""
    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = Path(path).resolve(strict=True)
    except OSError:
        return None
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError:
        return None
    parts = relative.parts
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def assert_owned_directory(path: Path) -> None:
    """Refuse symlinked, foreign, or non-directory paths before writing."""
    if path.is_symlink():
        raise WtError(f"path must not be a symlink: {path}")
    if not path.is_dir():
        raise WtError(f"not a directory: {path}")
    if path.stat().st_uid != os.getuid():
        raise WtError(f"directory is not owned by the current user: {path}")
