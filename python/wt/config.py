"""Environment-derived settings.

Everything configurable lives here so a caller can build a Config by hand and
drive the rest of the package against a temporary root.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_NAMESPACE = "feature"
DEFAULT_AGENT = "claude"
DEFAULT_MAX_AGENTS = 4
DEFAULT_FORGE = "https://github.com"
KNOWN_AGENTS = ("claude", "codex")


@dataclass(frozen=True)
class Config:
    """Where workspaces live and how agents are launched."""

    root: Path
    namespace: str = DEFAULT_NAMESPACE
    agent: str = DEFAULT_AGENT
    max_agents: int = DEFAULT_MAX_AGENTS
    forge: str = DEFAULT_FORGE
    state_dir: Path = Path.home() / ".local" / "state" / "wt"
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
        if max_agents < 0:
            max_agents = 0

        return cls(
            root=Path(root).expanduser(),
            namespace=environ.get("WT_NAMESPACE") or DEFAULT_NAMESPACE,
            agent=environ.get("WT_AGENT") or DEFAULT_AGENT,
            max_agents=max_agents,
            forge=environ.get("WT_FORGE") or DEFAULT_FORGE,
            state_dir=Path(state_root).expanduser() / "wt",
            max_agents_raw=raw_max,
        )

    @property
    def agents_dir(self) -> Path:
        return self.state_dir / "agents"
