"""Continuing the agent session a workspace already had.

A workspace is one line of work, so running the agent in it again almost
always means carrying on rather than starting over. Resuming is the one
place `wt` has to know an agent's own flags: there is no shared spelling
for *continue where you left off*, and an agent asked to continue a session
it never had reports that instead of starting one. So `wt` notes which
agents have run in a workspace and offers each of them the incantation it
understands; an agent named in neither the record nor the table below is
launched fresh, because guessing a flag wrong costs a session that will not
start.

The record is a convenience and never work: losing it costs a resume, so
every failure here is answered with "start fresh" rather than an error.
"""

from pathlib import Path

RECORD = ".wt-agents"

# What goes in front of an agent's own arguments to continue its last
# session here, and whether that form can also carry an opening prompt.
#
# `claude --continue` takes a trailing prompt like any other claude launch.
# The other two cannot: `codex resume` reads its first positional as
# `[SESSION_ID]`, and droid's `-r, --resume [sessionId]` takes an optional
# value, so in both a trailing prompt is read as a session to resume rather
# than as something to say.
RESUME: dict[str, tuple[tuple[str, ...], bool]] = {
    "claude": (("--continue",), True),
    "codex": (("resume", "--last"), False),
    "droid": (("--resume",), False),
}


def previous(workspace_dir: Path) -> frozenset[str]:
    """The agents that have been launched in this workspace before."""
    try:
        text = (workspace_dir / RECORD).read_text(encoding="utf-8")
    except OSError:
        # No record, or one that cannot be read: both mean the same thing
        # here, which is that nothing is known to resume.
        return frozenset()
    return frozenset(
        line.strip() for line in text.splitlines() if line.strip()
    )


def record(workspace_dir: Path, agent: str) -> None:
    """Note that agent has run here, so a later launch can resume it."""
    known = previous(workspace_dir)
    if agent in known:
        return
    try:
        (workspace_dir / RECORD).write_text(
            "".join(f"{name}\n" for name in sorted(known | {agent})),
            encoding="utf-8",
        )
    except OSError:
        pass


def resumable(workspace_dir: Path, agent: str) -> bool:
    """True when this agent has a session here and a way to continue it."""
    return agent in RESUME and agent in previous(workspace_dir)


def arguments(agent: str) -> tuple[str, ...]:
    """What asks this agent to continue, assuming there is something to."""
    return RESUME[agent][0] if agent in RESUME else ()


def carries_prompt(agent: str) -> bool:
    """True when this agent's resume form can also open with a prompt."""
    return RESUME[agent][1] if agent in RESUME else False
