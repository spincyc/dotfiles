"""The `wt` command line.

Argument parsing and every line of output live here; the other modules stay
importable without printing anything.
"""

import difflib
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import checks, clone, gitcmd, repos, sessions, slots, workspaces
from .config import KNOWN_AGENTS, Config
from .errors import (
    PartlyRemoved,
    RelayBlocked,
    RemovalRefused,
    UnsavedWorkError,
    UsageError,
    WtError,
)

USAGE = """\
Usage: wt [claude|codex|droid] [--new] [-b <branch>] [-r <repo>]...
          [--seed[-file] <x>] [<project>/]<slug>[/<child>...] [agent-args...]
       wt <verb> [<workspace>] [args...]

Launch:
  wt claude telos/agent-sync      Create or reuse the workspace, then run
  wt codex telos/agent-sync       the named agent with it as the working
  wt droid telos/agent-sync       directory
  wt telos/agent-sync             Use $WT_AGENT (default claude)
  wt agent-sync                   A bare slug takes $WT_PROJECT

  --new                           Start a fresh session; without it a launch
                                  resumes the one this agent had here
  -b, --branch <branch>           Work on this branch instead of the derived
                                  one; recorded when the workspace is created
  -r, --clone <repo>              Clone owner/repo, a URL, or a local path
                                  into the workspace first; repeatable
  --seed <text>                   Open the agent with this prompt, given to
                                  it as its trailing prompt argument
  --seed-file <path>              The same prompt read from a file, or from
                                  stdin when <path> is -, so that generated
                                  text never passes through shell quoting
  --relay <owner>/<repo>@<sha>    Open an agent on the relay brief that
                                  commit published: clone onto the -b
                                  branch, preflight and claim the turn, and
                                  hand over the brief and the commands

These are wt's own and may be typed either side of the workspace; -- ends them
and hands everything after it to the agent untouched. A launch continues the
session the named agent last had in that workspace, when wt recorded one and
the agent has a spelling for it; claude, codex and droid do, anything else is
always fresh. Only claude can be resumed and seeded at once, since codex and
droid both read a trailing prompt as the session to resume; a --seed asking
for both is refused, and a --relay turn opens a fresh session instead, since
its prompt is derived rather than typed. Use --new when driving the agent's
own session flags yourself.

--relay is what a relay-v6 launch handoff invokes. It needs -b and derives
everything else from the brief's front matter at the pinned commit. It then
performs the protocol's steps before the work -- initialization, preflight and
the claim -- rather than describing them to the agent, and a stop prints its
blocked-channel line and exits 3 before any session opens. It waits for the
agent rather than becoming it, so that when the session ends it can say
whether the result reached origin and print what the run owes its planner.

One launch does the whole opening: -b names the branch, -r clones what the
work needs onto it, and --seed says what to do there, so a new line of work
costs one command rather than new, clone and launch in sequence.

A workspace is a leaf named <project>/<slug>[/<child>...]. Intermediate
components group a stack of workspaces. Every repository in a leaf works on
feature/<slug>[/<child>...] ($WT_BRANCH_PREFIX plus the complete slug stack),
unless -b named another branch when the workspace was created, which is then
recorded in its .wt-workspace and is what every verb here means by "the
workspace branch". Existing leaves may be selected by full name, branch, slug
stack, unique leaf, or unambiguous component prefixes.

Verbs:
  ls [-q]                         List workspaces and the repos they hold;
                                  -q prints bare names, one per line
  new [--force] [-b <branch>]     Create a workspace, do not launch an agent
      [-r <repo>]... [<ws>]
  path [<workspace>]              Print a workspace directory
  pwd                             Print the root of the workspace you are in
  clone [-w <ws>] [-o <owner>]    Clone owner/repo, a URL, or a local path to
        [-b <branch>] <repo>...   <owner>/<repo>, on the workspace branch;
                                  -o files one clone under a chosen owner
  branch [<workspace>]            Print the workspace branch
  git [-w <workspace>] [--] <a>.. Run git in every repo of the workspace
  exec [-w <workspace>] [--] <c>. Run any command in every repo, with
                                  $WT_REPO naming each one
  status [-q] [<workspace>]       Per-repo branch, upstream, cleanliness;
                                  -q is one tab-separated line per repo
  log [<workspace>]               The commits of this line of work, per repo
  fetch [<workspace>]             git fetch --prune in every repo
  sync [<workspace>]              Fetch, then rebase onto the default branch
                                  (pull is not an alias; sync rewrites)
  push [<workspace>]              Publish the workspace branch where there is
                                  work to publish
  agents                          Show the agents running right now, with the
                                  run and turn of any relay worker among them
  check                           Sanity-check the environment and layout
  tidy [-n] [<workspace>]         Delete .scratch and Git-ignored files
  sweep [-n] [<workspace>]        Remove workspaces whose work is all pushed
  rm [-f] <workspace>             Remove a workspace holding no unsaved work
  help                            Show this message

Transient files belong under .scratch, at the top of a workspace or of a
clone; wt tidy deletes those and whatever the clones ignore. Unnamed, wt tidy
covers the workspace you are standing in, or every one when you are outside
the root; it spares a workspace another agent is running in. Unnamed, wt
sweep covers every workspace, keeping any that holds unsaved work, runs an
agent, contains the current directory, or holds anything wt cannot account
for. Both take -n for --dry-run.

A verb reads its first argument as the workspace when that workspace already
exists, or when the current directory is not inside one. `new`, `tidy` and
`sweep` name a workspace or take none, and `pwd` takes none at all. `clone`,
`git` and `exec` take -w to name one explicitly, since their other arguments
look just like a workspace name.

wt never changes the calling shell's directory; use cd "$(wt path NAME)", or
cd "$(wt pwd)" to return to the top of the workspace you are already in.

Environment:
  WT_ROOT            Workspace root           (default ~/git/worktrees)
  WT_PROJECT         Project for a bare slug  (no default)
  WT_BRANCH_PREFIX   Workspace branch prefix  (default feature)
  WT_AGENT           Agent for bare launches  (default claude)
  WT_FORGE           Base URL for owner/repo  (default https://github.com,
                     unused when gh is installed)

How many agents run at once is up to you; each one holds a slot in
$WT_ROOT/.agents for as long as it runs, which is how the verbs above know
not to delete a workspace out from under it.

Exported into the agent:
  WT_WORKSPACE       The complete workspace name
  WT_WORKSPACE_DIR   Its absolute path
  WT_BRANCH          The workspace branch, for git push -u origin "$WT_BRANCH"
  WT_AGENT_SLOT      Which slot this agent holds
  AIQ_DISABLE        A workspace keeps no work ledger\
"""

