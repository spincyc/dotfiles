#!/usr/bin/env python3
"""Unit checks for the wt package: the seams tests/wt.sh cannot reach.

The shell suite drives the command line end to end, which is the right way to
check what a user sees. What it cannot reach from a shell is the inside of a
decision: the environment git is handed, the parse of a clone spec that is
never cloned, the answer a corrupt repository gives, the slot the pool has
not been told about. Those are the places where a wrong answer is silent, so
they are checked here instead.

Standard library only, offline, and every check that runs git does so under a
temporary home, so the developer's own Git configuration cannot reach it.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Importing the package must not leave build artefacts in the checkout; the
# verification battery byte-compiles python/ deliberately and cleans up after
# itself, and this run is not that.
sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "python"))

from wt import (  # noqa: E402
    clone,
    config,
    gitcmd,
    guidance,
    names,
    repos,
    slots,
    workspaces,
)
from wt.config import Config  # noqa: E402
from wt.errors import WtError  # noqa: E402

GITCONFIG = """\
[user]
  name = wt unit
  email = wt-unit@example.invalid
[init]
  defaultBranch = main
[commit]
  gpgsign = false
"""


class TemporaryHome(unittest.TestCase):
    """A case whose git cannot see the developer's configuration.

    `wt` runs git through the ambient environment, so a global
    `core.excludesFile`, `commit.gpgsign`, or `core.hooksPath` would decide
    the outcome of these checks on one machine and not another.
    """

    def setUp(self) -> None:
        if not gitcmd.available():
            self.skipTest("git is not installed")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        home = self.root / "home"
        (home / ".config").mkdir(parents=True)
        gitconfig = home / "gitconfig"
        gitconfig.write_text(GITCONFIG, encoding="utf-8")
        patched = mock.patch.dict(
            os.environ,
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "GIT_CONFIG_GLOBAL": str(gitconfig),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
        patched.start()
        self.addCleanup(patched.stop)

    def git(self, repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()

    def make_repo(self, name: str = "repo") -> Path:
        """A repository with one commit on main and nothing else."""
        repo = self.root / name
        repo.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "--quiet", str(repo)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        (repo / "README.md").write_text("seed\n", encoding="utf-8")
        self.git(repo, "add", "README.md")
        self.git(repo, "commit", "--quiet", "-m", "seed")
        self.git(repo, "branch", "-M", "main")
        return repo

    def publish(self, repo: Path, name: str = "origin.git") -> Path:
        """Give the repository a remote and push main to it."""
        origin = self.root / name
        subprocess.run(
            ["git", "init", "--quiet", "--bare", str(origin)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.git(repo, "remote", "add", "origin", str(origin))
        self.git(repo, "push", "--quiet", "-u", "origin", "main")
        return origin


class ParsedEnvironmentTest(unittest.TestCase):
    """git's locale, pinned wherever wt parses git's own words.

    Under a translated git, a reader matching on git's wording sees nothing
    at all: `git clean` deletes the files and `wt tidy` reports zero paths
    removed. No shell test on a machine without that locale installed can
    reproduce it, so the pinning is checked directly.
    """

    def test_pins_the_c_locale(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"LC_ALL": "fr_FR.UTF-8", "LANG": "fr_FR.UTF-8", "LANGUAGE": "fr"},
        ):
            environment = gitcmd._parsed_env()
        self.assertEqual(environment["LC_ALL"], "C")
        self.assertEqual(environment["LANGUAGE"], "")

    def test_keeps_the_rest_of_the_environment(self) -> None:
        with mock.patch.dict(os.environ, {"WT_UNIT_MARKER": "kept"}):
            environment = gitcmd._parsed_env()
        self.assertEqual(environment["WT_UNIT_MARKER"], "kept")

    def test_read_runs_git_under_the_pinned_environment(self) -> None:
        with mock.patch("wt.gitcmd.subprocess.run") as runner:
            runner.return_value = subprocess.CompletedProcess([], 0, stdout="")
            gitcmd.read(Path("."), "status")
        passed = runner.call_args.kwargs["env"]
        self.assertEqual(passed["LC_ALL"], "C")
        self.assertEqual(passed["LANGUAGE"], "")

    def test_popen_runs_git_under_the_pinned_environment(self) -> None:
        with mock.patch("wt.gitcmd.subprocess.Popen") as opener:
            gitcmd.popen(Path("."), "clean", "-Xdn")
        passed = opener.call_args.kwargs["env"]
        self.assertEqual(passed["LC_ALL"], "C")
        self.assertEqual(passed["LANGUAGE"], "")

    def test_run_outside_a_repository_is_pinned_too(self) -> None:
        with mock.patch("wt.gitcmd.subprocess.run") as runner:
            runner.return_value = subprocess.CompletedProcess([], 0)
            gitcmd.run(["clone", "--", "src", "dst"], quiet=True)
        passed = runner.call_args.kwargs["env"]
        self.assertEqual(passed["LC_ALL"], "C")


class CloneSpecTest(unittest.TestCase):
    """Every form `wt clone` accepts, and the ones it must refuse."""

    def assert_spec(
        self, spec: str, owner: str, repo: str, url: str | None
    ) -> None:
        parsed = clone.parse(spec)
        self.assertEqual((parsed.owner, parsed.repo), (owner, repo), spec)
        self.assertEqual(parsed.url, url, spec)

    def test_bare_owner_repo_has_no_url(self) -> None:
        self.assert_spec("spincyc/telos", "spincyc", "telos", None)
        self.assert_spec("spincyc/telos/", "spincyc", "telos", None)
        self.assert_spec("spincyc/telos.git", "spincyc", "telos", None)

    def test_https_and_ssh_keep_their_url(self) -> None:
        self.assert_spec(
            "https://github.com/spincyc/telos.git",
            "spincyc",
            "telos",
            "https://github.com/spincyc/telos.git",
        )
        self.assert_spec(
            "https://example.invalid/a/b/spincyc/telos",
            "spincyc",
            "telos",
            "https://example.invalid/a/b/spincyc/telos",
        )
        self.assert_spec(
            "git@github.com:spincyc/telos.git",
            "spincyc",
            "telos",
            "git@github.com:spincyc/telos.git",
        )
        self.assert_spec(
            "ssh://git@example.invalid/spincyc/telos.git",
            "spincyc",
            "telos",
            "ssh://git@example.invalid/spincyc/telos.git",
        )

    def test_a_local_path_becomes_the_clone_url(self) -> None:
        # Keeping only the last two components of a path is what quietly
        # cloned a different repository of the same name from the network.
        self.assert_spec(
            "/srv/git/spincyc/telos",
            "spincyc",
            "telos",
            "/srv/git/spincyc/telos",
        )
        self.assert_spec(
            "/srv/git/spincyc/telos.git",
            "spincyc",
            "telos",
            "/srv/git/spincyc/telos.git",
        )
        self.assert_spec(
            "/srv/git/spincyc/telos/",
            "spincyc",
            "telos",
            "/srv/git/spincyc/telos",
        )

    def test_a_home_relative_path_is_expanded_here(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": "/home/nobody"}):
            self.assert_spec(
                "~/git/spincyc/telos",
                "spincyc",
                "telos",
                "/home/nobody/git/spincyc/telos",
            )

    def test_a_relative_path_is_resolved_against_the_caller(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            owner = Path(temporary).resolve() / "spincyc"
            (owner / "telos").mkdir(parents=True)
            (owner / "other").mkdir()
            here = os.getcwd()
            self.addCleanup(os.chdir, here)
            os.chdir(owner)
            self.assert_spec(
                "./telos", "spincyc", "telos", str(owner / "telos")
            )
            os.chdir(owner / "other")
            # Normalised lexically, the way the shell reads `..`, so the
            # owner directory the path names is the one that exists.
            self.assert_spec(
                "../telos", "spincyc", "telos", str(owner / "telos")
            )

    def test_refuses_what_names_no_repository(self) -> None:
        for spec in (
            "telos",
            "",
            "https://example.invalid/",
            "https://example.invalid/telos",
            "/telos",
            "/",
            "spincyc/../evil",
            "-flag/telos",
            "spincyc/-telos",
            "spincyc/.hidden",
        ):
            with self.subTest(spec=spec):
                with self.assertRaises(WtError):
                    clone.parse(spec)

    def test_clone_url_uses_the_forge_only_without_one(self) -> None:
        bare = clone.parse("spincyc/telos")
        self.assertEqual(
            bare.clone_url("https://forge.invalid/"),
            "https://forge.invalid/spincyc/telos.git",
        )
        local = clone.parse("/srv/git/spincyc/telos")
        self.assertEqual(
            local.clone_url("https://forge.invalid"), "/srv/git/spincyc/telos"
        )
        self.assertEqual(bare.name, "spincyc/telos")


class ConfigTest(unittest.TestCase):
    """Settings read from the environment, and where they put the registry."""

    def build(self, **environment: str) -> config.Config:
        return config.Config.from_env({"HOME": "/home/nobody", **environment})

    def test_defaults(self) -> None:
        settings = self.build()
        self.assertEqual(settings.root, Path("/home/nobody/git/worktrees"))
        self.assertIsNone(settings.project)
        self.assertEqual(settings.branch_prefix, config.DEFAULT_BRANCH_PREFIX)
        self.assertEqual(settings.agent, config.DEFAULT_AGENT)
        self.assertEqual(settings.forge, config.DEFAULT_FORGE)
        self.assertEqual(
            settings.agents_dir,
            Path("/home/nobody/git/worktrees/.agents"),
        )

    def test_every_setting_is_overridable(self) -> None:
        settings = self.build(
            WT_ROOT="/tmp/ws",
            WT_PROJECT="telos",
            WT_BRANCH_PREFIX="work",
            WT_AGENT="codex",
            WT_FORGE="https://forge.invalid",
        )
        self.assertEqual(settings.root, Path("/tmp/ws"))
        self.assertEqual(settings.project, "telos")
        self.assertEqual(settings.branch_prefix, "work")
        self.assertEqual(settings.agent, "codex")
        self.assertEqual(settings.forge, "https://forge.invalid")

    def test_the_registry_follows_the_root(self) -> None:
        # The root is the only location in the contract, so two roots keep
        # separate registries and neither reports the other's agents.
        here = self.build(WT_ROOT="/tmp/one")
        there = self.build(WT_ROOT="/tmp/two")
        self.assertEqual(here.agents_dir, Path("/tmp/one/.agents"))
        self.assertEqual(there.agents_dir, Path("/tmp/two/.agents"))
        # Dotted, so the walk that looks for projects steps over it.
        self.assertTrue(config.AGENTS_DIRNAME.startswith("."))

    def test_an_empty_value_is_no_value(self) -> None:
        settings = self.build(WT_PROJECT="", WT_AGENT="")
        self.assertIsNone(settings.project)
        self.assertEqual(settings.agent, config.DEFAULT_AGENT)


class SlotPoolTest(unittest.TestCase):
    """The flock-backed agent slots, and what the survey may not guess."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.agents_dir = Path(temporary.name) / "agents"

    def pool(self) -> slots.SlotPool:
        return slots.SlotPool(self.agents_dir)

    def test_a_directory_that_is_not_there_holds_nobody(self) -> None:
        # No registry yet is no agent yet, which is the one honest reading:
        # nothing has ever taken a lock here.
        pool = self.pool()
        self.assertEqual(pool.ceiling(), 0)
        self.assertEqual(pool.survey(), [])
        self.assertFalse(pool.busy_agents().holds("telos/demo"))

    def test_the_survey_reaches_the_highest_lock_on_disk(self) -> None:
        # A slot is not sized by any limit: whatever lock files exist are
        # what a live agent may be holding, and a survey that stopped short
        # of one would sweep the workspace out from under it.
        pool = self.pool()
        pool.ensure_dir()
        (self.agents_dir / "slot-7.lock").touch()
        self.assertEqual(pool.ceiling(), 7)
        self.assertEqual(len(pool.survey()), 7)

    def test_the_ceiling_ignores_what_is_not_a_slot(self) -> None:
        pool = self.pool()
        pool.ensure_dir()
        for name in ("slot-x.lock", "slot-9.info", "notes.txt", "slot-.lock"):
            (self.agents_dir / name).touch()
        self.assertEqual(pool.ceiling(), 0)

    @unittest.skipIf(os.geteuid() == 0, "root reads an unreadable directory")
    def test_an_unreadable_directory_refuses_to_answer(self) -> None:
        # An unreadable registry is not an empty one. Answering "nobody is
        # running" here is what deletes a workspace under a live agent, so
        # every consumer has to see this raise.
        pool = self.pool()
        pool.ensure_dir()
        self.agents_dir.chmod(0o000)
        self.addCleanup(self.agents_dir.chmod, 0o700)
        with self.assertRaises(WtError):
            pool.ceiling()
        with self.assertRaises(WtError):
            pool.busy_agents()

    def test_a_held_slot_names_its_workspace(self) -> None:
        pool = self.pool()
        slot = pool.acquire("claude", "telos/demo")
        self.addCleanup(pool.release)
        self.assertEqual(slot, 1)
        busy = self.pool().busy_agents()
        self.assertTrue(busy.holds("telos/demo"))
        self.assertFalse(busy.holds("telos/other"))

    def test_nothing_caps_how_many_slots_are_taken(self) -> None:
        # The registry counts agents; it does not ration them.
        held = []
        for expected in range(1, 6):
            pool = self.pool()
            self.addCleanup(pool.release)
            held.append(pool.acquire("claude", f"telos/lane-{expected}"))
        self.assertEqual(held, [1, 2, 3, 4, 5])
        busy = self.pool().busy_agents()
        self.assertTrue(busy.holds("telos/lane-5"))
        self.assertEqual(len(self.pool().running()), 5)

    def test_the_lowest_free_slot_is_reused(self) -> None:
        # Otherwise a machine accumulates one lock file per launch forever,
        # and every survey walks all of them.
        first = self.pool()
        second = self.pool()
        self.addCleanup(second.release)
        self.assertEqual(first.acquire("claude", "telos/one"), 1)
        self.assertEqual(second.acquire("claude", "telos/two"), 2)
        first.release()
        third = self.pool()
        self.addCleanup(third.release)
        self.assertEqual(third.acquire("claude", "telos/three"), 1)

    def test_a_busy_slot_with_no_info_protects_every_workspace(self) -> None:
        pool = self.pool()
        pool.acquire("claude", "telos/demo")
        self.addCleanup(pool.release)
        pool.info_path(1).unlink()
        busy = self.pool().busy_agents()
        self.assertTrue(busy.unnamed)
        # The workspace it holds cannot be identified, and guessing wrong
        # deletes the tree an agent is working in.
        self.assertTrue(busy.holds("anything/at-all"))

    def test_a_released_slot_names_nobody(self) -> None:
        pool = self.pool()
        pool.acquire("claude", "telos/demo")
        pool.release()
        busy = self.pool().busy_agents()
        self.assertFalse(busy.unnamed)
        self.assertFalse(busy.holds("telos/demo"))
        self.assertFalse(pool.info_path(1).exists())
        self.assertEqual(self.pool().running(), [])


