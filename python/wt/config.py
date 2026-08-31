"""Environment-derived settings.

Everything configurable lives here so a caller can build a Config by hand and
drive the rest of the package against a temporary root.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BRANCH_PREFIX = "feature"
DEFAULT_AGENT = "claude"
DEFAULT_FORGE = "https://github.com"
KNOWN_AGENTS = ("claude", "codex", "droid")
# The agent registry lives under the workspace root, so everything `wt`
# creates is below the root it was pointed at, and two roots keep separate
# registries without a second variable to agree about. The name is dotted
# because the listing walks the root for projects and steps over dotted
# entries.
AGENTS_DIRNAME = ".agents"


@dataclass(frozen=True)
class Config:
    """Where workspaces live and how agents are launched."""

    root: Path
    # A bare workspace name needs a project; there is no sensible default one,
    # so it stays None until WT_PROJECT names it.
    project: str | None = None
    branch_prefix: str = DEFAULT_BRANCH_PREFIX
    agent: str = DEFAULT_AGENT
    forge: str = DEFAULT_FORGE

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        environ = os.environ if env is None else env
        home = Path(environ.get("HOME") or Path.home())

        root = environ.get("WT_ROOT") or str(home / "git" / "worktrees")

        return cls(
            root=Path(root).expanduser(),
            project=environ.get("WT_PROJECT") or None,
            branch_prefix=environ.get("WT_BRANCH_PREFIX")
            or DEFAULT_BRANCH_PREFIX,
            agent=environ.get("WT_AGENT") or DEFAULT_AGENT,
            forge=environ.get("WT_FORGE") or DEFAULT_FORGE,
        )

    @property
    def agents_dir(self) -> Path:
        return self.root / AGENTS_DIRNAME