REPO_LINE = "{name:<34} {branch:<22} {state:<7} {upstream:<26} {tracking}"
LABELS = {checks.Level.OK: "ok", checks.Level.WARN: "warn",
          checks.Level.FAIL: "fail"}


def _take_flag(args: list[str], *spellings: str) -> tuple[bool, list[str]]:
    """Read a flag from wherever in the arguments it was typed.

    `--force` used to be accepted only in first position, so the obvious
    `wt rm telos/demo --force` failed with "rm needs exactly one workspace",
    blaming the wrong thing.
    """
    kept = [arg for arg in args if arg not in spellings]
    return len(kept) != len(args), kept


def _take_force(args: list[str]) -> tuple[bool, list[str]]:
    return _take_flag(args, "--force", "-f")


def _take_dry_run(args: list[str]) -> tuple[bool, list[str]]:
    return _take_flag(args, "--dry-run", "-n")


def _print_repo(status: repos.RepoStatus, indent: str = "") -> None:
    print(
        indent
        + REPO_LINE.format(
            name=status.name,
            branch=status.branch,
            state=status.state,
            upstream=status.upstream or "(no upstream)",
            tracking=status.tracking,
        ).rstrip()
    )


def _pool(config: Config) -> slots.SlotPool:
    return slots.SlotPool(config.agents_dir)


def _require_slot_view(config: Config) -> slots.BusyAgents:
    """Which workspaces hold an agent, or refuse to guess.

    A verb that deletes things must not proceed on a pool it could not
    survey: a registry that cannot be read is not an empty one, and reading
    it as empty is what sweeps a workspace out from under a live agent. The
    survey raises in that case, and this is the one place every such verb
    goes through, so none of them can forget to ask.
    """
    return _pool(config).busy_agents()


def _only_workspace(
    config: Config, args: list[str], verb: str
) -> workspaces.Workspace:
    """The workspace a verb was pointed at, with no arguments left over.

    A supplied selector always names the target; only an omitted one falls
    back to the current workspace.
    """
    if args:
        workspace = workspaces.select(config, args[0])
        rest = args[1:]
    else:
        workspace, rest = workspaces.resolve(config, args)
    if rest:
        raise UsageError(f"{verb} takes only a workspace")
    workspace.require()
    return workspace


def _named_target(
    config: Config, args: list[str], verb: str
) -> workspaces.Workspace | None:
    """The workspace a sweeping verb was pointed at, None when it was not."""
    if len(args) > 1:
        raise UsageError(f"{verb} takes only a workspace")
    if not args:
        return None
    workspace = workspaces.select(config, args[0])
    workspace.require()
    return workspace


def cmd_ls(config: Config, args: list[str]) -> int:
    quiet, args = _take_flag(args, "-q", "--porcelain", "--names")
    if args:
        raise UsageError("ls takes no arguments")
    found = workspaces.listing(config)
    if not found:
        if not quiet:
            print(f"No workspaces under {config.root}")
        return 0
    for workspace in found:
        if quiet:
            # One name per line, nothing else: this is what completion, a cd
            # shim, and any script that iterates workspaces actually need.
            print(workspace.name)
            continue
        print(workspace.name)
        statuses = workspace.statuses()
        if not statuses:
            print("  (no repositories)")
        for status in statuses:
            _print_repo(status, indent="  ")
    return 0


def cmd_new(config: Config, args: list[str]) -> int:
    force, args = _take_force(args)
    pin, args = _take_option(args, "-b", "--branch", what="branch")
    specs, args = _take_clones(args)
    if args:
        workspace = workspaces.reuse_or_named(
            config, args[0], abbreviate=False
        )
        if args[1:]:
            raise UsageError("new takes only a workspace")
    else:
        workspace = workspaces.current(config)
        if workspace is None:
            raise WtError(f"new needs a workspace name outside {config.root}")
    workspace = workspace.pinned_to(pin)
    if workspace.create(force_guidance=force):
        print(
            f"created  {workspace.path}  branch {workspace.branch}",
            file=sys.stderr,
        )
    _clone_specs(workspace, specs)
    print(workspace.path)
    return 0


def cmd_path(config: Config, args: list[str]) -> int:
    print(_only_workspace(config, args, "path").path)
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
    print(_only_workspace(config, args, "branch").branch)
    return 0


def _clone_specs(
    workspace: workspaces.Workspace, specs: list[clone.CloneSpec]
) -> None:
    """Put each repository in the workspace, saying which were new.

    On stderr, because a launch has already said what it created there and
    a caller reading `wt new`'s stdout wants the path and nothing else.
    """
    for spec in specs:
        if clone.into(
            workspace.path, spec, workspace.config.forge, workspace.branch
        ):
            print(
                f"cloned   {spec.name}  on {workspace.branch}",
                file=sys.stderr,
            )
        else:
            print(f"ok       {spec.name}", file=sys.stderr)


def cmd_clone(config: Config, args: list[str]) -> int:
    named, args = _take_option(args, "-w", "--workspace")
    owner, args = _take_option(args, "-o", "--owner", what="owner")
    pin, args = _take_option(args, "-b", "--branch", what="branch")
    if named is not None:
        workspace, rest = workspaces.reuse_or_named(config, named), args
    else:
        workspace, rest = workspaces.resolve(config, args)
    workspace = workspace.pinned_to(pin)
    if not rest:
        raise UsageError("clone needs at least one repository")
    if owner is not None and len(rest) > 1:
        # One owner cannot describe several repositories, and silently
        # filing them all under it would be worse than refusing.
        raise UsageError("-o takes one repository at a time")
    specs = [clone.parse(item) for item in rest]
    if owner is not None:
        specs = [clone.with_owner(spec, owner) for spec in specs]
    if workspace.create():
        print(f"created  {workspace.path}", file=sys.stderr)
    for spec in specs:
        if clone.into(workspace.path, spec, config.forge, workspace.branch):
            print(f"cloned   {spec.name}  on {workspace.branch}")
        else:
            print(f"ok       {spec.name}")
    return 0


