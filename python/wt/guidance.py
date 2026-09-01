"""The per-workspace agent guidance documents.

`AGENTS.md` is what tells an agent that clones belong here, owner-prefixed.
The Claude and Gemini files defer to it, mirroring the bootstrap pattern the
dotfiles repository already uses.
"""

from pathlib import Path

CANONICAL = "AGENTS.md"
POINTERS = ("CLAUDE.md", "GEMINI.md")
FILENAMES = frozenset({CANONICAL, *POINTERS})

_POINTER = """# Agent instructions

Read and follow [`AGENTS.md`](AGENTS.md), the workspace guidance for this
directory.
"""


def render(workspace: str, branch: str) -> str:
    """The AGENTS.md text for one workspace."""
    return f"""# Workspace {workspace}

This directory is a `wt` agent workspace, not a repository. It holds the
clones one line of work needs, side by side. Its name is
`<project>/<slug>[/<child>...]`: the project it belongs to, followed by the
complete slug stack for this one line of work.

## Keep replay stacks in separate leaves

Intermediate components group related work; only the final component is a
workspace leaf. For several replays of one high-level vision, use sibling
leaves such as `<project>/<vision>/replay-1` and
`<project>/<vision>/replay-2`. Each leaf has its own directory, agent slot,
and branch, so one replay cannot silently inherit another replay's files or
commits. Do not put work directly in the intermediate `<project>/<vision>`
group.

`wt` refuses to launch an intermediate group as a workspace, and it refuses
to add children below a path that is already a workspace: Git cannot keep a
branch and branches nested below that same branch ref. If the high-level
vision needs a baseline pass of its own, make `baseline` another leaf beside
the replay leaves.

Existing leaves can be selected in `wt` commands by their full workspace
name, full branch, slug stack without the project, unique final slug, or an
unambiguous prefix of each component. Ambiguous selectors are refused and
list their candidates. Prefer `$WT_WORKSPACE` and `$WT_BRANCH` in scripts;
they always carry the canonical values for this leaf.

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
  it once no repository holds uncommitted, unpushed, or stashed work, and
  `wt sweep` clears every workspace that has reached that state. Leave
  nothing here that is not committed and pushed.

## Always put transient items under `.scratch`

Everything you create that is not going into a commit belongs under a
`.scratch` directory: notes, plans, logs, scratch scripts, downloaded
samples, experiment output, anything else you would otherwise drop beside
the code. Two places, and no others:

- `.scratch` at the top of this workspace, for anything that is not about
  one repository.
- `<owner>/<repo>/.scratch` at the top of a clone, for anything that is.

Every clone made by `wt clone` excludes `.scratch/` in its
`.git/info/exclude`, so scratch files there never dirty the repository and
never reach a commit by accident. A clone you made by hand has no such
exclusion until a real `wt tidy` gives it one; add the line yourself if you
want it sooner.

Anything you leave outside those two places holds this workspace open. An
untracked file beside the code is indistinguishable from work you forgot to
commit, and a stray file at the top of this directory is something `wt` can
make no sense of; `wt sweep` keeps the workspace in either case.

`wt tidy` deletes both `.scratch` directories and everything the clones
ignore, without asking — including ignored build output such as a
virtualenv or `node_modules`. `wt tidy --dry-run` reports and deletes
nothing. Anything you leave in `.scratch` is gone at the next tidy.

## No work ledger here

This workspace keeps no local work state. Do not use `aiq` in it: no
ingesting, claiming, enqueuing, settling, or journal initialization, and no
treating the absence of work state as a defect. Do not use `tmt` here either:
record no candidates and scaffold no registry. `wt` exports `AIQ_DISABLE=1`,
which switches the installed hooks off — but only for an aiq newer than
`0.3.0a1`; an older one ignores the variable and goes on capturing. The rule
above holds either way; never work around it.

A cloned repository inside this workspace keeps its own contracts. If it has
a `tmt.json`, tool making applies to that repository normally.

## What `wt` sets in this session

`wt` exports five variables into the agent it launches:

- `WT_WORKSPACE` — this workspace's name, `{workspace}`.
- `WT_WORKSPACE_DIR` — its absolute path, the directory you started in.
- `WT_BRANCH` — the workspace branch, `{branch}`. Publish with
  `git push -u origin "$WT_BRANCH"` rather than retyping the name.
- `WT_AGENT_SLOT` — which agent slot this session holds; `wt agents` lists
  every agent running right now.
- `AIQ_DISABLE` — the work-ledger switch described above.

They exist only in this session; a shell opened anywhere else has none of
them.

## Which instructions govern a change

The active repository is whichever clone you are changing. That repository's
own instructions govern work inside it. This file only adds the workspace
layout rules above; it never overrides repository or personal guidance.

## Useful commands

    wt ls                                # workspaces and their repos
    wt status {workspace}
    wt git {workspace} -- fetch --prune
    wt tidy --dry-run                    # what tidy would delete, and where
    wt tidy                              # delete it, ignored build output too
"""


def documents(workspace: str, branch: str) -> dict[str, str]:
    """Every guidance file a workspace gets, keyed by filename."""
    files = {CANONICAL: render(workspace, branch)}
    files.update({name: _POINTER for name in POINTERS})
    return files


def write(
    directory: Path, workspace: str, branch: str, force: bool = False
) -> bool:
    """Write each guidance file that is missing. True when any was written.

    Every name is probed, not just `AGENTS.md`: judging the whole set by one
    of them left a deleted `CLAUDE.md` gone for good, since the only way back
    was `wt new --force`, which also rewrites the file the user annotated.
    """
    written = False
    for name, text in documents(workspace, branch).items():
        path = directory / name
        if path.is_symlink():
            # Writing through a link would put this workspace's guidance
            # wherever the link points, which need not be in the workspace.
            if not force:
                continue
            path.unlink()
        elif path.exists() and not force:
            continue
        path.write_text(text, encoding="utf-8")
        written = True
    return written
