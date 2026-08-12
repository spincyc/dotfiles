"""Agent workspaces under ~/git/worktrees.

A workspace is a plain directory holding several independent clones, each
parked at ``<owner>/<repo>``. The workspace is not a repository itself and is
never a ``git worktree`` of a canonical clone under ``~/git``.

The modules are meant to be reused on their own:

``wt.config``      environment-derived settings
``wt.errors``      the user-facing error types
``wt.names``       workspace-name normalisation and path safety
``wt.gitcmd``      a thin ``git`` runner
``wt.repos``       discovery, status, and the unsaved-work oracle
``wt.branches``    the workspace branch and what a clone tracks
``wt.clone``       clone-spec parsing and cloning
``wt.guidance``    the per-workspace agent guidance documents
``wt.scratch``     the ``.scratch`` convention and its local Git exclusion
``wt.workspaces``  workspace creation, listing, resolution, and the gate
                   every destructive verb passes through
``wt.slots``       the flock-backed concurrent-agent limit
``wt.checks``      the environment and layout sanity check
``wt.cli``         the ``wt`` command line
"""

__all__ = [
    "branches",
    "checks",
    "cli",
    "clone",
    "config",
    "errors",
    "gitcmd",
    "guidance",
    "names",
    "repos",
    "scratch",
    "slots",
    "workspaces",
]
