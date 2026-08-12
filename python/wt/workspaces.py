"""Workspace creation, listing, and resolution."""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from . import branches, guidance, names, repos, scratch
from .config import Config
from .errors import UnsavedWorkError, WtError


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

    def unaccounted(self) -> list[str]:
        """Everything in the workspace `wt` cannot explain, sorted.

        A sweep decides a workspace is disposable from the state of the
        clones it can find, so anything it cannot find has to stop it: a
        repository cloned to the wrong depth, or a file an agent left at the
        top instead of under `.scratch`, is work no clone reports.
        """
        target = self.require()
        clones = set(self.repo_names())
        owners = {name.split("/")[0] for name in clones}
        strays: list[str] = []
        for entry in sorted(target.iterdir(), key=lambda item: item.name):
            name = entry.name
            if name in guidance.FILENAMES:
                continue
            if name == scratch.NAME or entry.is_symlink():
                # A symlink holds nothing; removing it loses no work.
                continue
            if not entry.is_dir() or name not in owners:
                strays.append(name)
                continue
            strays += [
                f"{name}/{child.name}"
                for child in sorted(
                    entry.iterdir(), key=lambda item: item.name
                )
                if f"{name}/{child.name}" not in clones
            ]
        return strays

    def tidy(self, dry_run: bool = False) -> Iterator[tuple[str, str]]:
        """Delete the transient files, keeping the workspace itself.

        Yields ("removed", path) as each path goes and ("tracked", path) for
        a `.scratch` Git tracks, which is left where it is. Yielding as the
        work happens is what keeps the account honest when a later
        repository fails.
        """
        target = self.checked_target()

        if scratch.present(target):
            if not dry_run:
                scratch.remove(target / scratch.NAME)
            yield "removed", scratch.NAME

        for name in self.repo_names():
            repo = target / name
            # discover follows symlinks, and git would happily clean a
            # repository the workspace only points at.
            if repo.is_symlink() or repo.resolve() != target / name:
                yield "skipped", name
                continue
            if not dry_run:
                # A clone made by hand never got the exclusion; give it one
                # before its scratch directory can dirty the repository.
                scratch.ensure_exclude(repo)
            if scratch.present(repo):
                committed = scratch.tracked(repo)
                if committed:
                    yield "tracked", f"{name}/{scratch.NAME}"
                else:
                    if not dry_run:
                        scratch.remove(repo / scratch.NAME)
                    yield "removed", f"{name}/{scratch.NAME}"
            for path in scratch.clean_ignored(repo, dry_run):
                yield "removed", f"{name}/{path}"

    def checked_target(self) -> Path:
        """The workspace directory, proven to be the one `wt` owns.

        Every destructive verb goes through here: an intermediate symlink
        would otherwise let a workspace name reach any directory at all.
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
        return target

    def remove(self, force: bool = False, cwd: Path | None = None) -> Path:
        """Delete the workspace, refusing anything unsafe or unsaved."""
        resolved = self.checked_target().resolve()

        here = (cwd or Path.cwd()).resolve()
        if here == resolved or resolved in here.parents:
            raise WtError(
                f"refusing to remove the current directory; cd out of "
                f"{resolved}"
            )

        if not force:
            unsaved = self.has_unsaved_work()
            if unsaved:
                raise UnsavedWorkError(self.name, unsaved)

        shutil.rmtree(resolved)
        return resolved


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
    for project in sorted(
        entry
        for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    ):
        for slug in sorted(
            entry for entry in project.iterdir() if entry.is_dir()
        ):
            found.append(Workspace(f"{project.name}/{slug.name}", config))
    return found


def prune_projects(config: Config, projects: Iterable[str]) -> list[str]:
    """Remove the named project directories, if emptied. Returns those gone.

    A project is only a grouping directory, so one holding no workspace
    carries no information; `wt new` recreates it the moment it is named
    again. Only the projects a caller has just emptied are considered: an
    empty project directory someone else made is not this command's business.
    """
    here = Path.cwd().resolve()
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
            project.rmdir()
        except OSError:
            continue
        pruned.append(name)
    return pruned


def current(config: Config, cwd: Path | None = None) -> Workspace | None:
    """The workspace containing cwd, if any."""
    name = names.workspace_from_path(cwd or Path.cwd(), config.root)
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
        raise WtError(
            f"no workspace given and {cwd or Path.cwd()} is not inside "
            f"{config.root}"
        )
    return named(config, args[0]), args[1:]