def _take_clones(
    args: list[str],
) -> tuple[list[clone.CloneSpec], list[str]]:
    """Read every `--clone <spec>` from the arguments, in the order typed.

    Parsed here rather than at the point of use so a name the workspace
    cannot hold is refused before anything is created: a spec that fails
    halfway through leaves a workspace and some of its clones, and the
    cheap half of that is knowing sooner.
    """
    specs: list[clone.CloneSpec] = []
    kept = list(args)
    while True:
        found, kept = _take_option(
            kept, "-r", "--clone", what="repository"
        )
        if found is None:
            return specs, kept
        specs.append(clone.parse(found))


def _take_option(
    args: list[str], *spellings: str, what: str = "workspace"
) -> tuple[str | None, list[str]]:
    """Read `-w NAME` or `--long=VALUE` from anywhere in the arguments."""
    for index, arg in enumerate(args):
        name, assigned, inline = arg.partition("=")
        if assigned and name.startswith("--") and name in spellings:
            return inline, args[:index] + args[index + 1:]
        if arg in spellings:
            if index + 1 >= len(args):
                raise UsageError(f"{arg} needs a {what}")
            return args[index + 1], args[:index] + args[index + 2:]
    return None, args


def _narrate(message: str) -> None:
    """Say something on stderr, after everything already said on stdout.

    Our own lines are block-buffered under a pipe while a child writes to
    the same descriptor unbuffered, so a header printed without flushing
    first appears above output that was produced before it — attributing
    every result line to the wrong repository.
    """
    sys.stdout.flush()
    print(message, file=sys.stderr)
    sys.stderr.flush()


def _stream(repo: Path, args: list[str]) -> int:
    """Run git with its output attached, without letting ours overtake it."""
    sys.stdout.flush()
    sys.stderr.flush()
    return gitcmd.stream(repo, args)


def _fan_out(
    workspace: workspaces.Workspace,
    args: list[str],
    program: str | None = None,
) -> int:
    names = workspace.repo_names()
    if not names:
        print(f"wt: no repositories in {workspace.path}", file=sys.stderr)
        return 0
    status = 0
    for name in names:
        # The header names the repository the following output came from; it
        # is narration, so it stays off stdout and `wt git -- rev-parse HEAD`
        # stays pipeable.
        _narrate(f"== {name}")
        if program is None:
            code = _stream(workspace.path / name, args)
        else:
            sys.stdout.flush()
            sys.stderr.flush()
            try:
                code = _run_in(workspace.path / name, [program, *args], name)
            except WtError as error:
                # A relative program resolves per repository, so one clone
                # lacking it must not abandon the clones after it.
                print(f"wt: {error.message}", file=sys.stderr)
                status = 1
                continue
        if code != 0:
            status = 1
            print(f"wt: failed in {name}", file=sys.stderr)
    return status


def _run_in(repo: Path, command: list[str], name: str) -> int:
    """Run a command in one clone, telling it which clone it is in."""
    environment = {**os.environ, "WT_REPO": name, "WT_REPO_DIR": str(repo)}
    try:
        return subprocess.run(
            command, cwd=repo, env=environment, check=False
        ).returncode
    except OSError as error:
        raise WtError(f"cannot run {command[0]} in {name}: {error}") from error


def cmd_git(config: Config, args: list[str]) -> int:
    workspace, rest = _fan_out_target(config, args, "git")
    if not rest:
        raise UsageError("git needs a command")
    return _fan_out(workspace, rest)


def cmd_exec(config: Config, args: list[str]) -> int:
    workspace, rest = _fan_out_target(config, args, "exec")
    if not rest:
        raise UsageError("exec needs a command")
    return _fan_out(workspace, rest[1:], program=rest[0])


def _fan_out_target(
    config: Config, args: list[str], verb: str
) -> tuple[workspaces.Workspace, list[str]]:
    """Split a fan-out verb's arguments into its workspace and its command.

    These verbs take arbitrary trailing arguments, and a command argument
    looks exactly like a workspace name — `wt exec src/build.sh` is not a
    request about a workspace called `src/build.sh`. So only a selector that
    resolves to an existing workspace is inferred; `-w` names one explicitly.
    """
    named, args = _take_option(args, "-w", "--workspace")
    if named is not None:
        workspace, rest = workspaces.select(config, named), args
    else:
        workspace, rest = workspaces.resolve(config, args)
    workspace.require()
    if rest and rest[0] == "--":
        rest = rest[1:]
    return workspace, rest


def cmd_status(config: Config, args: list[str]) -> int:
    porcelain, args = _take_flag(args, "-q", "--porcelain")
    workspace = _only_workspace(config, args, "status")
    statuses = workspace.statuses()
    if not statuses:
        if not porcelain:
            print(f"No repositories in {workspace.path}")
        return 0
    for status in statuses:
        if porcelain:
            # Tab-separated and column-free: the human form aligns on fixed
            # widths that a long owner/repo name pushes out, and there was
            # no shape a script could read at all.
            print(
                "\t".join(
                    (
                        workspace.name,
                        status.name,
                        status.branch,
                        status.upstream or "",
                        status.state,
                        "" if status.ahead is None else str(status.ahead),
                        "" if status.behind is None else str(status.behind),
                    )
                )
            )
            continue
        _print_repo(status)
        for line in repos.changes(status.path) or []:
            print(f"  {line}")
    return 0


def cmd_fetch(config: Config, args: list[str]) -> int:
    workspace = _only_workspace(config, args, "fetch")
    return _fan_out(workspace, ["fetch", "--prune"])


def _mid_rebase(repo: Path) -> bool:
    """True when a rebase was left unfinished in this clone."""
    return any(
        (repo / ".git" / name).exists()
        for name in ("rebase-merge", "rebase-apply")
    )


def _tracked_changes(repo: Path) -> bool | None:
    """True when tracked files differ from HEAD. None when git could not say.

    `repos.is_dirty` counts untracked files, which is right for the deletion
    gate and wrong as a rebase precondition: a stray note beside the code
    does not stop a rebase, and treating it as if it did made `wt sync`
    quietly do nothing for the rest of a session.
    """
    lines = repos.changes(repo)
    if lines is None:
        return None
    return any(not line.startswith("??") for line in lines)


