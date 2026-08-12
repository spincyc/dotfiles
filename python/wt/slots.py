"""The flock-backed concurrent-agent limit.

Each slot is a lock file. The holder keeps the descriptor open, and the kernel
releases the lock when the process dies, so a crashed or killed agent never
leaves a slot behind and there is no stale state to prune.

The descriptor is marked inheritable, which is what lets `wt` hand the slot to
the agent it execs: the lock lives on the open file description, so it
survives the exec and is held for exactly as long as the agent runs.
"""

import fcntl
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SlotState:
    """One slot as `wt agents` reports it."""

    index: int
    busy: bool
    info: str = ""


class SlotPool:
    """A fixed number of agent slots below one directory."""

    def __init__(self, agents_dir: Path, size: int) -> None:
        self.agents_dir = agents_dir
        self.size = size
        self._held_fd: int | None = None
        self._held_index: int | None = None

    def lock_path(self, index: int) -> Path:
        return self.agents_dir / f"slot-{index}.lock"

    def info_path(self, index: int) -> Path:
        return self.agents_dir / f"slot-{index}.info"

    def ensure_dir(self) -> None:
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.agents_dir.chmod(0o700)

    def acquire(self, agent: str, workspace: str) -> int | None:
        """Take the first free slot, or None when every slot is busy."""
        self.ensure_dir()
        for index in range(1, self.size + 1):
            fd = os.open(
                self.lock_path(index),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                continue
            # Survive the exec into the agent, and stay open for its lifetime.
            os.set_inheritable(fd, True)
            self._held_fd = fd
            self._held_index = index
            self._describe(index, agent, workspace)
            return index
        return None

    def _describe(self, index: int, agent: str, workspace: str) -> None:
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.info_path(index).write_text(
            f"agent={agent} workspace={workspace} pid={os.getpid()} "
            f"started={started}\n",
            encoding="utf-8",
        )

    def is_free(self, index: int) -> bool:
        """Probe one slot without disturbing whoever holds it."""
        path = self.lock_path(index)
        if not path.exists():
            return True
        try:
            fd = os.open(path, os.O_WRONLY | os.O_APPEND)
        except OSError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        finally:
            # Closing drops the probe's lock; the holder's is untouched.
            os.close(fd)
        return True

    def survey(self) -> list[SlotState]:
        """The state of every slot, in order."""
        self.ensure_dir()
        states: list[SlotState] = []
        for index in range(1, self.size + 1):
            if self.is_free(index):
                states.append(SlotState(index=index, busy=False))
                continue
            try:
                info = self.info_path(index).read_text(encoding="utf-8").strip()
            except OSError:
                info = ""
            states.append(SlotState(index=index, busy=True, info=info))
        return states
