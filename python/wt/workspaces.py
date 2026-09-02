"""Workspace creation, listing, resolution, and disposal.

One rule shapes this module: every path that removes a *workspace* goes
through `Workspace.blockers`, and nothing removes one the gate has not just
answered for. `tidy` is deliberately outside it — it deletes only what the
clones themselves call disposable, and never the workspace. `wt rm` and `wt sweep` used to ask different questions — rm
checked two conditions, the sweep checked five, and the sweep asked them up
to a whole sweep before it acted — so the two disagreed about what was
disposable and the sweep acted on facts that had since changed.
"""

import re
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import branches, guidance, names, repos, scratch, sessions, slots
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

# New workspaces carry an unambiguous marker so stacked group directories do
# not look like legacy two-component workspaces. Older workspaces are still
# recognised by their established depth and guidance files.
MARKER = ".wt-workspace"
MARKER_VERSION = "wt-workspace-v1"
MARKER_CONTENT = f"{MARKER_VERSION}\n"
MARKER_BRANCH = "branch"
GROUP_MARKER = ".wt-group"
GROUP_MARKER_CONTENT = "wt-group-v1\n"


def marker_text(branch: str | None) -> str:
    """The marker a workspace carries, naming a branch it was pinned to.

    A workspace normally works on `<prefix>/<slug>`, which is derived and
    needs no recording. One pinned to a branch someone else named — the
    branch a relay run was opened on, say — has nothing to derive it from,
    so the marker is where it lives: every verb that judges a clone reads
    the branch from the same place, rather than each deriving a name the
    clones are not on.
    """
    if branch is None:
        return MARKER_CONTENT
    return f"{MARKER_VERSION}\n{MARKER_BRANCH}: {branch}\n"


def read_marker(path: Path) -> str | None:
    """The branch a workspace marker pins, or None when it pins none.

    Raises on anything this `wt` does not recognise. A workspace whose
    branch cannot be read is one whose clones cannot be judged, and falling
    back to `<prefix>/<slug>` for it would report the wrong upstream, push
    the wrong branch, and let a sweep read unsaved work as saved.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise WtError(f"cannot read wt marker {path}: {error}") from error
    lines = content.splitlines()
    if not lines or lines[0] != MARKER_VERSION:
        raise WtError(f"unrecognised wt marker: {path}")
    branch: str | None = None
    for line in lines[1:]:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or key.strip() != MARKER_BRANCH:
            raise WtError(f"unrecognised wt marker: {path}")
        branch = value.strip()
        # Cheaply, because this is read on every question about the
        # workspace; the full reference rules are asked once, on the way in.
        if not branch or branch.split() != [branch]:
            raise WtError(f"wt marker names an unusable branch: {path}")
    return branch


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
    """One ``<project>/<slug>[/<child>...]`` workspace leaf."""

    name: str
    config: Config
    # A branch the caller named on this invocation, before the workspace
    # exists to have recorded one. It is what `create` writes down.
    pin: str | None = None

    @property
    def path(self) -> Path:
        return self.config.root / self.name

    def pinned_to(self, branch: str | None) -> "Workspace":
        """The same workspace, working on a branch the caller named."""
        return replace(self, pin=branch)

    def recorded_branch(self) -> str | None:
        """The branch this workspace's marker pins, if it pins one."""
        marker = self.path / MARKER
        if marker.is_symlink() or not marker.is_file():
            return None
        return read_marker(marker)

    @property
    def project(self) -> str:
        return names.split_workspace(self.name)[0]

    @property
    def slug(self) -> str:
        return names.split_workspace(self.name)[1]

    @property
    def branch(self) -> str:
        """The branch every clone in this workspace commits to."""
        return (
            self.pin
            or self.recorded_branch()
            or branches.name(self.config.branch_prefix, self.slug)
        )

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
        if (
            (self.path / GROUP_MARKER).exists()
            and not (self.path / MARKER).exists()
        ):
            raise WtError(
                f"{self.name} is a stack group; name a workspace leaf below it"
            )
        if self.pin is not None and self.exists():
            # Which branch a workspace works on is decided when it is
            # created. Changing it afterwards would leave the clones already
            # in it on a branch nothing here names any more.
            settled = self.recorded_branch() or branches.name(
                self.config.branch_prefix, self.slug
            )
            if settled != self.pin:
                raise WtError(
                    f"{self.name} already works on {settled}, not "
                    f"{self.pin}; a branch is chosen when the workspace is"
                )
        if not names.valid_branch(self.branch):
            # Asked once, here, about the string that actually becomes the
            # branch — the slug alone is not it, and a prefix git dislikes
            # would otherwise pass unexamined. Refused now it costs a
            # retyped name; discovered later it costs a directory full of
            # clones stuck on whatever branch they arrived on.
            raise WtError(f"not a usable branch name: {self.branch}")
        created = not self.path.exists()
        current = self.config.root
        _ensure_directory(current)
        components = Path(self.name).parts
        for index, component in enumerate(components):
            current /= component
            _ensure_directory(current)
            if 0 < index < len(components) - 1:
                if (current / MARKER).exists() or any(
                    (current / item).exists() for item in guidance.FILENAMES
                ):
                    parent = "/".join(components[: index + 1])
                    raise WtError(
                        f"cannot stack {self.name} under workspace {parent}; "
                        "use an intermediate group"
                    )
                _write_control_file(
                    current, GROUP_MARKER, GROUP_MARKER_CONTENT
                )
        _write_marker(self.path, self.pin)
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
        if name in guidance.FILENAMES or name in (
            MARKER,
            GROUP_MARKER,
            sessions.RECORD,
        ):
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