def cmd_sync(config: Config, args: list[str]) -> int:
    """Fetch, then put every clone back on top of its default branch.

    `git pull --ff-only` only ever worked in the window before the first
    commit: once the work diverges it refuses, and once the branch is
    published its upstream is no longer the default branch at all, so the
    thing a user means by "pull" stopped happening exactly when they needed
    it.
    """
    workspace = _only_workspace(config, args, "sync")
    names = workspace.repo_names()
    if not names:
        _narrate(f"wt: no repositories in {workspace.path}")
        return 0
    status = 0
    skipped = 0
    for name in names:
        repo = workspace.path / name
        _narrate(f"== {name}")
        if _stream(repo, ["fetch", "--prune"]) != 0:
            _narrate(f"wt: fetch failed in {name}")
            status = 1
            continue
        if not repos.has_commits(repo):
            # Nothing to rebase, and nothing wrong: a clone of an empty
            # repository used to be counted as a skip, which made the whole
            # workspace exit non-zero forever.
            print(f"skipped  {name}  no commits yet")
            continue
        if _mid_rebase(repo):
            # Reported before the dirty test, which would otherwise call an
            # unfinished rebase "uncommitted changes" and hide it entirely.
            print(f"skipped  {name}  a rebase is already in progress")
            skipped += 1
            continue
        on = repos.branch(repo)
        if on != workspace.branch:
            # Rebasing whatever HEAD happens to be would rewrite a side
            # branch, or a detached HEAD whose commits nothing else names.
            print(f"skipped  {name}  on {on}, not {workspace.branch}")
            skipped += 1
            continue
        dirty = _tracked_changes(repo)
        if dirty is None or dirty:
            reason = "uncommitted changes" if dirty else "git cannot say"
            print(f"skipped  {name}  {reason}")
            skipped += 1
            continue
        default = repos.default_branch(repo)
        if default is None:
            print(
                f"skipped  {name}  no default branch on origin; "
                f"git remote set-head origin -a"
            )
            skipped += 1
            continue
        if _stream(repo, ["rebase", f"origin/{default}"]) != 0:
            status = 1
            if _mid_rebase(repo):
                _narrate(f"wt: {name} is mid-rebase; resolve and "
                    f"git rebase --continue, or git rebase --abort")
            else:
                _narrate(f"wt: rebase onto origin/{default} failed in {name}")
            continue
        print(f"synced   {name}  onto origin/{default}")
    if skipped:
        # A partial sync must not read as a whole one to `wt sync && wt push`.
        _narrate(f"wt: {skipped} of {len(names)} repositories skipped")
        status = status or 1
    return status


def cmd_pull(config: Config, args: list[str]) -> int:
    """Refuse, and say what to run instead.

    `pull` used to mean `git pull --ff-only`, which never rewrote anything.
    `sync` rebases. Silently pointing an old habit at a history rewrite is
    not a rename, so this asks rather than assumes.
    """
    raise UsageError(
        "pull is now sync, which rebases onto the default branch; "
        "run wt sync"
    )


def cmd_push(config: Config, args: list[str]) -> int:
    """Publish the workspace branch, only where there is something to publish.

    A blanket `git push -u` across the workspace creates a remote branch for
    every clone the agent never touched, and retargets their upstreams,
    after which `wt status` can no longer tell which repository holds the
    work.
    """
    workspace = _only_workspace(config, args, "push")
    names = workspace.repo_names()
    if not names:
        _narrate(f"wt: no repositories in {workspace.path}")
        return 0
    status = 0
    pushed = 0
    for name in names:
        repo = workspace.path / name
        on = repos.branch(repo)
        if on != workspace.branch:
            print(f"skipped  {name}  on {on}, not {workspace.branch}")
            continue
        # The branch question, not the workspace-wide one: a commit parked
        # on an unrelated side branch is not a reason to publish this one.
        outstanding = repos.unpushed(repo, workspace.branch)
        if outstanding == 0:
            print(f"skipped  {name}  nothing to publish")
            continue
        if outstanding is None:
            print(f"skipped  {name}  no commits yet")
            continue
        _narrate(f"== {name}")
        if _stream(repo, ["push", "-u", "origin", workspace.branch]) != 0:
            _narrate(f"wt: push failed in {name}")
            status = 1
            continue
        pushed += 1
        print(f"pushed   {name}  {workspace.branch}")
    noun = "repository" if pushed == 1 else "repositories"
    print(f"{pushed} {noun} published")
    return status


def cmd_log(config: Config, args: list[str]) -> int:
    """The commits of this line of work, in every clone that has any.

    There is no single revision range a user could type instead: one repo's
    default is `main`, another's `master`, and after publication neither is
    the upstream any more.
    """
    workspace = _only_workspace(config, args, "log")
    names = workspace.repo_names()
    if not names:
        _narrate(f"wt: no repositories in {workspace.path}")
        return 0
    status = 0
    for name in names:
        repo = workspace.path / name
        if not repos.has_commits(repo):
            continue
        span = repos.line_of_work(repo, workspace.branch)
        if span is None:
            _narrate(f"wt: {name} has no default branch on origin; "
                f"git remote set-head origin -a")
            status = 1
            continue
        code, listed = gitcmd.read(repo, "log", "--oneline", span)
        if code != 0:
            # An empty answer and an unanswerable question are different
            # facts, and collapsing them let a broken clone vanish silently.
            _narrate(f"wt: cannot list {span} in {name}")
            status = 1
            continue
        if not listed:
            continue
        print(name)
        for line in listed.splitlines():
            print(f"  {line}")
    return status


def cmd_agents(config: Config, args: list[str]) -> int:
    """List the agents running now. A free slot is a lock file, not news."""
    if args:
        raise UsageError("agents takes no arguments")
    running = _pool(config).running()
    for state in running:
        # An unidentifiable slot is still an agent, and saying so is what
        # explains why the deleting verbs are refusing to touch anything.
        print(f"slot {state.index:<3} {state.info or '(unidentified)'}")
    if not running:
        print("no agents running")
        return 0
    noun = "agent" if len(running) == 1 else "agents"
    print(f"{len(running)} {noun} running")
    return 0


def cmd_check(config: Config, args: list[str]) -> int:
    if args:
        raise UsageError("check takes no arguments")
    results = checks.run(config)
    for result in results:
        print(f"{LABELS[result.level]:<8} {result.message}")
    # stdout is block-buffered under a pipe, so the verdict on stderr would
    # otherwise be printed above the results it summarises.
    sys.stdout.flush()
    if checks.failed(results):
        print("wt check failed.", file=sys.stderr)
        return 1
    print("wt check passed.")
    return 0


