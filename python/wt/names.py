"""Workspace-name normalisation and path safety.

Names become directories, so they are held to a conservative charset and
anything that could escape the workspace root is refused here rather than at
the filesystem. The slug also becomes part of a Git branch name, so the
reference rules are enforced here too.
"""

import os
import re
from pathlib import Path

from .errors import WtError

SAFE_COMPONENT = re.compile(r"\A[A-Za-z0-9._-]+\Z")
RESERVED = frozenset({".", ".."})


def is_safe_component(value: str) -> bool:
    """True when value is usable as a path component and in a branch name."""
    if value in RESERVED or value.startswith("-"):
        return False
    # Git refuses a reference component that starts or ends with a dot or
    # ends in .lock, and every slug becomes one.
    if value.startswith(".") or value.endswith(".") or value.endswith(".lock"):
        return False
    return bool(SAFE_COMPONENT.match(value))


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