def _write_marker(directory: Path, pin: str | None) -> None:
    """Write the workspace marker, or leave an existing one agreeing with it.

    Unlike the group marker this one carries a value, so it is validated by
    reading rather than by comparing bytes: a workspace pinned to a branch
    and one that derives its own both have to keep their marker across every
    later `wt new`.
    """
    marker = directory / MARKER
    if marker.is_symlink():
        raise WtError(f"wt marker must not be a symlink: {marker}")
    if marker.exists():
        if not marker.is_file():
            raise WtError(f"wt marker is not a file: {marker}")
        recorded = read_marker(marker)
        if pin is not None and recorded != pin and recorded is not None:
            raise WtError(f"{marker} already names {recorded}, not {pin}")
        if recorded is not None or pin is None:
            return
    marker.write_text(marker_text(pin), encoding="utf-8")


def _write_control_file(directory: Path, name: str, expected: str) -> None:
    """Write or validate a wt marker without following a link."""
    marker = directory / name
    if marker.is_symlink():
        raise WtError(f"wt marker must not be a symlink: {marker}")
    if marker.exists():
        if not marker.is_file():
            raise WtError(f"wt marker is not a file: {marker}")
        try:
            content = marker.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise WtError(
                f"cannot read wt marker {marker}: {error}"
            ) from error
        if content != expected:
            raise WtError(f"unrecognised wt marker: {marker}")
        return
    marker.write_text(expected, encoding="utf-8")


def named(config: Config, value: str) -> Workspace:
    """Build a Workspace from a user-supplied name."""
    return Workspace(names.normalize_workspace(value, config.project), config)