def cmd_tidy(config: Config, args: list[str]) -> int:
    """Tidy the workspace you named, or the one you are standing in.

    Only from outside the root does an unnamed tidy mean all of them, and
    that sweep spares a workspace with a running agent; the workspace an
    agent is standing in is its own to tidy, since it holds that slot itself.
    """
    dry_run, args = _take_dry_run(args)
    here = workspaces.current(config)
    chosen = _named_target(config, args, "tidy") or here
    targets = workspaces.listing(config) if chosen is None else [chosen]
    if not targets:
        print(f"No workspaces under {config.root}")
        return 0

    busy = _require_slot_view(config)
    mine = here.name if here is not None else ""
    word = "would rm" if dry_run else "removed"
    status = 0
    total = 0
    for workspace in targets:
        if workspace.name != mine and busy.holds(workspace.name):
            print(f"{'kept':<9}{workspace.name}  an agent is running here")
            continue
        # Reported as each step happens, not from the returned list: a clean
        # that dies partway raises, and the account of what it had already
        # deleted must not die with it.
        nonlocal_failed: list[str] = []

        def report(kind: str, path: str, name: str = workspace.name) -> None:
            nonlocal total
            if kind == workspaces.REMOVED:
                total += 1
                print(f"{word:<9}{name}/{path}")
            elif kind == workspaces.TRACKED:
                print(f"{'kept':<9}{name}/{path}  tracked")
            elif kind == workspaces.NESTED:
                print(f"{'kept':<9}{name}/{path}  holds a repository")
            elif kind == workspaces.FAILED:
                nonlocal_failed.append(path)
                print(f"{'failed':<9}{name}/{path}")
            else:
                print(f"{'kept':<9}{name}/{path}  a symlink")

        try:
            workspace.tidy(dry_run=dry_run, on_step=report)
        except (WtError, OSError) as error:
            print(f"wt: {_message(error)}", file=sys.stderr)
            status = 1
        if nonlocal_failed:
            status = 1
    noun = "path" if total == 1 else "paths"
    print(f"{total} transient {noun} {'to remove' if dry_run else 'removed'}")
    return status


def cmd_sweep(config: Config, args: list[str]) -> int:
    """Sweep out every workspace whose work is already saved.

    There is deliberately no --force: discarding unsaved work stays a named,
    single-workspace decision made through `wt rm`.
    """
    dry_run, args = _take_dry_run(args)
    named = _named_target(config, args, "sweep")
    targets = [named] if named else sorted(
        workspaces.listing(config),
        key=lambda workspace: (
            -len(Path(workspace.name).parts),
            workspace.name,
        ),
    )
    if not targets:
        print(f"No workspaces under {config.root}")
        return 0

    here = workspaces.current(config)
    # Surveyed once here only to fail fast on an unusable limit; every
    # workspace re-surveys below, because the answer that matters most —
    # whether an agent is running in this tree — is also the one most likely
    # to have changed since the sweep began.
    _require_slot_view(config)
    word = "would rm" if dry_run else "removed"
    status = 0
    removed = 0
    kept = 0
    damaged = 0
    emptied: list[str] = []
    for workspace in targets:
        try:
            # Prove the path is one wt owns before anything else reads it.
            # A workspace that fails this is a defect, not a thing to keep.
            workspace.checked_target()
            busy = _require_slot_view(config)
            if dry_run:
                reasons = workspace.blockers(here=here, busy=busy)
            else:
                # One gate call, asked with a survey taken moments ago: a
                # snapshot from the top of a long sweep would name an agent
                # that had since started as absent.
                workspace.remove(here=here, busy=busy)
                reasons = []
        except RemovalRefused as refusal:
            reasons = refusal.reasons
        except PartlyRemoved as error:
            # Neither removed nor kept: counting it as kept would tell a
            # script the workspace is still there, which is the one thing
            # it is not.
            print(f"{'damaged':<9}{workspace.name}  partly removed")
            print(f"wt: {error.message}", file=sys.stderr)
            status = 1
            damaged += 1
            continue
        except (WtError, OSError) as error:
            print(f"wt: {_message(error)}", file=sys.stderr)
            status = 1
            kept += 1
            continue
        if reasons:
            print(f"{'kept':<9}{workspace.name}  {reasons[0]}")
            kept += 1
            continue
        print(f"{word:<9}{workspace.name}")
        removed += 1
        emptied.append(workspace.name)

    for group in workspaces.prune_groups(config, emptied, dry_run=dry_run):
        kind = "project" if "/" not in group else "group"
        print(f"{'pruned':<9}{group}  empty {kind}")
    tail = f", {damaged} damaged" if damaged else ""
    print(
        f"{removed} {'to remove' if dry_run else 'removed'}, {kept} kept{tail}"
    )
    return status


def cmd_clean(config: Config, args: list[str]) -> int:
    print(
        "wt: clean is now sweep; clean still works but will stop being "
        "documented",
        file=sys.stderr,
    )
    return cmd_sweep(config, args)


def cmd_rm(config: Config, args: list[str]) -> int:
    force, args = _take_force(args)
    if len(args) != 1:
        raise UsageError("rm needs exactly one workspace")
    workspace = workspaces.select(config, args[0])
    busy = _require_slot_view(config)
    try:
        removed = workspace.remove(force=force, busy=busy)
    except UnsavedWorkError as error:
        for name in error.repositories:
            print(f"unsaved  {name}", file=sys.stderr)
        for reason in error.reasons:
            if not reason.startswith("unsaved:"):
                print(f"also     {reason}", file=sys.stderr)
        raise WtError(
            f"{error.message}; use wt rm --force to discard it"
        ) from error
    print(f"removed  {removed}")
    if len(Path(workspace.name).parts) > 2:
        for group in workspaces.prune_groups(config, [workspace.name]):
            kind = "project" if "/" not in group else "group"
            print(f"{'pruned':<9}{group}  empty {kind}")
    return 0


def agent_environment(
    workspace: workspaces.Workspace, slot: int
) -> dict[str, str]:
    """What `wt` promises an agent it will find in its environment.

    This is package policy, not a detail of the command line: the workspace
    guidance and the personal AI guidance both key on WT_WORKSPACE, so the
    contract belongs somewhere a test or another script can read it.
    """
    return {
        "WT_WORKSPACE": workspace.name,
        "WT_WORKSPACE_DIR": str(workspace.path),
        "WT_BRANCH": workspace.branch,
        "WT_AGENT_SLOT": str(slot),
        # A workspace keeps no work ledger. The workspace root is not a
        # repository, so aiq would otherwise fall back to user scope and
        # capture every prompt of a session that is meant to be disposable.
        "AIQ_DISABLE": "1",
    }


