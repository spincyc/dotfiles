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
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import WtError

_LOCK_NAME = re.compile(r"slot-(\d+)\.lock\Z")


# A slot index is bounded so one absurd filename cannot make every
# destructive verb stat its way to a halt: the survey walks 1..ceiling.
_MAX_SLOT = 1024


@dataclass(frozen=True)
class SlotState:
    """One slot as `wt agents` reports it."""

    index: int
    busy: bool
    info: str = ""

    @property
    def workspace(self) -> str:
        """The workspace this slot was taken for, or empty when unnamed."""
        for token in self.info.split():
            key, separator, value = token.partition("=")
            if separator and key == "workspace":
                return value
        return ""


@dataclass(frozen=True)
class BusyAgents:
    """Which workspaces hold a running agent, and whether one is unknown."""

    workspaces: frozenset[str]
    unnamed: bool = False

    def holds(self, workspace: str) -> bool:
        """True when an agent may be running in this workspace.

        A busy slot whose info file is missing or unreadable makes this true
        of every workspace: the one it holds cannot be identified, and
        guessing wrong deletes the tree an agent is working in.
        """
        return self.unnamed or workspace in self.workspaces


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

    def ceiling(self) -> int:
        """The highest slot worth probing.

        A slot taken when the limit was higher is still held by a live agent,
        so a sweep that only looked at the current limit would delete the
        workspace out from under it. Never shrink below what exists on disk.
        """
        highest = self.size
        try:
            entries = list(self.agents_dir.iterdir())
        except OSError:
            # An unreadable directory says nothing about who is running; the
            # configured size is all this can honestly claim.
            return highest
        for entry in entries:
            match = _LOCK_NAME.match(entry.name)
            if match:
                highest = max(highest, min(int(match.group(1)), _MAX_SLOT))
        return highest

    def acquire(self, agent: str, workspace: str) -> int | None:
        """Take the first free slot, or None when every slot is busy."""
        if self._held_fd is not None:
            raise WtError("this pool already holds an agent slot")
        self.ensure_dir()
        for index in range(1, self.size + 1):
            try:
                fd = os.open(
                    self.lock_path(index),
                    os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                    0o600,
                )
            except OSError:
                # One lock file we cannot open is one slot lost, not a failed
                # launch: treat it exactly as `is_free` does and try the next.
                continue
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

    def release(self) -> None:
        """Drop the held slot and remove its info file.

        The exec path never calls this — the kernel does it. A script that
        acquires and keeps running needs it, and a stale info file would
        otherwise name a workspace whose agent is long gone: wrong info, unlike
        missing info, defeats the busy guard with no fail-safe behind it.
        """
        index, fd = self._held_index, self._held_fd
        self._held_index, self._held_fd = None, None
        if index is not None:
            self._forget(index)
        if fd is not None:
            # Closing the descriptor is what releases the kernel's lock.
            os.close(fd)

    def __enter__(self) -> "SlotPool":
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    def _describe(self, index: int, agent: str, workspace: str) -> None:
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            self.info_path(index).write_text(
                f"agent={agent} workspace={workspace} pid={os.getpid()} "
                f"started={started}\n",
                encoding="utf-8",
            )
        except OSError:
            # A slot we hold but cannot name must read as unnamed rather than
            # keep whatever a previous holder left behind: an unidentifiable
            # busy slot protects every workspace, a misnamed one protects the
            # wrong one.
            self._forget(index)

    def _forget(self, index: int) -> None:
        try:
            self.info_path(index).unlink(missing_ok=True)
        except OSError:
            pass

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

    def busy_agents(self) -> "BusyAgents":
        """Which workspaces are occupied, from one pass over the slots."""
        states = self.survey()
        return BusyAgents(
            workspaces=frozenset(
                state.workspace
                for state in states
                if state.busy and state.workspace
            ),
            unnamed=any(
                state.busy and not state.workspace for state in states
            ),
        )

    def survey(self) -> list[SlotState]:
        """The state of every slot, in order."""
        self.ensure_dir()
        states: list[SlotState] = []
        for index in range(1, self.ceiling() + 1):
            if self.is_free(index):
                states.append(SlotState(index=index, busy=False))
                continue
            try:
                text = self.info_path(index).read_text(encoding="utf-8")
                info = text.strip()
            except OSError:
                info = ""
            states.append(SlotState(index=index, busy=True, info=info))
        return states
