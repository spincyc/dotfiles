"""The per-workspace agent guidance documents.

`AGENTS.md` is what tells an agent that clones belong here, owner-prefixed.
The Claude and Gemini files defer to it, mirroring the bootstrap pattern the
dotfiles repository already uses.
"""

from pathlib import Path

CANONICAL = "AGENTS.md"
POINTERS = ("CLAUDE.md", "GEMINI.md")

_POINTER = """# Agent instructions

Read and follow [`AGENTS.md`](AGENTS.md), the workspace guidance for this
directory.
"""


def render(workspace: str, branch: str) -> str:
    """The AGENTS.md text for one workspace."""
    return f"""# Workspace {workspace}

This directory is a `wt` agent workspace, not a repository. It holds the
clones one line of work needs, side by side. Its name is
`<project>/<slug>`: the project it belongs to, and the slug of this one line
of work.

## Commit to `{branch}`, in every repository

Every clone here works on `{branch}`, the workspace branch. `wt clone` puts
each new clone on it, and it tracks the branch the clone arrived on until
you publish it.

- Never commit to `main`, `master`, or any other default branch here, and do
  not rename or switch the workspace branch.
- Publish with `git push -u origin {branch}`. A bare `git push` deliberately
  refuses while the branch still tracks the default branch; that refusal is
  the guard against pushing this work to `main`.
- A clone that was already here keeps the branch it is on. `wt status` shows
  every branch, and `wt check` warns about a repository that has left
  `{branch}`.

## Always clone into this directory, owner-prefixed

Every repository lives at `<owner>/<repo>` below this directory, for example
`spincyc/telos`. Create them with:

    wt clone {workspace} spincyc/telos

or, from this directory:

    mkdir -p spincyc && git clone <url> spincyc/telos
    git -C spincyc/telos checkout -b {branch}

Rules:

- Never clone into the workspace root itself, and never nest a clone inside
  another clone.
- Never work in, commit to, or reconfigure the canonical clones under
  `~/git`. The clones here are independent; changes here do not reach them.
- Keep unrelated work out of this workspace. One workspace, one line of work.
- Everything below this directory is disposable. `wt rm {workspace}` deletes
  it once no repository holds uncommitted, unpushed, or stashed work, so
  leave nothing here that is not committed and pushed.

## No work ledger here

This workspace keeps no local work state. Do not use `aiq` in it: no
ingesting, claiming, enqueuing, settling, or journal initialization, and no
treating the absence of work state as a defect. Do not use `tmt` here either:
record no candidates and scaffold no registry. `wt` exports `AIQ_DISABLE`, so
the installed hooks are already inert; never work around that.

A cloned repository inside this workspace keeps its own contracts. If it has
a `tmt.json`, tool making applies to that repository normally.

## Which instructions govern a change

The active repository is whichever clone you are changing. That repository's
own instructions govern work inside it. This file only adds the workspace
layout rules above; it never overrides repository or personal guidance.

## Useful commands

    wt ls                                # workspaces and their repos
    wt status {workspace}
    wt git {workspace} -- fetch --prune
"""


def documents(workspace: str, branch: str) -> dict[str, str]:
    """Every guidance file a workspace gets, keyed by filename."""
    files = {CANONICAL: render(workspace, branch)}
    files.update({name: _POINTER for name in POINTERS})
    return files


def write(
    directory: Path, workspace: str, branch: str, force: bool = False
) -> bool:
    """Write the guidance unless it is already there. True when written."""
    if (directory / CANONICAL).exists() and not force:
        return False
    for name, text in documents(workspace, branch).items():
        (directory / name).write_text(text, encoding="utf-8")
    return True