SEED_OPTIONS = ("--seed", "--seed-file")
BRANCH_OPTIONS = ("-b", "--branch")
CLONE_OPTIONS = ("-r", "--clone")
RELAY_OPTION = "--relay"
NEW_OPTION = "--new"
LAUNCH_OPTIONS = (
    *SEED_OPTIONS,
    *BRANCH_OPTIONS,
    *CLONE_OPTIONS,
    RELAY_OPTION,
    NEW_OPTION,
)


def _read_seed(path: str) -> str:
    """The seed prompt held in a file, or on stdin when path is `-`.

    A prompt read from a file never passes through shell quoting, which is
    the whole reason this exists alongside `--seed`: the text a planning
    agent generates is the last thing that should be interpreted by a shell
    on the way to the agent that will act on it.
    """
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).expanduser().read_text(encoding="utf-8")
    except OSError as error:
        raise WtError(f"cannot read the seed prompt: {error}") from error


@dataclass(frozen=True)
class LaunchOptions:
    """What `wt` itself was told about a launch, before the agent's own."""

    seed: str | None = None
    branch: str | None = None
    clones: tuple[clone.CloneSpec, ...] = ()
    relay: str | None = None
    fresh: bool = False


def _take_launch_options(
    args: list[str],
) -> tuple[LaunchOptions, list[str]]:
    """Read wt's own launch options from wherever they were typed.

    Either side of the workspace, because `wt claude telos/demo --seed ...`
    is how anyone would write it: naming the workspace and then saying what
    to do there. `--` ends them, so an agent with a `--seed` or `--new` flag
    of its own is still reachable, the way it is for the fan-out verbs.
    """
    text: str | None = None
    source: str | None = None
    branch: str | None = None
    clones: list[clone.CloneSpec] = []
    relay: str | None = None
    fresh = False
    kept: list[str] = []
    rest = list(args)
    while rest:
        head = rest.pop(0)
        if head == "--":
            kept.extend(rest)
            break
        name, assigned, inline = head.partition("=")
        if name not in LAUNCH_OPTIONS:
            kept.append(head)
            continue
        if name == NEW_OPTION:
            if assigned:
                raise UsageError(f"{NEW_OPTION} takes no value")
            fresh = True
            continue
        if name in BRANCH_OPTIONS:
            wants = "branch"
        elif name in CLONE_OPTIONS:
            wants = "repository"
        elif name == RELAY_OPTION:
            wants = "run pointer"
        else:
            wants = "prompt"
        if assigned and name.startswith("--"):
            value = inline
        elif rest:
            value = rest.pop(0)
        else:
            raise UsageError(f"{name} needs a {wants}")
        if name in BRANCH_OPTIONS:
            if branch is not None:
                raise UsageError("a launch works on one branch, not two")
            branch = value
            continue
        if name in CLONE_OPTIONS:
            # Parsed now, so a name the workspace cannot hold is refused
            # before anything is created.
            clones.append(clone.parse(value))
            continue
        if name == RELAY_OPTION:
            if relay is not None:
                raise UsageError("a launch carries one run pointer, not two")
            relay = value
            continue
        if text is not None:
            raise UsageError(
                f"{source} and {name} name one seed prompt, not two"
            )
        text = value if name == "--seed" else _read_seed(value)
        source = name
    if text is not None:
        # A file or a heredoc almost always ends in a newline that means
        # nothing, and leading blank lines survive copy and paste; neither
        # belongs in the prompt an agent is handed.
        text = text.strip()
        if not text:
            raise UsageError(f"{source} gave an empty seed prompt")
    if relay is not None:
        if text is not None:
            raise UsageError(
                f"{RELAY_OPTION} derives the prompt from the brief it names; "
                f"{source} would give the executor a second one"
            )
        if branch is None:
            raise UsageError(
                f"{RELAY_OPTION} needs the branch the handoff names, as -b"
            )
    return LaunchOptions(
        seed=text,
        branch=branch,
        clones=tuple(clones),
        relay=relay,
        fresh=fresh,
    ), kept


def _restore_terminal_stdin() -> None:
    """Give the agent a terminal back after reading a seed from stdin.

    Reading the prompt from a pipe or a heredoc leaves stdin at end of file,
    and an interactive agent handed an exhausted stdin exits immediately.
    Without a controlling terminal — a script, a hook, CI — there is nothing
    to restore and nothing that wanted it.
    """
    try:
        handle = os.open("/dev/tty", os.O_RDONLY)
    except OSError:
        return
    try:
        os.dup2(handle, sys.stdin.fileno())
    finally:
        os.close(handle)


def _relay_modules():
    """The relay package, or a refusal naming what is missing.

    `wt` is usable without it: only a launch handoff needs the protocol,
    and only the protocol's own package should hold protocol knowledge.
    """
    try:
        from relay import handoff, steps
        from relay.errors import Blocked, RelayError
    except ImportError as error:
        raise WtError(
            f"--relay needs the relay package, which is not importable: "
            f"{error}"
        ) from error
    return handoff, steps, Blocked, RelayError


def _fast_forward(checkout: Path, branch: str) -> None:
    """Catch a checkout up to origin when that is all it needs.

    Strictly behind and nothing of its own: no merge is created, no commit
    is rewritten, and nothing is decided. Anything else is left exactly as
    it is for preflight to stop on.
    """
    remote = f"origin/{branch}"
    ancestor = ("merge-base", "--is-ancestor")
    ahead = gitcmd.read(checkout, *ancestor, remote, "HEAD")
    behind = gitcmd.read(checkout, *ancestor, "HEAD", remote)
    if ahead[0] == 0 or behind[0] != 0:
        return
    status, output = gitcmd.read(checkout, "merge", remote, "--ff-only")
    if status != 0:
        raise WtError(f"cannot fast-forward to {remote}: {output}")
    print(f"synced   fast-forwarded to {remote}", file=sys.stderr)


@dataclass(frozen=True)
class RelayTurn:
    """A claimed relay turn, and the prompt that executes it."""

    brief: object
    checkout: Path
    prompt: str


