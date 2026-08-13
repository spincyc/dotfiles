"""Workspace creation, listing, resolution, and disposal.

One rule shapes this module: every path that removes a *workspace* goes
through `Workspace.blockers`, and nothing removes one the gate has not just
answered for. `tidy` is deliberately outside it — it deletes only what the
clones themselves call disposable, and never the workspace. `wt rm` and `wt sweep` used to ask different questions — rm
checked two conditions, the sweep checked five, and the sweep asked them up
to a whole sweep before it acted — so the two disagreed about what was
disposable and the sweep acted on facts that had since changed.
"""

import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from . import branches, guidance, names, repos, scratch, slots
from .config import Config
from .errors import (
    PartlyRemoved,
    RemovalRefused,
    UnsavedWorkError,
    UsageError,
    WtError,
)

# What `tidy` reports about each path it considered.
REMOVED = "removed"
TRACKED = "tracked"
SKIPPED = "skipped"
NESTED = "nested"
FAILED = "failed"

Step = tuple[str, str]
OnStep = Callable[[str, str], None]


@dataclass(frozen=True)
class Inventory:
    """Everything a workspace directory holds, classified once.

    `checks` and the disposal gate both need to know what a workspace is
    made of, and they used to derive it separately with rules that had
    already drifted apart. This is the one answer both read.
    """

    clones: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    strays: list[str] = field(default_factory=list)
    nested: list[str] = field(default_factory=list)
    # A directory wt could not read holds an unknown amount of work, which
    # is not the same as holding none. Without this the removal gate reads
    # an unreadable workspace as empty and deletes it.
    readable: bool = True