def listing(config: Config) -> list[Workspace]:
    """Every existing workspace leaf, in full-name order.

    Markers make arbitrary-depth leaves explicit. A two-component directory
    without a marker remains a legacy workspace unless it is only the group
    holding one or more marked descendants.
    """
    root = config.root
    if not root.is_dir():
        return []
    marked: set[str] = set()
    legacy: list[tuple[str, Path]] = []

    def walk(directory: Path, parts: tuple[str, ...]) -> None:
        for entry in _sorted_dirs(directory, skip_dotted=True):
            relative = (*parts, entry.name)
            name = "/".join(relative)
            if len(relative) == 2:
                legacy.append((name, entry))
            if entry.is_symlink():
                # Keep a legacy symlink visible so checks and destructive
                # verbs can refuse it, but never walk through it.
                continue
            # Never enter a clone. Besides being expensive, a repository may
            # legitimately contain a file with the same marker name.
            if (entry / ".git").exists():
                continue
            marker = entry / MARKER
            if marker.exists() or marker.is_symlink():
                marked.add(name)
            walk(entry, relative)

    walk(root, ())
    found = set(marked)
    for name, directory in legacy:
        if directory.is_symlink():
            found.add(name)
            continue
        has_marked_child = any(item.startswith(f"{name}/") for item in marked)
        has_guidance = any(
            (directory / item).exists() for item in guidance.FILENAMES
        )
        is_group = (directory / GROUP_MARKER).exists()
        if (not has_marked_child and not is_group) or has_guidance:
            found.add(name)
    return [Workspace(name, config) for name in sorted(found)]


def _sorted_dirs(parent: Path, skip_dotted: bool = False) -> list[Path]:
    """Directories under parent, sorted, tolerating an unreadable one."""
    try:
        entries = [entry for entry in parent.iterdir() if entry.is_dir()]
    except OSError:
        return []
    if skip_dotted:
        entries = [e for e in entries if not e.name.startswith(".")]
    return sorted(entries, key=lambda entry: entry.name)


