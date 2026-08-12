"""The `wt` command line.

Argument parsing and every line of output live here; the other modules stay
importable without printing anything.
"""

import os
import shutil
import sys

from . import checks, clone, gitcmd, repos, slots, workspaces
from .config import KNOWN_AGENTS, Config
from .errors import UnsavedWorkError, UsageError, WtError

USAGE = """\
Usage: wt [claude|codex] [<project>/]<slug> [agent-args...]
       wt <verb> [<workspace>] [args...]

Launch:
  wt claude telos/agent-sync      Create or reuse the workspace, then run
  wt codex telos/agent-sync       the agent with it as the working directory
  wt telos/agent-sync             Use $WT_AGENT (default claude)
  wt agent-sync                   A bare slug takes $WT_PROJECT

A workspace is <project>/<slug>, and every repository cloned into it works on
the branch feature/<slug> ($WT_BRANCH_PREFIX/<slug>).

Verbs:
  ls                              List workspaces and the repos they hold
  new [--force] [<workspace>]     Create a workspace, do not launch an agent
  path [<workspace>]              Print a workspace directory
  pwd                             Print the root of the workspace you are in
  clone [<workspace>] <repo>...   Clone owner/repo or a URL to <owner>/<repo>,
                                  on the workspace branch
  branch [<workspace>]            Print the workspace branch
  git [<workspace>] [--] <args>   Run git in every repo of the workspace
  status [<workspace>]            Per-repo branch, cleanliness and tracking
  fetch [<workspace>]             git fetch --prune in every repo
  pull [<workspace>]              git pull --ff-only in every repo
  agents                          Show occupied and free agent slots
  check                           Sanity-check the environment and layout
  tidy [--dry-run] [<workspace>]  Delete .scratch and Git-ignored files
  clean [--dry-run] [<workspace>] Remove workspaces whose work is all pushed
  rm [--force] <workspace>        Remove a workspace holding no unsaved work
  help                            Show this message

Transient files belong under .scratch, at the top of a workspace or of a
clone; wt tidy deletes those and whatever the clones ignore. Given no
workspace, wt clean sweeps them all, keeping any that holds unsaved work,
runs an agent, or contains the current directory. Both take -n for --dry-run.

A verb reads its first argument as the workspace when that workspace already
exists, or when the current directory is not inside one. Otherwise the
current workspace is used and every argument belongs to the verb.

wt never changes the calling shell's directory; use cd "$(wt path NAME)", or
cd "$(wt pwd)" to return to the top of the workspace you are already in.

Environment:
  WT_ROOT            Workspace root           (default ~/git/worktrees)
  WT_PROJECT         Project for a bare slug  (no default)
  WT_BRANCH_PREFIX   Workspace branch prefix  (default feature)
  WT_AGENT           Agent for bare launches  (default claude)
  WT_MAX_AGENTS      Concurrent agent slots   (default 4)
  WT_FORGE           Base URL for owner/repo  (default https://github.com)\
"""

REPO_LINE = "{name:<34} {branch:<22} {state:<5} {tracking}"


def _take_force(args: list[str]) -> tuple[bool, list[str]]:
    if args and args[0] == "--force":
        return True, args[1:]
    return False, args


def _take_dry_run(args: list[str]) -> tuple[bool, list[str]]:
    """Read -n or --dry-run from wherever in the arguments it was typed."""
    kept = [arg for arg in args if arg not in ("-n", "--dry-run")]
    return len(kept) != len(args), kept


def _print_repo(status: repos.RepoStatus, indent: str = "") -> None:
    print(
        indent
        + REPO_LINE.format(
            name=status.name,
            branch=status.branch,
            state=status.state,
            tracking=status.tracking,
        ).rstrip()
    )


def _pool(config: Config) -> slots.SlotPool:
    return slots.SlotPool(config.agents_dir, config.max_agents)


def _report_agents(config: Config, stream=sys.stdout) -> int:
    pool = _pool(config)
    busy = 0
    for state in pool.survey():
        if state.busy:
            busy += 1
            suffix = f"   {state.info}" if state.info else ""
            print(f"slot {state.index:<3} busy{suffix}", file=stream)
        else:
            print(f"slot {state.index:<3} free", file=stream)
    print(f"{busy} of {config.max_agents} slots in use", file=stream)
    return busy