@dataclass(frozen=True)
class Workspace:
    """One ``<project>/<slug>`` directory below the workspace root."""

    name: str
    config: Config

    @property
    def path(self) -> Path:
        return self.config.root / self.name

    @property
    def project(self) -> str:
        return names.split_workspace(self.name)[0]

    @property
    def slug(self) -> str:
        return names.split_workspace(self.name)[1]

    @property
    def branch(self) -> str:
        """The branch every clone in this workspace commits to."""
        return branches.name(self.config.branch_prefix, self.slug)

    def exists(self) -> bool:
        return self.path.is_dir()

    def require(self) -> Path:
        if not self.exists():
            raise WtError(f"no such workspace: {self.name} ({self.path})")
        return self.path

    def create(self, force_guidance: bool = False) -> bool:
        """Create the workspace if needed and give it guidance.

        Returns True when the directory itself was created.
        """
        if not names.valid_branch(self.branch):
            # Asked once, here, about the string that actually becomes the
            # branch — the slug alone is not it, and a prefix git dislikes
            # would otherwise pass unexamined. Refused now it costs a
            # retyped name; discovered later it costs a directory full of
            # clones stuck on whatever branch they arrived on.
            raise WtError(f"not a usable branch name: {self.branch}")
        _ensure_directory(self.config.root)
        _ensure_directory(self.config.root / self.project)
        created = not self.path.exists()
        _ensure_directory(self.path)
        guidance.write(self.path, self.name, self.branch, force=force_guidance)
        return created

    def repo_names(self) -> list[str]:
        return repos.discover(self.path)

    def statuses(self) -> list[repos.RepoStatus]:
        return [repos.status(self.path, name) for name in self.repo_names()]

    def has_unsaved_work(self) -> list[str]:
        """The repositories that would lose work if this were removed."""
        return [
            name
            for name in self.repo_names()
            if repos.has_unsaved_work(self.path / name)
        ]

    def inventory(self) -> Inventory:
        return inventory(self)

    def unaccounted(self) -> list[str]:
        """Everything in the workspace `wt` cannot explain, sorted."""
        return self.inventory().strays

    def checked_target(self) -> Path:
        """The workspace directory, proven to be the one `wt` owns.

        Every destructive verb goes through here: an intermediate symlink
        would otherwise let a workspace name reach any directory at all.
        The path comes back resolved, because a caller that compares it
        against a resolved child — as tidy does — must not be handed one
        side of the comparison unresolved.
        """
        target = self.require()
        names.assert_owned_directory(target)
        resolved = target.resolve()
        expected = self.config.root.resolve() / self.name
        if resolved != expected:
            raise WtError(
                f"refusing to touch a path resolving outside "
                f"{self.config.root}: {target}"
            )
        return resolved

    def blockers(
        self,
        here: "Workspace | None" = None,
        busy: slots.BusyAgents | None = None,
        force: bool = False,
        cwd: Path | None = None,
    ) -> list[str]:
        """Every reason not to delete this workspace, cheapest question first."""
        return self._gate(here=here, busy=busy, force=force, cwd=cwd)[0]

    def _gate(
        self,
        here: "Workspace | None" = None,
        busy: slots.BusyAgents | None = None,
        force: bool = False,
        cwd: Path | None = None,
    ) -> tuple[list[str], list[str]]:
        """The reasons not to delete this, and the repositories holding work.

        Asked once and answered once: walking the clones is the expensive
        half, and `remove` needs both the verdict and the names behind it.

        The order matters for more than speed. A workspace holding a running
        agent is never asked to walk its clones, so a sweep cannot be slowed
        or confused by a tree that is being written to as it looks.

        `force` waives the two questions about the user's own work. It never
        waives standing in the directory or an agent running in it, because
        neither is the caller's to discard.
        """
        reasons: list[str] = []

        target = self.path.resolve() if self.exists() else self.path
        try:
            current = (cwd or Path.cwd()).resolve()
        except OSError:
            # A shell left in a directory something else removed is nowhere,
            # which is not the same as being somewhere safe.
            current = target
        if current == target or target in current.parents:
            reasons.append("the current directory")
        elif here is not None and here.name == self.name:
            reasons.append("the current directory")

        if busy is not None and busy.holds(self.name):
            reasons.append("an agent is running here")

        if reasons or force:
            # Nothing below can be waived by anything above, and a busy or
            # current workspace has already earned its keep.
            return reasons, []

        found = self.inventory()
        if not found.readable:
            reasons.append("wt cannot read this directory")
            return reasons, []

        unsaved = self.has_unsaved_work()
        if unsaved:
            reasons.append(f"unsaved: {' '.join(unsaved)}")
        if found.strays:
            reasons.append(f"not from wt: {' '.join(found.strays)}")
        if found.nested:
            # `git clean` refuses to recurse into a nested repository and
            # rmtree has no such scruple, so the gate has to supply the
            # caution. The unsaved-work oracle cannot always see these: a
            # clone under an ignored *parent* is collapsed to the parent by
            # git's own listing.
            reasons.append(f"holds a repository: {' '.join(found.nested)}")
        return reasons, unsaved

    def tidy(
        self,
        dry_run: bool = False,
        on_step: OnStep | None = None,
    ) -> list[Step]:
        """Delete the transient files, keeping the workspace itself.

        Returns every step taken, and calls `on_step` as each one happens so
        a caller can report in real time. It is deliberately not a generator:
        a generator that is built and never drained deletes nothing and
        raises nothing, and the safety check would not even run.
        """
        steps: list[Step] = []

        def record(kind: str, path: str) -> None:
            steps.append((kind, path))
            if on_step is not None:
                on_step(kind, path)

        target = self.checked_target()

        if scratch.present(target):
            nested = scratch.repositories_under(target / scratch.NAME)
            if nested:
                record(NESTED, f"{scratch.NAME}")
            else:
                if not dry_run:
                    scratch.remove(target / scratch.NAME)
                record(REMOVED, scratch.NAME)

        for name in self.repo_names():
            try:
                self._tidy_repo(target, name, dry_run, record)
            except (WtError, OSError) as error:
                # One clone that cannot be tidied is that clone's problem.
                # Abandoning its siblings left the rest of the workspace
                # dirty for a reason nothing had reported against them.
                record(FAILED, f"{name}: {error}")
        return steps

    def _tidy_repo(
        self, target: Path, name: str, dry_run: bool, record: OnStep
    ) -> None:
        """Tidy one clone, raising only about that clone."""
        repo = target / name
        # discover follows symlinks, and git would happily clean a
        # repository the workspace only points at. Both sides of this
        # comparison are resolved; comparing a resolved child against an
        # unresolved parent called every clone a symlink whenever any
        # directory above the root was one.
        if repo.is_symlink() or repo.resolve() != target / name:
            record(SKIPPED, name)
            return
        if not dry_run:
            # A clone made by hand never got the exclusion; give it one
            # before its scratch directory can dirty the repository.
            scratch.ensure_exclude(repo, root=target)
        if scratch.present(repo):
            nested = scratch.repositories_under(repo / scratch.NAME)
            if scratch.tracked(repo):
                record(TRACKED, f"{name}/{scratch.NAME}")
            elif nested:
                # A checkout under .scratch is work no clone reports and
                # git clean would never have taken.
                record(NESTED, f"{name}/{scratch.NAME}")
            else:
                if not dry_run:
                    scratch.remove(repo / scratch.NAME)
                record(REMOVED, f"{name}/{scratch.NAME}")
        # Streamed, so a clean that dies partway still accounts for the
        # paths it had already taken.
        for path in scratch.clean_ignored(repo, dry_run):
            record(REMOVED, f"{name}/{path}")

    def remove(
        self,
        force: bool = False,
        cwd: Path | None = None,
        busy: slots.BusyAgents | None = None,
        here: "Workspace | None" = None,
    ) -> Path:
        """Delete the workspace, refusing anything unsafe or unsaved.

        The gate runs here, immediately before the tree goes, so a sweep
        that decided a workspace was disposable minutes ago cannot act on
        an answer that has since changed.
        """
        resolved = self.checked_target()

        reasons, unsaved = self._gate(
            here=here, busy=busy, force=force, cwd=cwd
        )
        if unsaved:
            # Named separately so the caller can list the repositories, even
            # when something else is also holding the workspace open.
            raise UnsavedWorkError(self.name, unsaved, reasons)
        if reasons:
            raise RemovalRefused(self.name, reasons)

        # rmtree deletes everything it can before raising, so a refusal
        # partway through leaves a gutted tree. Saying only "could not
        # remove" would describe that as though nothing had happened.
        refused: list[str] = []

        def note(function, path, excinfo) -> None:
            refused.append(str(path))

        shutil.rmtree(resolved, onexc=note)
        if refused:
            raise PartlyRemoved(self.name, refused)
        return resolved


