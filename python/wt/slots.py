"""The flock-backed registry of running agents.

Each agent holds one slot, which is a lock file. The holder keeps the
descriptor open, and the kernel releases the lock when the process dies, so a
crashed or killed agent never leaves a slot behind and there is no stale state
to prune.

The descriptor is marked inheritable, which is what lets `wt` hand the slot to
the agent it execs: the lock lives on the open file description, so it
survives the exec and is held for exactly as long as the agent runs.

Nothing here caps how many agents may run. The registry exists so the verbs
that delete things can tell which workspaces are occupied; how many agents to
run is decided by how many you start.
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

    def field(self, name: str) -> str:
        """One `key=value` from the info line, or empty when it has none."""
        for token in self.info.split():
            key, separator, value = token.partition("=")
            if separator and key == name:
                return value
        return ""

    @property
    def workspace(self) -> str:
        """The workspace this slot was taken for, or empty when unnamed."""
        return self.field("workspace")

    @property
    def relay(self) -> str:
        """The relay run and turn this slot is working, when it is one."""
        run, turn = self.field("run"), self.field("turn")
        return f"{run} turn {turn}" if run and turn else ""


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
    """Every agent slot below one directory."""

    def __init__(self, agents_dir: Path) -> None:
        self.agents_dir = agents_dir
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
        """The highest slot worth probing, from the lock files on disk.

        A directory that is not there yet holds no locks, so nothing is
        running. A directory that exists and cannot be read is a different
        fact: it says nothing about who is running, and reading it as an
        empty pool is what would let a sweep delete a workspace a live agent
        is holding. So it raises instead.
        """
        highest = 0
        try:
            entries = list(self.agents_dir.iterdir())
        except FileNotFoundError:
            return highest
        except OSError as error:
            raise WtError(
                f"cannot read the agent slots in {self.agents_dir}: {error}"
            ) from error
        for entry in entries:
            match = _LOCK_NAME.match(entry.name)
            if match:
                highest = max(highest, min(int(match.group(1)), _MAX_SLOT))
        return highest

    def acquire(self, agent: str, workspace: str) -> int:
        """Take the lowest free slot.

        The lowest rather than the next one up, so the lock files a machine
        accumulates stay as few as the agents that ran at once, rather than
        one per launch forever.
        """
        if self._held_fd is not None:
            raise WtError("this pool already holds an agent slot")
        self.ensure_dir()
        for index in range(1, _MAX_SLOT + 1):
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
        raise WtError(
            f"no agent slot could be taken in {self.agents_dir}: "
            f"{_MAX_SLOT} are in use or unusable"
        )

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

    def describe(
        self,
        agent: str,
        workspace: str,
        run: str = "",
        turn: str = "",
    ) -> None:
        """Say more about the slot this pool holds than acquiring could.

        A relay turn's run and turn number are only known after the brief
        has been read, which happens after the slot is taken; without this
        `wt agents` could name the workspace but not which turn of which
        run is being worked in it.
        """
        if self._held_index is None:
            raise WtError("this pool holds no agent slot to describe")
        self._describe(self._held_index, agent, workspace, run, turn)

    def _describe(
        self,
        index: int,
        agent: str,
        workspace: str,
        run: str = "",
        turn: str = "",
    ) -> None:
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # Absent rather than empty: a reader splits on whitespace, and
        # `run=` would otherwise read as a run whose name is nothing.
        relay = f" run={run} turn={turn}" if run and turn else ""
        try:
            self.info_path(index).write_text(
                f"agent={agent} workspace={workspace}{relay} "
                f"pid={os.getpid()} started={started}\n",
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

    def running(self) -> list["SlotState"]:
        """Every slot a live agent is holding, in order."""
        return [state for state in self.survey() if state.busy]

    def survey(self) -> list[SlotState]:
        """The state of every slot a lock file exists for, in order."""
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