class UnsavedWorkTest(TemporaryHome):
    """The gate in front of `shutil.rmtree`, which has to fail closed."""

    def test_a_published_clone_holds_nothing(self) -> None:
        repo = self.make_repo()
        self.publish(repo)
        self.assertFalse(repos.has_unsaved_work(repo))

    def test_a_dirty_tree_is_unsaved(self) -> None:
        repo = self.make_repo()
        self.publish(repo)
        (repo / "README.md").write_text("changed\n", encoding="utf-8")
        self.assertTrue(repos.has_unsaved_work(repo))

    def test_a_stash_alone_is_unsaved(self) -> None:
        repo = self.make_repo()
        self.publish(repo)
        (repo / "README.md").write_text("changed\n", encoding="utf-8")
        self.git(repo, "stash", "push", "--quiet")
        self.assertEqual(self.git(repo, "status", "--porcelain"), "")
        self.assertTrue(repos.has_unsaved_work(repo))

    def test_an_unreadable_repository_is_unsaved(self) -> None:
        # A corrupt index makes `git status` exit non-zero. Reading that as
        # "no changes" hands the clone to rm -rf with the work still in it,
        # and no shell test can tell a fail-closed answer from a lucky one.
        repo = self.make_repo()
        self.publish(repo)
        self.assertFalse(repos.has_unsaved_work(repo))
        (repo / ".git" / "index").write_bytes(b"not an index")
        self.assertIsNone(repos.changes(repo))
        self.assertTrue(repos.is_dirty(repo))
        self.assertTrue(repos.has_unsaved_work(repo))

    def test_a_listing_says_unknown_rather_than_clean(self) -> None:
        repo = self.make_repo("work/spincyc/telos")
        self.publish(repo)
        (repo / ".git" / "index").write_bytes(b"not an index")
        status = repos.status(self.root / "work", "spincyc/telos")
        self.assertFalse(status.answered)
        self.assertEqual(status.state, "unknown")

    def test_a_nested_ignored_repository_is_unsaved(self) -> None:
        # A vendored checkout listed in .gitignore keeps its own commits, and
        # the outer `git status` is silent about it by construction.
        repo = self.make_repo()
        self.publish(repo)
        (repo / ".gitignore").write_text("vendor/\n", encoding="utf-8")
        self.git(repo, "add", ".gitignore")
        self.git(repo, "commit", "--quiet", "-m", "ignore vendor")
        self.git(repo, "push", "--quiet", "origin", "main")
        nested = repo / "vendor"
        nested.mkdir()
        subprocess.run(
            ["git", "init", "--quiet", str(nested)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.assertEqual(repos.ignored_repositories(repo), ["vendor"])
        self.assertTrue(repos.has_unsaved_work(repo))

    def test_discovery_finds_only_owner_repo_clones(self) -> None:
        workspace = self.root / "workspace"
        (workspace / "spincyc").mkdir(parents=True)
        clone_path = self.make_repo("workspace/spincyc/telos")
        # A clone at the top, one level too deep, and a bare one: none is at
        # <owner>/<repo>, so none of them is work any clone reports.
        self.make_repo("workspace/loose")
        self.make_repo("workspace/spincyc/deep/telos")
        self.assertEqual(repos.discover(workspace), ["spincyc/telos"])
        self.assertTrue((clone_path / ".git").is_dir())


class WorkspaceNameTest(TemporaryHome):
    """Names become directories and branch names, so they are refused early."""

    def test_a_project_is_supplied_or_demanded(self) -> None:
        self.assertEqual(
            names.normalize_workspace("demo", "telos"), "telos/demo"
        )
        self.assertEqual(
            names.normalize_workspace("telos/demo", None), "telos/demo"
        )
        self.assertEqual(
            names.normalize_workspace("telos/demo/", None), "telos/demo"
        )
        # A trailing slash is trimmed before the split, so "demo/" is the
        # bare slug it looks like rather than a name with an empty half.
        self.assertEqual(
            names.normalize_workspace("demo/", "telos"), "telos/demo"
        )
        with self.assertRaises(WtError) as raised:
            names.normalize_workspace("demo", None)
        self.assertIn("WT_PROJECT", raised.exception.message)

    def test_a_revision_range_is_refused_at_creation_not_resolution(
        self,
    ) -> None:
        # "a..b" is a fine directory name and a hopeless branch name. The
        # rule therefore belongs to creation: applied to resolution it would
        # strand any workspace made before the rule existed, which `wt ls`
        # would go on listing while every named verb refused it.
        self.assertEqual(
            names.normalize_workspace("telos/a..b", "telos"), "telos/a..b"
        )
        self.assertTrue(names.is_safe_component("a..b"))
        self.assertFalse(names.valid_branch("feature/a..b"))
        # A slug git accepts under a prefix is not rejected for standing
        # alone: `feature/HEAD` is a legal branch, `HEAD` alone is not.
        self.assertTrue(names.valid_branch("feature/HEAD"))
        # Traversal is still refused outright, wherever it appears.
        for value in ("telos/..", "../escape", "telos/."):
            with self.subTest(value=value):
                with self.assertRaises(WtError):
                    names.normalize_workspace(value, "telos")

    def test_creation_refuses_a_branch_git_would_not_take(self) -> None:
        # The full branch is what gets validated, so a prefix git dislikes
        # is caught too — the slug alone never sees it.
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        config = Config(root=root)
        with self.assertRaises(WtError) as raised:
            workspaces.named(config, "proj/a..b").create()
        self.assertIn("feature/a..b", raised.exception.message)
        self.assertFalse((root / "proj" / "a..b").exists())

        odd = Config(root=root, branch_prefix="bad prefix")
        with self.assertRaises(WtError):
            workspaces.named(odd, "proj/fine").create()

    def test_refuses_what_git_or_the_filesystem_would_not_take(self) -> None:
        for value in (
            "telos/demo.lock",
            "telos/.hidden",
            "telos/demo.",
            "telos/-dash",
            "telos/de mo",
            "telos/de~mo",
            "",
        ):
            with self.subTest(value=value):
                with self.assertRaises(WtError):
                    names.normalize_workspace(value, "telos")

    def test_a_slug_stack_keeps_every_component_after_the_project(self) -> None:
        name = names.normalize_workspace(
            "telos/high-level-vision/replay-one", None
        )
        self.assertEqual(name, "telos/high-level-vision/replay-one")
        self.assertEqual(
            names.split_workspace(name),
            ("telos", "high-level-vision/replay-one"),
        )

    def test_workspace_from_path(self) -> None:
        root = self.root / "worktrees"
        deep = root / "telos" / "demo" / "spincyc" / "telos"
        deep.mkdir(parents=True)
        self.assertEqual(
            names.workspace_from_path(deep, root), "telos/demo"
        )
        self.assertEqual(
            names.workspace_from_path(
                deep,
                root,
                ("telos/demo", "telos/demo/spincyc/telos"),
            ),
            "telos/demo/spincyc/telos",
        )
        self.assertIsNone(names.workspace_from_path(root / "telos", root))
        self.assertIsNone(names.workspace_from_path(self.root, root))


class WorkspaceSelectionTest(TemporaryHome):
    """Stack leaves and their human-sized, unambiguous selectors."""

    def setUp(self) -> None:
        super().setUp()
        self.config = Config(root=self.root / "worktrees")

    def make(self, name: str) -> workspaces.Workspace:
        workspace = workspaces.named(self.config, name)
        workspace.create()
        return workspace

    def test_a_marked_leaf_does_not_turn_its_groups_into_workspaces(self) -> None:
        workspace = self.make("telos/high-level-vision/replay-one")
        deep = workspace.path / "owner" / "repo"
        deep.mkdir(parents=True)
        self.assertEqual(
            workspace.branch, "feature/high-level-vision/replay-one"
        )
        self.assertEqual(
            [item.name for item in workspaces.listing(self.config)],
            ["telos/high-level-vision/replay-one"],
        )
        self.assertEqual(
            workspaces.current(self.config, deep),
            workspace,
        )
        self.assertEqual(
            (workspace.path / workspaces.MARKER).read_text(encoding="utf-8"),
            workspaces.MARKER_CONTENT,
        )
        self.assertEqual(
            (workspace.path.parent / workspaces.GROUP_MARKER).read_text(
                encoding="utf-8"
            ),
            workspaces.GROUP_MARKER_CONTENT,
        )

    def test_branch_slug_leaf_and_component_prefixes_select_one_leaf(
        self,
    ) -> None:
        workspace = self.make("telos/high-level-vision/replay-one")
        for selector in (
            "feature/high-level-vision/replay-one",
            "high-level-vision/replay-one",
            "replay-one",
            "tel/high/rep-o",
            "HIGH_LEVEL_VISION/REPLAY_ONE",
        ):
            with self.subTest(selector=selector):
                self.assertEqual(
                    workspaces.select(self.config, selector), workspace
                )

    def test_an_ambiguous_short_selector_names_every_choice(self) -> None:
        self.make("telos/vision/replay-one")
        self.make("other/vision/replay-one")
        with self.assertRaises(WtError) as raised:
            workspaces.select(self.config, "replay-o")
        self.assertIn("ambiguous workspace replay-o", raised.exception.message)
        self.assertIn("other/vision/replay-one", raised.exception.message)
        self.assertIn("telos/vision/replay-one", raised.exception.message)

    def test_general_similarity_does_not_capture_a_new_lane_name(self) -> None:
        config = Config(root=self.root / "lanes", project="work")
        workspaces.named(config, "meridian-lane-2").create()
        selected = workspaces.reuse_or_named(config, "meridian-lane-3")
        self.assertEqual(selected.name, "work/meridian-lane-3")
        self.assertFalse(selected.exists())

    def test_a_group_is_not_a_workspace_and_a_workspace_is_not_a_group(
        self,
    ) -> None:
        self.make("telos/vision/replay-one")
        with self.assertRaises(WtError) as group:
            workspaces.reuse_or_named(self.config, "telos/vision")
        self.assertIn("is a stack group", group.exception.message)

        parent = self.make("other/vision")
        with self.assertRaises(WtError) as nested:
            workspaces.named(self.config, "other/vision/replay-one").create()
        self.assertIn(
            "cannot stack other/vision/replay-one under workspace other/vision",
            nested.exception.message,
        )
        self.assertTrue(parent.exists())


class GuidanceWriteTest(unittest.TestCase):
    """The per-workspace guidance files, and what a rewrite must not touch."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def write(self, force: bool = False) -> bool:
        return guidance.write(
            self.directory, "telos/demo", "feature/demo", force=force
        )

    def test_writes_every_document_once(self) -> None:
        self.assertTrue(self.write())
        for name in guidance.FILENAMES:
            self.assertTrue((self.directory / name).is_file(), name)
        self.assertIn(
            "Commit to `feature/demo`",
            (self.directory / guidance.CANONICAL).read_text(encoding="utf-8"),
        )
        self.assertIn(
            "Keep replay stacks in separate leaves",
            (self.directory / guidance.CANONICAL).read_text(encoding="utf-8"),
        )
        # Nothing is missing, so nothing is written.
        self.assertFalse(self.write())

    def test_restores_a_deleted_pointer_without_rewriting_the_canon(
        self,
    ) -> None:
        # Judging the whole set by AGENTS.md left a deleted CLAUDE.md gone for
        # good: the only way back was --force, which also overwrites the file
        # the user annotated.
        self.write()
        canonical = self.directory / guidance.CANONICAL
        canonical.write_text(
            canonical.read_text(encoding="utf-8") + "local note\n",
            encoding="utf-8",
        )
        (self.directory / "CLAUDE.md").unlink()
        self.assertTrue(self.write())
        self.assertTrue((self.directory / "CLAUDE.md").is_file())
        self.assertIn("local note", canonical.read_text(encoding="utf-8"))

    def test_force_rewrites_everything(self) -> None:
        self.write()
        canonical = self.directory / guidance.CANONICAL
        canonical.write_text("mine\n", encoding="utf-8")
        self.assertTrue(self.write(force=True))
        self.assertNotIn("mine", canonical.read_text(encoding="utf-8"))

    def test_a_symlinked_document_is_not_written_through(self) -> None:
        # Writing through a link would put this workspace's guidance wherever
        # the link points, which need not be in the workspace.
        outside = self.directory.parent / "outside.md"
        outside.write_text("elsewhere\n", encoding="utf-8")
        pointer = self.directory / "GEMINI.md"
        pointer.symlink_to(outside)
        self.write()
        self.assertEqual(outside.read_text(encoding="utf-8"), "elsewhere\n")
        self.assertTrue(pointer.is_symlink())
        self.write(force=True)
        self.assertFalse(pointer.is_symlink())
        self.assertEqual(outside.read_text(encoding="utf-8"), "elsewhere\n")


if __name__ == "__main__":
    unittest.main()