def cmd_ls(config: Config, args: list[str]) -> int:
    if args:
        raise UsageError("ls takes no arguments")
    found = workspaces.listing(config)
    if not found:
        print(f"No workspaces under {config.root}")
        return 0
    for workspace in found:
        print(workspace.name)
        statuses = workspace.statuses()
        if not statuses:
            print("  (no repositories)")
        for status in statuses:
            _print_repo(status, indent="  ")
    return 0


def cmd_new(config: Config, args: list[str]) -> int:
    force, args = _take_force(args)
    if args:
        workspace = workspaces.named(config, args[0])
        if args[1:]:
            raise UsageError("new takes only a workspace")
    else:
        workspace = workspaces.current(config)
        if workspace is None:
            raise WtError(f"new needs a workspace name outside {config.root}")
    if workspace.create(force_guidance=force):
        print(
            f"created  {workspace.path}  branch {workspace.branch}",
            file=sys.stderr,
        )
    print(workspace.path)
    return 0


def cmd_path(config: Config, args: list[str]) -> int:
    workspace, rest = workspaces.resolve(config, args)
    if rest:
        raise UsageError("path takes only a workspace")
    print(workspace.require())
    return 0


def cmd_pwd(config: Config, args: list[str]) -> int:
    """Answer "where am I" without naming anything.

    Unlike `path`, this never reads an argument as a workspace, so it stays
    usable from a deep subdirectory of a clone.
    """
    if args:
        raise UsageError("pwd takes no arguments")
    workspace = workspaces.current(config)
    if workspace is None:
        raise WtError(f"not inside a workspace under {config.root}")
    print(workspace.require())
    return 0


def cmd_branch(config: Config, args: list[str]) -> int:
    workspace, rest = workspaces.resolve(config, args)
    if rest:
        raise UsageError("branch takes only a workspace")
    print(workspace.branch)
    return 0


def cmd_clone(config: Config, args: list[str]) -> int:
    workspace, rest = workspaces.resolve(config, args)
    if not rest:
        raise UsageError("clone needs at least one repository")
    specs = [clone.parse(item) for item in rest]
    if workspace.create():
        print(f"created  {workspace.path}", file=sys.stderr)
    for spec in specs:
        if clone.into(workspace.path, spec, config.forge, workspace.branch):
            print(f"cloned   {spec.name}  on {workspace.branch}")
        else:
            print(f"ok       {spec.name}")
    return 0


def _fan_out(workspace: workspaces.Workspace, args: list[str]) -> int:
    names = workspace.repo_names()
    if not names:
        print(f"wt: no repositories in {workspace.path}", file=sys.stderr)
        return 0
    status = 0
    for name in names:
        print(f"== {name}")
        sys.stdout.flush()
        if gitcmd.stream(workspace.path / name, args) != 0:
            status = 1
            print(f"wt: git failed in {name}", file=sys.stderr)
    return status


def cmd_git(config: Config, args: list[str]) -> int:
    workspace, rest = workspaces.resolve(config, args)
    if rest and rest[0] == "--":
        rest = rest[1:]
    if not rest:
        raise UsageError("git needs a command")
    workspace.require()
    return _fan_out(workspace, rest)


def cmd_status(config: Config, args: list[str]) -> int:
    workspace, rest = workspaces.resolve(config, args)
    if rest:
        raise UsageError("status takes only a workspace")
    workspace.require()
    statuses = workspace.statuses()
    if not statuses:
        print(f"No repositories in {workspace.path}")
        return 0
    for status in statuses:
        _print_repo(status)
        porcelain = gitcmd.value(
            status.path, "status", "--porcelain", "--untracked-files=normal"
        )
        for line in (porcelain or "").splitlines():
            print(f"  {line}")
    return 0


def cmd_fetch(config: Config, args: list[str]) -> int:
    workspace, rest = workspaces.resolve(config, args)
    if rest:
        raise UsageError("fetch takes only a workspace")
    workspace.require()
    return _fan_out(workspace, ["fetch", "--prune"])


def cmd_pull(config: Config, args: list[str]) -> int:
    workspace, rest = workspaces.resolve(config, args)
    if rest:
        raise UsageError("pull takes only a workspace")
    workspace.require()
    return _fan_out(workspace, ["pull", "--ff-only"])