def open_relay_turn(
    workspace: workspaces.Workspace,
    pointer_text: str,
    branch: str,
    agent: str,
) -> RelayTurn:
    """Do every mechanical step of the turn, and leave only the work.

    The clone comes first because the brief is inside it, and the branch is
    already settled: the handoff names it and the workspace was pinned to
    it before anything was cloned, which is the bootstrap the protocol
    prefers over switching a checkout afterwards. Initialization, preflight
    and the claim then run here rather than being described to an agent —
    they are decidable without judgement, and a step an executor has to
    reconstruct from prose is the step that gets improvised. A stop is
    reported before any session starts, so a failed preflight costs nothing
    but the time to discover it.
    """
    handoff, steps, Blocked, RelayError = _relay_modules()
    brief = None
    try:
        pointer = handoff.parse_pointer(pointer_text)
        if not handoff.TOKEN.match(branch):
            raise WtError(
                f"a launch handoff holds every token to "
                f"{handoff.TOKEN.pattern}, and this branch does not match: "
                f"{branch}"
            )
        spec = clone.parse(pointer.repository)
        if clone.into(workspace.path, spec, workspace.config.forge, branch):
            print(f"cloned   {spec.name}  on {branch}", file=sys.stderr)
        checkout = workspace.path / spec.owner / spec.repo
        status, _ = gitcmd.read(checkout, "fetch", "origin")
        if status != 0:
            raise WtError(f"cannot fetch origin in {checkout}")
        brief = handoff.read_brief(checkout, pointer.sha)
        if brief.branch != branch:
            # The protocol makes the brief the authority and calls this a
            # violation to report, not a difference to reconcile.
            raise WtError(
                f"the handoff names branch {branch} and the brief at "
                f"{pointer.sha} says {brief.branch}"
            )
        steps.initialize(checkout, pointer.repository, branch)
        # Preflight stops on a stale base and says to fast-forward when that
        # is all it is, because divergence found before a turn's work costs
        # nothing and the same divergence found after it is a rebase with
        # conflict risk. `relay preflight` reports rather than mutates, so
        # the pure fast-forward is taken here — and only that one: a branch
        # that has really diverged before any work began is the stop the
        # protocol wants, not something to reconcile.
        _fast_forward(checkout, branch)
        steps.preflight(checkout, pointer.repository, branch, pointer.sha)
        # Asked before claiming, because a claim already at origin is the
        # protocol's proof that the turn is owned, and the local file that
        # came down with the fetch would otherwise stop the run as an
        # ordinary refusal rather than as the token the planner needs.
        owned = f"origin/{branch}:{steps.claim_path(brief.run, brief.claim)}"
        if gitcmd.read(checkout, "cat-file", "-e", owned)[0] == 0:
            raise Blocked(
                "claim-replay",
                f"{steps.claim_path(brief.run, brief.claim)} is already at "
                f"origin, so turn {brief.claim} is owned; report the replay "
                f"and do not redo the work",
            )
        claimed = steps.claim(
            checkout, brief.run, brief.claim, branch, agent
        )
    except Blocked as error:
        raise RelayBlocked(
            brief.run if brief else "?",
            brief.claim if brief else "?",
            error.token,
            error.message,
            relayed=error.relayed,
        ) from error
    except RelayError as error:
        # The relay package raises its own type; a user of `wt` should see
        # a wt: line and an exit status, not a traceback from a package
        # they did not invoke.
        raise WtError(str(error)) from error
    print(f"claimed  {claimed.path}", file=sys.stderr)
    relative = checkout.relative_to(workspace.path)
    return RelayTurn(
        brief=brief,
        checkout=checkout,
        prompt=handoff.prompt(
            brief,
            pointer,
            str(relative),
            agent=agent,
            tool=shutil.which("relay") is not None,
        ),
    )


def launch(config: Config, agent: str, args: list[str]) -> int:
    """Create or reuse the workspace, take a slot, and become the agent.

    A selector that uniquely abbreviates an existing workspace reuses it. A
    name matching nothing is still created, including one a finger-slip away
    from an existing leaf; component-prefix matching does not treat general
    spelling similarity as identity.
    """
    options, args = _take_launch_options(args)
    seed = options.seed
    if not args:
        raise UsageError(f"{agent} needs a workspace")
    if shutil.which(agent) is None:
        raise WtError(f"agent is not installed: {agent}")

    workspace = workspaces.reuse_or_named(config, args[0]).pinned_to(
        options.branch
    )

    # The pool stays referenced for the rest of this process: it owns the open
    # descriptor that holds the slot across the exec below. Take it before
    # creating anything, so a failed launch leaves no empty workspace.
    pool = _pool(config)
    slot = pool.acquire(agent, workspace.name)

    if workspace.create():
        print(f"created  {workspace.path}", file=sys.stderr)
    _clone_specs(workspace, list(options.clones))

    turn = None
    if options.relay is not None:
        turn = open_relay_turn(
            workspace, options.relay, workspace.branch, agent
        )
        brief, seed = turn.brief, turn.prompt
        pool.describe(agent, workspace.name, run=brief.run, turn=brief.claim)
        print(
            f"wt: {brief.protocol} run {brief.run}, brief {brief.turn}, "
            f"claim {brief.claim}, on {brief.branch}",
            file=sys.stderr,
        )

    resuming = not options.fresh and sessions.resumable(
        workspace.path, agent
    )
    if resuming and seed is not None and not sessions.carries_prompt(agent):
        if turn is None:
            raise UsageError(
                f"{agent} cannot be given a seed prompt while resuming its "
                f"previous session in {workspace.name}; use --new for a "
                f"fresh session, or drop the seed"
            )
        # A relay turn has no such choice to offer: the prompt is derived,
        # not typed, and refusing would leave the run with no way to take
        # its next turn under this agent. Every brief is self-sufficient at
        # its pinned commit, which is exactly why the protocol calls
        # `state: resume` a cost hint and not a requirement — so a fresh
        # session is correct here, and the cost is saying so.
        print(
            f"wt: {agent} cannot resume and be given this turn's brief at "
            f"once, so this turn opens a fresh session; the brief is "
            f"self-sufficient at its pinned commit",
            file=sys.stderr,
        )
        resuming = False
    # Recorded before the exec, because after it there is no wt left to
    # record anything. A launch that dies immediately still counts: the
    # agent may well have written a session before it did.
    sessions.record(workspace.path, agent)

    os.environ.update(agent_environment(workspace, slot))
    print(
        f"wt: {agent} in {workspace.path} on {workspace.branch} "
        f"(slot {slot})",
        file=sys.stderr,
    )
    if resuming:
        print(
            f"wt: resuming the previous {agent} session here; --new starts "
            f"a fresh one",
            file=sys.stderr,
        )
    # The prompt itself is never echoed: it can be long, and a handoff it
    # carries is the agent's to read rather than the terminal's to keep.
    if seed is not None:
        print(
            f"wt: seeded with a {len(seed)}-character prompt",
            file=sys.stderr,
        )
        _restore_terminal_stdin()
    sys.stdout.flush()
    sys.stderr.flush()
    # The seed goes last and positional: claude, codex and droid each read a
    # trailing argument as the prompt to open with, so one launch seeds any
    # of them without wt knowing one agent's flags from another's. Resuming
    # is the exception it does have to know.
    command = [
        agent,
        *(sessions.arguments(agent) if resuming else ()),
        *args[1:],
        *([seed] if seed else []),
    ]
    try:
        os.chdir(workspace.path)
        if turn is None:
            os.execvp(agent, command)
        # A relay turn ends in something the user owes the planner, so this
        # launch waits for the agent instead of becoming it. Every other one
        # still execs: an extra process between a terminal and an agent
        # earns its keep only when there is something to say afterwards.
        code = _run_agent(command)
    except OSError as error:
        raise WtError(f"cannot start {agent}: {error}") from error
    _report_turn(turn)
    return code


