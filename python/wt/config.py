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
DEFAULT_MAX_AGENTS = 4
# A slot costs a lock file and a probe, so the limit is a small number by
# nature. Bounding it keeps one fat-fingered digit from turning every
# destructive verb into an unbounded walk.
MAX_AGENTS_CEILING = 1024
DEFAULT_FORGE = "https://github.com"
KNOWN_AGENTS = ("claude", "codex", "droid")


@dataclass(frozen=True)
class Config:
    """Where workspaces live and how agents are launched."""

    root: Path
    # A bare workspace name needs a project; there is no sensible default one,
    # so it stays None until WT_PROJECT names it.
    project: str | None = None
    branch_prefix: str = DEFAULT_BRANCH_PREFIX
    agent: str = DEFAULT_AGENT
    max_agents: int = DEFAULT_MAX_AGENTS
    forge: str = DEFAULT_FORGE
    # None means "derive from HOME when asked". Reading the home directory at
    # class-definition time would make importing this module depend on the
    # environment, and would quietly point a hand-built Config at the real
    # home's lock files instead of the root it was given.
    state_dir: Path | None = None
    # Kept verbatim so `wt check` can report an unusable value instead of
    # failing to build a Config at all.
    max_agents_raw: str = str(DEFAULT_MAX_AGENTS)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        environ = os.environ if env is None else env
        home = Path(environ.get("HOME") or Path.home())

        root = environ.get("WT_ROOT") or str(home / "git" / "worktrees")
        state_root = environ.get("XDG_STATE_HOME") or str(
            home / ".local" / "state"
        )
        raw_max = environ.get("WT_MAX_AGENTS") or str(DEFAULT_MAX_AGENTS)
        try:
            max_agents = int(raw_max)
        except ValueError:
            max_agents = 0
        if max_agents < 0 or max_agents > MAX_AGENTS_CEILING:
            max_agents = 0

        return cls(
            root=Path(root).expanduser(),
            project=environ.get("WT_PROJECT") or None,
            branch_prefix=environ.get("WT_BRANCH_PREFIX")
            or DEFAULT_BRANCH_PREFIX,
            agent=environ.get("WT_AGENT") or DEFAULT_AGENT,
            max_agents=max_agents,
            forge=environ.get("WT_FORGE") or DEFAULT_FORGE,
            state_dir=Path(state_root).expanduser() / "wt",
            max_agents_raw=raw_max,
        )

    @property
    def agents_dir(self) -> Path:
        state = self.state_dir
        if state is None:
            state = Path.home() / ".local" / "state" / "wt"
        return state / "agents"

    @property
    def max_agents_valid(self) -> bool:
        """False when WT_MAX_AGENTS was not a positive integer.

        An unusable limit is not "no slots to check": every consumer that
        could destroy something must refuse outright, because a survey sized
        from a value nobody understood would report an empty pool and let a
        sweep delete the workspace a live agent is holding.
        """
        try:
            limit = int(self.max_agents_raw)
        except ValueError:
            return False
        # A Config assembled by hand carries the default raw string, so the
        # parsed limit has to agree before the value counts as usable.
        return limit > 0 and self.max_agents > 0