def cmd_agents(config: Config, args: list[str]) -> int:
    if args:
        raise UsageError("agents takes no arguments")
    _report_agents(config)
    return 0


def cmd_check(config: Config, args: list[str]) -> int:
    if args:
        raise UsageError("check takes no arguments")
    results = checks.run(config)
    for result in results:
        print(f"{result.level:<8} {result.message}")
    if checks.failed(results):
        print("wt check failed.", file=sys.stderr)
        return 1
    print("wt check passed.")
    return 0


def _named_target(
    config: Config, args: list[str], verb: str
) -> workspaces.Workspace | None:
    """The workspace a sweeping verb was pointed at, None when it was not.

    What an unnamed sweep covers is left to the verb; the two disagree.
    """
    if len(args) > 1:
        raise UsageError(f"{verb} takes only a workspace")
    if not args:
        return None
    workspace = workspaces.named(config, args[0])
    workspace.require()
    return workspace


def _keep_reason(
    workspace: workspaces.Workspace,
    here: workspaces.Workspace | None,
    busy: slots.BusyAgents,
) -> str:
    """Why a sweep spares this workspace, or empty when it can go.

    The cheap facts come first, so a busy or current workspace is never
    asked to walk its clones.
    """
    if here is not None and workspace.name == here.name:
        return "the current directory"
    if busy.holds(workspace.name):
        return "an agent is running here"
    unsaved = workspace.has_unsaved_work()
    if unsaved:
        return f"unsaved: {' '.join(unsaved)}"
    strays = workspace.unaccounted()
    if strays:
        return f"not from wt: {' '.join(strays)}"
    return ""


def cmd_tidy(config: Config, args: list[str]) -> int:
    """Tidy the workspace you named, or the one you are standing in.

    Only from outside the root does an unnamed tidy mean all of them, and
    that sweep spares a workspace with a running agent; a named one is not
    second-guessed, since an agent tidying the workspace it was launched
    into holds that slot itself.
    """
    dry_run, args = _take_dry_run(args)
    here = workspaces.current(config)
    chosen = _named_target(config, args, "tidy") or here
    targets = workspaces.listing(config) if chosen is None else [chosen]
    if not targets:
        print(f"No workspaces under {config.root}")
        return 0

    # The workspace an agent is standing in is its own to tidy; every other
    # occupied one keeps its build, whether it was named or merely swept up.
    busy = _pool(config).busy_agents()
    mine = here.name if here is not None else ""
    word = "would rm" if dry_run else "removed"
    status = 0
    total = 0
    for workspace in targets:
        if workspace.name != mine and busy.holds(workspace.name):
            print(f"{'kept':<9}{workspace.name}  an agent is running here")
            continue
        try:
            for kind, path in workspace.tidy(dry_run=dry_run):
                if kind == "removed":
                    total += 1
                    print(f"{word:<9}{workspace.name}/{path}")
                elif kind == "tracked":
                    print(f"{'kept':<9}{workspace.name}/{path}  tracked")
                else:
                    print(f"{'kept':<9}{workspace.name}/{path}  a symlink")
        except WtError as error:
            print(f"wt: {error.message}", file=sys.stderr)
            status = 1
    noun = "path" if total == 1 else "paths"
    print(f"{total} transient {noun} {'to remove' if dry_run else 'removed'}")
    return status


def cmd_clean(config: Config, args: list[str]) -> int:
    """Sweep out every workspace whose work is already saved.

    There is deliberately no --force: discarding unsaved work stays a named,
    single-workspace decision made through `wt rm`.
    """
    dry_run, args = _take_dry_run(args)
    named = _named_target(config, args, "clean")
    targets = [named] if named else workspaces.listing(config)
    if not targets:
        print(f"No workspaces under {config.root}")
        return 0

    here = workspaces.current(config)
    busy = _pool(config).busy_agents()
    word = "would rm" if dry_run else "removed"
    status = 0
    removed = 0
    kept = 0
    emptied: list[str] = []
    for workspace in targets:
        try:
            # Prove the path is one wt owns before anything else reads it,
            # and before a dry run promises a removal the real run refuses.
            # A workspace that fails this is a defect, not a thing to keep.
            workspace.checked_target()
            reason = _keep_reason(workspace, here, busy)
            if not reason and not dry_run:
                workspace.remove()
        except WtError as error:
            print(f"wt: {error.message}", file=sys.stderr)
            status = 1
            kept += 1
            continue
        if reason:
            print(f"{'kept':<9}{workspace.name}  {reason}")
            kept += 1
            continue
        print(f"{word:<9}{workspace.name}")
        removed += 1
        if not dry_run:
            emptied.append(workspace.project)

    for project in workspaces.prune_projects(config, emptied):
        print(f"{'pruned':<9}{project}  empty project")
    print(f"{removed} {'to remove' if dry_run else 'removed'}, {kept} kept")
    return status