def _run_agent(command: list[str]) -> int:
    """Run the agent to completion, leaving the terminal and the keys to it.

    Ctrl-C reaches the whole foreground process group, so the agent has it
    too and decides what it means — for most of them, cancel this turn
    rather than end the session. `wt` only has to still be here when the
    session does end, so it waits again instead of abandoning the report.

    Ignoring SIGINT in this process would be worse than useless. SIG_IGN
    survives the exec, so the agent would inherit it and never see the key
    at all; and `subprocess.run` kills the child when a KeyboardInterrupt
    reaches it, which is exactly the session the report is waiting for.
    """
    process = subprocess.Popen(command)
    while True:
        try:
            return process.wait()
        except KeyboardInterrupt:
            continue


def _result_state(turn: RelayTurn) -> str:
    """Whether this turn's result reached origin: yes, no, or unknown.

    Asked rather than assumed, and a fetch that failed is its own answer:
    reading it as "nothing was published" would report an absence this
    never actually looked for. The protocol has the planner read the result
    file itself and never infer an outcome, so this only decides what to
    tell the user to expect.
    """
    if gitcmd.read(turn.checkout, "fetch", "origin")[0] != 0:
        return "unknown"
    reference = f"origin/{turn.brief.branch}:{turn.brief.result_path}"
    status, _ = gitcmd.read(turn.checkout, "cat-file", "-e", reference)
    return "yes" if status == 0 else "no"


_RESULT_WORDING = {
    "yes": "is at origin",
    "no": "is NOT at origin",
    "unknown": "could not be checked, because origin is unreachable",
}


def _report_turn(turn: RelayTurn | None) -> None:
    """What the user owes the planner now that the session has ended.

    The acknowledgement goes to stdout alone so it can be copied without
    the commentary, and it asserts only that the session ended: whether the
    turn succeeded is in the result file, which the planner reads itself.
    """
    if turn is None:
        return
    brief = turn.brief
    landed = _result_state(turn)
    # Interleaved on purpose, so the lines read in order on a terminal: our
    # stderr is unbuffered and our stdout is not, and the acknowledgement
    # would otherwise arrive after the sentence about it.
    print(
        f"\nwt: the {brief.protocol} session for run {brief.run} has ended, "
        f"and {brief.result_path} {_RESULT_WORDING[landed]}. "
        f"Tell the planner:",
        file=sys.stderr,
    )
    sys.stderr.flush()
    print(f"done {brief.run} {brief.claim}")
    sys.stdout.flush()
    if landed == "no":
        print(
            "wt: the turn published nothing, so the planner will ask for "
            "the executor's `relay blocked ...` line; relay that verbatim "
            "instead if there was one.",
            file=sys.stderr,
        )


Verb = Callable[[Config, list[str]], int]

VERBS: dict[str, Verb] = {
    "ls": cmd_ls,
    "list": cmd_ls,
    "new": cmd_new,
    "path": cmd_path,
    "pwd": cmd_pwd,
    "branch": cmd_branch,
    "clone": cmd_clone,
    "git": cmd_git,
    "exec": cmd_exec,
    "status": cmd_status,
    "log": cmd_log,
    "fetch": cmd_fetch,
    "sync": cmd_sync,
    # Not an alias for sync: sync rebases, and pointing an old habit at a
    # history rewrite without asking is not a rename.
    "pull": cmd_pull,
    "push": cmd_push,
    "agents": cmd_agents,
    "check": cmd_check,
    "tidy": cmd_tidy,
    "sweep": cmd_sweep,
    "clean": cmd_clean,
    "rm": cmd_rm,
}


def _message(error: Exception) -> str:
    return getattr(error, "message", str(error))


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
        # A leading seed option is a launch under $WT_AGENT that has not
        # reached its workspace yet; launch owns the parsing.
        if command.partition("=")[0] in LAUNCH_OPTIONS:
            return launch(config, config.agent, argv)
        raise UsageError(f"unknown option: {command}")
    close = difflib.get_close_matches(command, VERBS, n=1, cutoff=0.8)
    if close and "/" not in command:
        # Otherwise `wt satus demo/x` creates a workspace called `satus` and
        # runs the agent in it, with the workspace you meant as an argument.
        raise UsageError(f"unknown verb: {command}; did you mean {close[0]}?")
    return launch(config, config.agent, argv)


def main(argv: list[str] | None = None, config: Config | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        code = dispatch(config or Config.from_env(), arguments)
        # Flush inside the guard: a short answer stays in the buffer until
        # the interpreter exits, and a reader that has already gone away
        # would otherwise surface as an unhandled BrokenPipeError during
        # that final flush, with a noisy message and a useless exit code.
        sys.stdout.flush()
        return code
    except UsageError as error:
        print(f"wt: {error.message}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return error.exit_code
    except RelayBlocked as error:
        # Exactly one line on stdout, because that line is the whole of
        # what the user is permitted to carry back. A stop the protocol's
        # blocked channel does not name is spelled differently on purpose,
        # so it is never relayed as one of its tokens.
        if error.relayed:
            print(error.line)
        else:
            print(f"wt: stopped: {error.token}", file=sys.stderr)
        sys.stdout.flush()
        print(f"wt: {error.message}", file=sys.stderr)
        return error.exit_code
    except WtError as error:
        print(f"wt: {error.message}", file=sys.stderr)
        return error.exit_code
    except BrokenPipeError:
        # `wt ls | head` closes the pipe early; say nothing and leave the
        # interpreter no stdout to flush on the way out.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    except OSError as error:
        # A vanished cwd, an over-long name, an unreadable tree: the user
        # gets a wt: line, not a traceback.
        print(f"wt: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