def inventory(workspace: Workspace) -> Inventory:
    """Classify everything in a workspace directory, once.

    A sweep decides a workspace is disposable from the state of the clones
    it can find, so anything it cannot find has to stop it: a repository
    cloned to the wrong depth, or a file an agent left at the top instead of
    under `.scratch`, is work no clone reports.
    """
    target = workspace.require()
    clones = workspace.repo_names()
    owners = sorted({name.split("/")[0] for name in clones})
    known = set(clones)
    strays: list[str] = []
    nested: list[str] = []

    try:
        entries = sorted(target.iterdir(), key=lambda item: item.name)
    except OSError:
        return Inventory(clones=clones, owners=owners, readable=False)

    for entry in entries:
        name = entry.name
        if name in guidance.FILENAMES:
            continue
        if name == scratch.NAME or entry.is_symlink():
            # A symlink holds nothing; removing it loses no work.
            continue
        if not entry.is_dir() or name not in set(owners):
            strays.append(name)
            continue
        try:
            children = sorted(entry.iterdir(), key=lambda item: item.name)
        except OSError:
            # Unreadable, so its contents are unknown; naming it as a stray
            # is what keeps a sweep off it.
            strays.append(name)
            continue
        strays += [
            f"{name}/{child.name}"
            for child in children
            if f"{name}/{child.name}" not in known
        ]

    for name in clones:
        if repos.discover(target / name):
            nested.append(name)

    return Inventory(
        clones=clones, owners=owners, strays=strays, nested=nested
    )