def cmd_rm(config: Config, args: list[str]) -> int:
    force, args = _take_force(args)
    if len(args) != 1:
        raise UsageError("rm needs exactly one workspace")
    workspace = workspaces.named(config, args[0])
    try:
        removed = workspace.remove(force=force)
    except UnsavedWorkError as error:
        for name in error.repositories:
            print(f"unsaved  {name}", file=sys.stderr)
        raise
    print(f"removed  {removed}")
    return 0


def launch(config: Config, agent: str, args: list[str]) -> int:
    """Create or reuse the workspace, take a slot, and become the agent."""
    if not args:
        raise UsageError(f"{agent} needs a workspace")
    if shutil.which(agent) is None:
        raise WtError(f"agent is not installed: {agent}")
    if config.max_agents <= 0:
        raise WtError(
            f"WT_MAX_AGENTS is not a positive integer: {config.max_agents_raw}"
        )

    workspace = workspaces.named(config, args[0])
    if workspace.create():
        print(f"created  {workspace.path}", file=sys.stderr)

    # The pool stays referenced for the rest of this process: it owns the open
    # descriptor that holds the slot across the exec below.
    pool = _pool(config)
    slot = pool.acquire(agent, workspace.name)
    if slot is None:
        print(
            f"wt: all {config.max_agents} agent slots are busy (WT_MAX_AGENTS)",
            file=sys.stderr,
        )
        _report_agents(config, stream=sys.stderr)
        return 1

    os.environ["WT_WORKSPACE"] = workspace.name
    os.environ["WT_WORKSPACE_DIR"] = str(workspace.path)
    os.environ["WT_BRANCH"] = workspace.branch
    os.environ["WT_AGENT_SLOT"] = str(slot)
    # A workspace keeps no work ledger. The workspace root is not a
    # repository, so aiq would otherwise fall back to user scope and capture
    # every prompt of a session that is meant to be disposable.
    os.environ["AIQ_DISABLE"] = "1"
    os.chdir(workspace.path)
    print(
        f"wt: {agent} in {workspace.path} on {workspace.branch} "
        f"(slot {slot} of {config.max_agents})",
        file=sys.stderr,
    )
    sys.stdout.flush()
    sys.stderr.flush()
    os.execvp(agent, [agent, *args[1:]])


VERBS = {
    "ls": cmd_ls,
    "list": cmd_ls,
    "new": cmd_new,
    "path": cmd_path,
    "pwd": cmd_pwd,
    "branch": cmd_branch,
    "clone": cmd_clone,
    "git": cmd_git,
    "status": cmd_status,
    "fetch": cmd_fetch,
    "pull": cmd_pull,
    "agents": cmd_agents,
    "check": cmd_check,
    "tidy": cmd_tidy,
    "clean": cmd_clean,
    "rm": cmd_rm,
}


def dispatch(config: Config, argv: list[str]) -> int:
    if not argv:
        raise UsageError("no command given")
    command, args = argv[0], argv[1:]
    if command in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if command in VERBS:
        return VERBS[command](config, args)
    if command in KNOWN_AGENTS:
        return launch(config, command, args)
    if command.startswith("-"):
        raise UsageError(f"unknown option: {command}")
    return launch(config, config.agent, argv)


def main(argv: list[str] | None = None, config: Config | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        return dispatch(config or Config.from_env(), arguments)
    except UsageError as error:
        print(f"wt: {error.message}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return error.exit_code
    except WtError as error:
        print(f"wt: {error.message}", file=sys.stderr)
        return error.exit_code
    except KeyboardInterrupt:
        return 130