def prune_groups(
    config: Config,
    workspace_names: Iterable[str],
    cwd: Path | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Remove empty ancestors of workspace leaves that were just removed.

    Only ancestors of named leaves are considered. A stack group is removed
    only when its sole remaining entry is wt's group marker; a project only
    when truly empty. Unrelated empty directories remain outside this action.
    """
    if dry_run:
        # The workspace leaves still exist during a dry-run, so no ancestor
        # is empty in the state being inspected.
        return []
    here = (cwd or Path.cwd()).resolve()
    candidates: set[str] = set()
    for workspace_name in workspace_names:
        parts = Path(workspace_name).parts
        for length in range(len(parts) - 1, 0, -1):
            candidates.add("/".join(parts[:length]))

    pruned: list[str] = []
    for name in sorted(
        candidates, key=lambda item: (-len(Path(item).parts), item)
    ):
        group = config.root / name
        if group.is_symlink() or not group.is_dir():
            continue
        if group.resolve() == here:
            continue
        try:
            entries = list(group.iterdir())
            marker = group / GROUP_MARKER
            if (
                entries == [marker]
                and marker.is_file()
                and not marker.is_symlink()
            ):
                if (
                    marker.read_text(encoding="utf-8")
                    != GROUP_MARKER_CONTENT
                ):
                    continue
                marker.unlink()
                entries = []
            if entries:
                continue
            group.rmdir()
        except (OSError, UnicodeError):
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
    found = listing(config)
    name = names.workspace_from_path(
        here, config.root, (workspace.name for workspace in found)
    )
    return Workspace(name, config) if name else None


def _selector_key(value: str) -> tuple[str, ...]:
    """Case- and separator-insensitive components for a selector."""
    return tuple(
        re.sub(r"[-_.]+", "", component).casefold()
        for component in value.rstrip("/").split("/")
    )


def _component_abbreviates(typed: str, candidate: str) -> bool:
    """True when one path component is a readable prefix abbreviation."""
    typed_key = _selector_key(typed)[0]
    candidate_key = _selector_key(candidate)[0]
    if candidate_key.startswith(typed_key):
        return True
    typed_words = re.split(r"[-_.]+", typed.casefold())
    candidate_words = re.split(r"[-_.]+", candidate.casefold())
    return len(typed_words) == len(candidate_words) and all(
        candidate_word.startswith(typed_word)
        for typed_word, candidate_word in zip(
            typed_words, candidate_words, strict=True
        )
    )


def _aliases(workspace: Workspace) -> tuple[str, ...]:
    """The full name, branch, slug stack, and leaf accepted for a workspace."""
    return (
        workspace.name,
        workspace.branch,
        workspace.slug,
        workspace.slug.rpartition("/")[2],
    )


def _matches(
    config: Config, value: str, abbreviate: bool = True
) -> list[Workspace]:
    """Existing workspaces selected by an exact alias or component prefix."""
    found = listing(config)
    wanted = value.rstrip("/")
    if not wanted:
        return []

    # A literal full workspace name always wins over aliases. This keeps a
    # project actually named like the configured branch prefix addressable.
    literal = [workspace for workspace in found if workspace.name == wanted]
    if literal:
        return literal

    wanted_key = _selector_key(wanted)
    full_key = [
        workspace
        for workspace in found
        if _selector_key(workspace.name) == wanted_key
    ]
    if full_key:
        return full_key

    exact = {
        workspace.name: workspace
        for workspace in found
        if wanted in _aliases(workspace)
    }
    if exact:
        return sorted(exact.values(), key=lambda workspace: workspace.name)

    canonical = {
        workspace.name: workspace
        for workspace in found
        if any(
            _selector_key(alias) == wanted_key for alias in _aliases(workspace)
        )
    }
    if canonical or not abbreviate:
        return sorted(canonical.values(), key=lambda workspace: workspace.name)

    wanted_parts = wanted.split("/")
    abbreviated = {
        workspace.name: workspace
        for workspace in found
        if any(
            len(alias_parts := alias.split("/")) == len(wanted_parts)
            and all(
                _component_abbreviates(typed, candidate)
                for typed, candidate in zip(
                    wanted_parts, alias_parts, strict=True
                )
            )
            for alias in _aliases(workspace)
        )
    }
    return sorted(abbreviated.values(), key=lambda workspace: workspace.name)


def select(
    config: Config, value: str, abbreviate: bool = True
) -> Workspace:
    """Resolve one existing workspace from a forgiving, unambiguous selector."""
    matched = _matches(config, value, abbreviate=abbreviate)
    if not matched:
        try:
            candidate = named(config, value)
        except WtError:
            candidate = None
        # Preserve the more useful path-safety refusal for a named symlink.
        if candidate is not None and candidate.path.is_symlink():
            return candidate
        # A valid exact name that is simply absent keeps the established
        # "no such workspace" error (including its resolved path).
        if candidate is not None and not candidate.path.exists():
            candidate.require()
        raise WtError(f"no workspace matches: {value}")
    if len(matched) > 1:
        choices = " ".join(workspace.name for workspace in matched)
        raise WtError(f"ambiguous workspace {value}: {choices}")
    return matched[0]


def reuse_or_named(
    config: Config, value: str, abbreviate: bool = True
) -> Workspace:
    """Reuse a selected workspace, or build the exact name for creation."""
    matched = _matches(config, value, abbreviate=abbreviate)
    if len(matched) > 1:
        choices = " ".join(workspace.name for workspace in matched)
        raise WtError(f"ambiguous workspace {value}: {choices}")
    if matched:
        return matched[0]
    candidate = named(config, value)
    if (
        (candidate.path / GROUP_MARKER).exists()
        and not (candidate.path / MARKER).exists()
    ):
        raise WtError(
            f"{candidate.name} is a stack group; name a workspace leaf below it"
        )
    return candidate


def resolve(
    config: Config, args: list[str], cwd: Path | None = None
) -> tuple[Workspace, list[str]]:
    """Split a verb's arguments into its workspace and the rest.

    The first argument is the workspace when it names an existing workspace,
    or when the current directory is not inside one. Otherwise the current
    workspace is used and every argument belongs to the verb.
    """
    if args and args[0] != "--" and not args[0].startswith("-"):
        matched = _matches(config, args[0])
        candidate = matched[0] if len(matched) == 1 else None
        if len(matched) > 1:
            choices = " ".join(workspace.name for workspace in matched)
            raise WtError(f"ambiguous workspace {args[0]}: {choices}")
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