def _ensure_directory(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True)
        path.chmod(0o755)
    names.assert_owned_directory(path)


def named(config: Config, value: str) -> Workspace:
    """Build a Workspace from a user-supplied name."""
    return Workspace(names.normalize_workspace(value, config.project), config)


def listing(config: Config) -> list[Workspace]:
    """Every existing workspace, in project then slug order."""
    root = config.root
    if not root.is_dir():
        return []
    found: list[Workspace] = []
    for project in _sorted_dirs(root, skip_dotted=True):
        for slug in _sorted_dirs(project, skip_dotted=True):
            found.append(Workspace(f"{project.name}/{slug.name}", config))
    return found


def _sorted_dirs(parent: Path, skip_dotted: bool = False) -> list[Path]:
    """Directories under parent, sorted, tolerating an unreadable one."""
    try:
        entries = [entry for entry in parent.iterdir() if entry.is_dir()]
    except OSError:
        return []
    if skip_dotted:
        entries = [e for e in entries if not e.name.startswith(".")]
    return sorted(entries, key=lambda entry: entry.name)


def prune_projects(
    config: Config,
    projects: Iterable[str],
    cwd: Path | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Remove the named project directories, if emptied. Returns those gone.

    A project is only a grouping directory, so one holding no workspace
    carries no information; `wt new` recreates it the moment it is named
    again. Only the projects a caller has just emptied are considered: an
    empty project directory someone else made is not this command's business.
    """
    here = (cwd or Path.cwd()).resolve()
    pruned: list[str] = []
    for name in sorted(set(projects)):
        project = config.root / name
        if project.is_symlink() or not project.is_dir():
            continue
        # Standing in a project directory is not standing in a workspace,
        # so nothing else stops this one from vanishing underfoot.
        if project.resolve() == here:
            continue
        try:
            if any(project.iterdir()):
                continue
            if not dry_run:
                project.rmdir()
        except OSError:
            continue
        pruned.append(name)
    return pruned


def current(config: Config, cwd: Path | None = None) -> Workspace | None:
    """The workspace containing cwd, if any."""
    try:
        here = cwd or Path.cwd()
    except OSError:
        # A shell left standing in a directory another `wt rm` removed is
        # not inside a workspace; it is nowhere.
        return None
    name = names.workspace_from_path(here, config.root)
    return Workspace(name, config) if name else None


def resolve(
    config: Config, args: list[str], cwd: Path | None = None
) -> tuple[Workspace, list[str]]:
    """Split a verb's arguments into its workspace and the rest.

    The first argument is the workspace when it names an existing workspace,
    or when the current directory is not inside one. Otherwise the current
    workspace is used and every argument belongs to the verb.
    """
    if args and args[0] != "--" and not args[0].startswith("-"):
        try:
            candidate = named(config, args[0])
        except WtError:
            candidate = None
        if candidate is not None and candidate.exists():
            return candidate, args[1:]

    here = current(config, cwd)
    if here is not None:
        return here, args

    if not args or args[0] == "--" or args[0].startswith("-"):
        # Not knowing which workspace to act on is a usage problem, the same
        # as giving a verb too many arguments. Naming one that is not there
        # is a different fact and keeps its own exit code.
        raise UsageError(
            f"no workspace given and {cwd or Path.cwd()} is not inside "
            f"{config.root}"
        )
    return named(config, args[0]), args[1:]


def workspace_reference(config: Config, value: str) -> bool:
    """True when value is shaped like a workspace name rather than a verb arg.

    `wt clone` and `wt git` take free-form arguments that can look exactly
    like a workspace, so naming one that does not exist used to fall through
    silently and act on the current workspace instead.
    """
    if "/" not in value or value.startswith("-"):
        return False
    try:
        names.normalize_workspace(value, config.project)
    except WtError:
        return False
    return True
