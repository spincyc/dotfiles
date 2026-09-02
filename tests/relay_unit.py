#!/usr/bin/env python3
"""Unit checks for the relay package: the decisions that fail silently.

`relay` exists because the protocol's mechanical steps are easy to
improvise wrongly, and a wrongly improvised step usually looks like it
worked: a rebase that flattens a deliberate merge, a claim retried over a
turn somebody else owns, a result naming a sha the sync already destroyed,
a preflight that fails on an untracked scratch file. None of those raise
anything on their own, so they are checked here against real throwaway
repositories rather than against mocks of git.

Standard library only, offline, and every check that runs git does so
under a temporary home, so the developer's own Git configuration cannot
reach it.
"""

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Importing the package must not leave build artefacts in the checkout;
# the verification battery byte-compiles python/ deliberately and cleans
# up after itself, and this run is not that.
sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "python"))

from relay import PROTOCOL_URL, PROTOCOL_VERSION  # noqa: E402
from relay import (  # noqa: E402
    cli,
    errors,
    gitcmd,
    handoff,
    identity,
    steps,
    turnfile,
)
from relay.errors import Blocked, RelayError  # noqa: E402

GITCONFIG = """\
[user]
  name = relay unit
  email = relay-unit@example.invalid
[init]
  defaultBranch = main
[commit]
  gpgsign = false
"""

BRANCH = "feat/relay"
RUN = "2026-08-31-01"
SHA = "4cf777c1e2a94b0d5f6e8a3b2c1d0e9f8a7b6c5d"


def brief_path(turn: str = "001", word: str = "brief") -> str:
    return f".agent/runs/{RUN}/{turn}-{word}.md"


class TemporaryHome(unittest.TestCase):
    """A case whose git cannot see the developer's configuration.

    `relay` runs git through the ambient environment, so a global
    `commit.gpgsign`, `core.hooksPath`, or `rebase.backend` would decide
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

    def head(self, repo: Path) -> str:
        return self.git(repo, "rev-parse", "HEAD")

    def write(self, repo: Path, name: str, text: str) -> Path:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(
        self, repo: Path, name: str, text: str | None = None
    ) -> str:
        self.write(repo, name, text if text is not None else f"{name}\n")
        self.git(repo, "add", "--", name)
        self.git(repo, "commit", "--quiet", "-m", f"write {name}")
        return self.head(repo)

    def publish(
        self, repo: Path, name: str, text: str | None = None
    ) -> str:
        sha = self.commit(repo, name, text)
        self.git(repo, "push", "--quiet", "origin", BRANCH)
        return sha


class WithOrigin(TemporaryHome):
    """A bare origin, the executor's checkout, and a second writer.

    Two clones are the only way to reproduce what the protocol is actually
    defending against: a ref that moved under the executor between its
    last fetch and its push.
    """

    def setUp(self) -> None:
        super().setUp()
        self.origin = self.root / "origin.git"
        subprocess.run(
            ["git", "init", "--quiet", "--bare", str(self.origin)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        seed = self.root / "seed"
        seed.mkdir()
        subprocess.run(
            ["git", "init", "--quiet", str(seed)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.write(seed, "README.md", "seed\n")
        self.git(seed, "add", "README.md")
        self.git(seed, "commit", "--quiet", "-m", "seed")
        self.git(seed, "branch", "-M", "main")
        self.git(seed, "remote", "add", "origin", str(self.origin))
        self.git(seed, "push", "--quiet", "-u", "origin", "main")
        self.git(seed, "switch", "--quiet", "-c", BRANCH)
        self.git(seed, "push", "--quiet", "-u", "origin", BRANCH)
        self.work = self.clone("work")
        self.other = self.clone("other")

    def clone(self, name: str) -> Path:
        target = self.root / name
        subprocess.run(
            ["git", "clone", "--quiet", str(self.origin), str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.git(target, "switch", "--quiet", BRANCH)
        return target


class IdentityTests(unittest.TestCase):
    """The same repository, spelled every way a remote is spelled."""

    CANONICAL = "github.com/spincyc/dotfiles"

    def test_every_spelling_normalises_to_one_string(self) -> None:
        for url in (
            "https://github.com/spincyc/dotfiles",
            "https://github.com/spincyc/dotfiles.git",
            "https://github.com/spincyc/dotfiles/",
            "ssh://git@github.com/spincyc/dotfiles.git",
            "ssh://git@GitHub.com:22/spincyc/dotfiles",
            "git://github.com/spincyc/dotfiles.git",
            "git@github.com:spincyc/dotfiles.git",
            "git@GITHUB.COM:spincyc/dotfiles",
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    identity.normalize_remote(url), self.CANONICAL
                )

    def test_shorthand_matches_the_last_two_segments(self) -> None:
        for url in (
            "https://github.com/spincyc/dotfiles.git",
            "git@github.com:spincyc/dotfiles.git",
            "ssh://git@example.invalid/spincyc/dotfiles",
        ):
            with self.subTest(url=url):
                self.assertTrue(
                    identity.same_repository(url, "spincyc/dotfiles")
                )

    def test_a_different_repository_does_not_match(self) -> None:
        # The gate exists to catch exactly this: a checkout of something
        # else, in which every later step would still "work".
        self.assertFalse(
            identity.same_repository(
                "git@github.com:spincyc/dotfiles.git", "spincyc/otherfiles"
            )
        )
        self.assertFalse(
            identity.same_repository(
                "git@github.com:spincyc/dotfiles.git",
                "https://github.com/someone/dotfiles",
            )
        )

    def test_an_owner_spelled_with_capitals_still_matches(self) -> None:
        # Only the host is folded. Lowercasing the shorthand as though it
        # were a host would make this compare unequal.
        self.assertTrue(
            identity.same_repository(
                "https://github.com/SpinCyc/dotfiles.git", "SpinCyc/dotfiles"
            )
        )


class CleanTreeTests(WithOrigin):
    """What the tracked-clean gate must and must not stop."""

    def test_an_untracked_file_does_not_fail_the_gate(self) -> None:
        self.write(self.work, "scratch.txt", "not committed\n")
        self.assertEqual(steps.check_clean(self.work), "tracked tree is clean")

    def test_a_tracked_modification_fails_the_gate(self) -> None:
        self.write(self.work, "README.md", "changed\n")
        with self.assertRaises(Blocked) as raised:
            steps.check_clean(self.work)
        self.assertEqual(raised.exception.token, "preflight-failed")
        self.assertIn("README.md", raised.exception.message)


class PreflightTests(WithOrigin):
    def test_a_clean_checkout_passes_every_step(self) -> None:
        brief = self.publish(self.other, brief_path(), "objective\n")
        self.git(self.work, "fetch", "--quiet", "origin")
        self.git(
            self.work, "merge", "--quiet", "--ff-only", f"origin/{BRANCH}"
        )
        self.write(self.work, "scratch.txt", "untracked\n")
        done = steps.preflight(self.work, str(self.origin), BRANCH, brief)
        self.assertEqual(len(done), 7)
        self.assertIn("tracked tree is clean", done)

    def test_a_pure_fast_forward_names_relay_sync(self) -> None:
        brief = self.publish(self.other, brief_path(), "objective\n")
        with self.assertRaises(Blocked) as raised:
            steps.preflight(self.work, str(self.origin), BRANCH, brief)
        self.assertEqual(raised.exception.token, "preflight-failed")
        self.assertIn("relay sync", raised.exception.message)

    def test_a_brief_off_the_branch_is_a_hard_stop(self) -> None:
        stranded = self.commit(self.work, "local.txt")
        with self.assertRaises(Blocked) as raised:
            steps.preflight(self.work, str(self.origin), BRANCH, stranded)
        self.assertEqual(raised.exception.token, "preflight-failed")
        self.assertIn("not an ancestor", raised.exception.message)

    def test_another_repository_is_refused(self) -> None:
        with self.assertRaises(Blocked) as raised:
            steps.preflight(self.work, "someone/elsewhere", BRANCH, "HEAD")
        self.assertIn("not", raised.exception.message)


class SyncTests(WithOrigin):
    """Every branch of the final sync, including the one that rewrites."""

    def merges(self, repo: Path) -> int:
        return len(
            [
                line
                for line in self.git(
                    repo, "rev-list", "--merges", "HEAD"
                ).splitlines()
                if line
            ]
        )

    def test_already_synchronized_does_not_rebase(self) -> None:
        mine = self.commit(self.work, "mine.txt")
        result = steps.sync(self.work, BRANCH)
        self.assertEqual(result.action, "synchronized")
        self.assertEqual(result.message, "synchronized: no rebase needed")
        self.assertFalse(result.moved)
        self.assertEqual(self.head(self.work), mine)

    def test_a_pure_fast_forward_merges_forward(self) -> None:
        theirs = self.publish(self.other, "theirs.txt")
        result = steps.sync(self.work, BRANCH)
        self.assertEqual(result.action, "fast-forward")
        self.assertTrue(result.moved)
        self.assertEqual(self.head(self.work), theirs)
        self.assertEqual(self.merges(self.work), 0)

    def test_a_linear_divergence_rebases(self) -> None:
        self.publish(self.other, "theirs.txt")
        self.commit(self.work, "mine.txt")
        result = steps.sync(self.work, BRANCH)
        self.assertEqual(result.action, "rebase")
        self.assertTrue(result.moved)
        self.assertTrue((self.work / "theirs.txt").is_file())
        self.assertTrue((self.work / "mine.txt").is_file())
        self.assertEqual(self.merges(self.work), 0)

    def test_a_divergence_carrying_a_merge_keeps_it(self) -> None:
        # A plain rebase would replay this range flat and throw the merge
        # away, which is the defect --rebase-merges is here to avoid.
        self.commit(self.work, "mine.txt")
        self.git(self.work, "switch", "--quiet", "-c", "side")
        self.commit(self.work, "side.txt")
        self.git(self.work, "switch", "--quiet", BRANCH)
        self.git(
            self.work, "merge", "--quiet", "--no-ff", "-m", "merge side",
            "side",
        )
        self.assertEqual(self.merges(self.work), 1)
        self.publish(self.other, "theirs.txt")
        result = steps.sync(self.work, BRANCH)
        self.assertEqual(result.action, "rebase --rebase-merges")
        self.assertEqual(self.merges(self.work), 1)
        self.assertTrue((self.work / "theirs.txt").is_file())
        self.assertTrue((self.work / "side.txt").is_file())

    def test_a_conflict_aborts_and_restores_the_head(self) -> None:
        self.publish(self.other, "README.md", "theirs\n")
        before = self.commit(self.work, "README.md", "mine\n")
        with self.assertRaises(Blocked) as raised:
            steps.sync(self.work, BRANCH)
        self.assertEqual(raised.exception.token, "sync-conflict")
        self.assertEqual(self.head(self.work), before)
        self.assertFalse((self.work / ".git" / "rebase-merge").exists())
        self.assertFalse((self.work / ".git" / "rebase-apply").exists())
        # And the checkout is usable again, which is the whole point of
        # never leaving a mid-rebase state behind.
        self.assertEqual(
            steps.check_no_operation(self.work),
            "no rebase or merge in progress",
        )

    def test_dry_run_reports_the_path_and_changes_nothing(self) -> None:
        self.publish(self.other, "theirs.txt")
        self.commit(self.work, "mine.txt")
        before = self.head(self.work)
        result = steps.sync(self.work, BRANCH, dry_run=True)
        self.assertEqual(result.action, "rebase")
        self.assertTrue(result.dry_run)
        self.assertEqual(self.head(self.work), before)


class InitTests(WithOrigin):
    def test_a_checkout_on_the_default_branch_switches(self) -> None:
        fresh = self.root / "fresh"
        subprocess.run(
            ["git", "clone", "--quiet", str(self.origin), str(fresh)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        done = steps.initialize(fresh, str(self.origin), BRANCH)
        self.assertEqual(
            self.git(fresh, "rev-parse", "--abbrev-ref", "HEAD"), BRANCH
        )
        self.assertIn(f"switched to a new {BRANCH}", " ".join(done))

    def test_a_branch_with_the_wrong_upstream_is_a_hard_stop(self) -> None:
        fresh = self.root / "fresh"
        subprocess.run(
            ["git", "clone", "--quiet", str(self.origin), str(fresh)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.git(fresh, "branch", BRANCH, "origin/main")
        with self.assertRaises(Blocked) as raised:
            steps.initialize(fresh, str(self.origin), BRANCH)
        self.assertEqual(raised.exception.token, "preflight-failed")
        self.assertEqual(
            self.git(fresh, "rev-parse", "--abbrev-ref", "HEAD"), "main"
        )
        # The branch it refused to use is untouched.
        self.assertEqual(
            self.git(fresh, "rev-parse", BRANCH),
            self.git(fresh, "rev-parse", "origin/main"),
        )

    def test_being_on_the_branch_already_changes_nothing(self) -> None:
        done = steps.initialize(self.work, str(self.origin), BRANCH)
        self.assertIn("no branch change", " ".join(done))


class ClaimTests(WithOrigin):
    def push_claim(self, repo: Path, turn: str) -> str:
        text = turnfile.render(
            [
                ("protocol", PROTOCOL_VERSION),
                ("run", RUN),
                ("turn", turn),
                ("role", "executor"),
                ("agent", "other-agent"),
                ("branch", BRANCH),
                ("base", self.head(repo)),
            ]
        )
        return self.publish(repo, brief_path(turn, "claim"), text)

    def test_a_claim_already_at_origin_is_a_replay(self) -> None:
        self.push_claim(self.other, "002")
        with self.assertRaises(Blocked) as raised:
            steps.claim(self.work, RUN, "002", BRANCH, "claude-code")
        self.assertEqual(raised.exception.token, "claim-replay")
        self.assertIn("already owned", raised.exception.message)

    def test_a_ref_that_merely_moved_is_retried_once(self) -> None:
        self.publish(self.other, "theirs.txt")
        result = steps.claim(self.work, RUN, "002", BRANCH, "claude-code")
        self.assertTrue(result.retried)
        self.assertEqual(result.path, brief_path("002", "claim"))
        self.assertTrue(
            gitcmd.succeeds(
                self.work,
                "cat-file",
                "-e",
                f"origin/{BRANCH}:{result.path}",
            )
        )
        # The retry rebased onto their commit rather than over it.
        self.assertTrue((self.work / "theirs.txt").is_file())

    def test_an_unobstructed_claim_pushes_first_time(self) -> None:
        result = steps.claim(self.work, RUN, "003", BRANCH, "claude-code")
        self.assertFalse(result.retried)
        written = (self.work / result.path).read_text(encoding="utf-8")
        self.assertIn(f"protocol: {PROTOCOL_VERSION}", written)
        self.assertIn(f"base: {result.base}", written)
        self.assertEqual(turnfile.lint_file(self.work / result.path), [])

    def test_an_existing_claim_file_is_never_overwritten(self) -> None:
        path = self.write(
            self.work, brief_path("004", "claim"), "mine already\n"
        )
        with self.assertRaises(RelayError):
            steps.claim(self.work, RUN, "004", BRANCH, "claude-code")
        self.assertEqual(path.read_text(encoding="utf-8"), "mine already\n")


class PrepareTests(WithOrigin):
    def test_an_untouched_brief_reports_the_shas(self) -> None:
        brief = self.publish(self.other, brief_path(), "objective\n")
        result = steps.prepare(self.work, BRANCH, brief, brief_path())
        self.assertEqual(result.sync.action, "fast-forward")
        self.assertEqual(result.head, self.head(self.work))
        self.assertEqual(len(result.head), 40)

    def test_a_rewritten_brief_is_reported(self) -> None:
        brief = self.publish(self.other, brief_path(), "objective\n")
        self.publish(self.other, brief_path(), "objective, rewritten\n")
        with self.assertRaises(Blocked) as raised:
            steps.prepare(self.work, BRANCH, brief, brief_path())
        self.assertEqual(raised.exception.token, "brief-mutated")


class PublishTests(WithOrigin):
    def result_text(self, base: str, work: str) -> str:
        front = turnfile.render(
            [
                ("protocol", PROTOCOL_VERSION),
                ("run", RUN),
                ("turn", "002"),
                ("role", "executor"),
                ("agent", "claude-code"),
                ("branch", BRANCH),
                ("base", base),
                ("answers", brief_path()),
            ]
        )
        return f"{front}\nstatus: complete\nwork: {work}\n"

    def test_current_shas_publish(self) -> None:
        head = self.head(self.work)
        relative = brief_path("002", "result")
        self.write(
            self.work, relative, self.result_text(head, f"{BRANCH}@{head}")
        )
        result = steps.publish(self.work, BRANCH, relative)
        self.assertFalse(result.retried)
        self.assertTrue(
            gitcmd.succeeds(
                self.work, "cat-file", "-e", f"origin/{BRANCH}:{relative}"
            )
        )

    def test_shas_that_no_longer_name_the_head_are_refused(self) -> None:
        head = self.head(self.work)
        self.commit(self.work, "later.txt")
        relative = brief_path("002", "result")
        self.write(
            self.work, relative, self.result_text(head, f"{BRANCH}@{head}")
        )
        with self.assertRaises(Blocked) as raised:
            steps.publish(self.work, BRANCH, relative)
        self.assertEqual(raised.exception.token, "stale-shas")
        self.assertIn(self.head(self.work), raised.exception.message)

    def test_a_push_the_sync_moves_is_refused_rather_than_pushed(
        self,
    ) -> None:
        head = self.head(self.work)
        relative = brief_path("002", "result")
        self.write(
            self.work, relative, self.result_text(head, f"{BRANCH}@{head}")
        )
        # origin moves after the shas were read, which is exactly the race
        # that would otherwise publish a result naming a dead commit.
        self.publish(self.other, "theirs.txt")
        with self.assertRaises(Blocked) as raised:
            steps.publish(self.work, BRANCH, relative)
        self.assertEqual(raised.exception.token, "stale-shas")
        self.assertFalse(
            gitcmd.succeeds(
                self.work, "cat-file", "-e", f"origin/{BRANCH}:{relative}"
            )
        )


class PushClassificationTests(unittest.TestCase):
    def test_a_hook_rejection_is_not_read_as_a_stale_ref(self) -> None:
        # git says "rejected" for both; only the hook line tells them
        # apart, and retrying a hook rejection is pointless.
        self.assertEqual(
            steps.classify_push_failure(
                "! [remote rejected] main -> main (pre-receive hook "
                "declined)"
            ),
            "hooks-rejected",
        )

    def test_a_non_fast_forward_is_a_rejection(self) -> None:
        self.assertEqual(
            steps.classify_push_failure(
                "! [rejected] feat -> feat (fetch first)"
            ),
            "rejected",
        )

    def test_a_missing_credential_is_named_as_one(self) -> None:
        self.assertEqual(
            steps.classify_push_failure(
                "fatal: Authentication failed for 'https://host/o/n'"
            ),
            "no-credentials",
        )


class LintTests(unittest.TestCase):
    """The static rules, checked on files rather than on strings."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def file(self, name: str, fields: list[tuple[str, str]]) -> Path:
        path = self.directory / name
        path.write_text(
            turnfile.render(fields) + "\nbody\n", encoding="utf-8"
        )
        return path

    def brief_fields(self) -> list[tuple[str, str]]:
        return [
            ("protocol", PROTOCOL_VERSION),
            ("run", RUN),
            ("turn", "001"),
            ("role", "planner"),
            ("agent", "claude-planner"),
            ("subagents", "2"),
            ("branch", BRANCH),
            ("base", SHA),
        ]

    def claim_fields(self) -> list[tuple[str, str]]:
        return [
            ("protocol", PROTOCOL_VERSION),
            ("run", RUN),
            ("turn", "002"),
            ("role", "executor"),
            ("agent", "claude-code"),
            ("branch", BRANCH),
            ("base", SHA),
        ]

    def result_fields(self) -> list[tuple[str, str]]:
        return self.claim_fields() + [("answers", brief_path())]

    def locations(self, path: Path) -> list[str]:
        return [
            finding.split(": ", 1)[0].rsplit(":", 1)[1]
            for finding in turnfile.lint_file(path)
        ]

    def test_a_valid_brief_claim_and_result_pass(self) -> None:
        for name, fields in (
            ("001-brief.md", self.brief_fields()),
            ("002-claim.md", self.claim_fields()),
            ("002-result.md", self.result_fields()),
            ("003-close.md", self.claim_fields()),
        ):
            with self.subTest(name=name):
                fixed = [
                    (key, "003" if key == "turn" and name.startswith("003")
                     else value)
                    for key, value in fields
                ]
                if name.startswith("003"):
                    fixed = [
                        (key, "planner" if key == "role" else value)
                        for key, value in fixed
                    ]
                self.assertEqual(
                    turnfile.lint_file(self.file(name, fixed)), []
                )

    def test_fields_out_of_order_are_reported(self) -> None:
        fields = self.claim_fields()
        base = fields.pop()
        fields.insert(-1, base)
        path = self.file("002-claim.md", fields)
        self.assertIn("branch", self.locations(path))

    def test_an_abbreviated_sha_is_reported(self) -> None:
        fields = [
            (name, "4cf777c" if name == "base" else value)
            for name, value in self.claim_fields()
        ]
        path = self.file("002-claim.md", fields)
        self.assertIn("base", self.locations(path))
        self.assertIn("40-character", "".join(turnfile.lint_file(path)))

    def test_an_absolute_path_is_reported(self) -> None:
        fields = [
            (name, "/home/someone/repo/brief.md" if name == "answers"
             else value)
            for name, value in self.result_fields()
        ]
        path = self.file("002-result.md", fields)
        self.assertIn("answers", self.locations(path))

    def test_a_home_relative_path_is_reported(self) -> None:
        fields = [
            (name, "~/repo/brief.md" if name == "answers" else value)
            for name, value in self.result_fields()
        ]
        self.assertIn(
            "answers", self.locations(self.file("002-result.md", fields))
        )

    def test_a_turn_disagreeing_with_the_filename_is_reported(self) -> None:
        fields = [
            (name, "003" if name == "turn" else value)
            for name, value in self.claim_fields()
        ]
        self.assertIn(
            "turn", self.locations(self.file("002-claim.md", fields))
        )

    def test_a_role_disagreeing_with_the_filename_is_reported(self) -> None:
        fields = [
            (name, "planner" if name == "role" else value)
            for name, value in self.claim_fields()
        ]
        self.assertIn(
            "role", self.locations(self.file("002-claim.md", fields))
        )

    def test_role_only_fields_are_enforced(self) -> None:
        without = [
            (name, value)
            for name, value in self.brief_fields()
            if name != "subagents"
        ]
        self.assertIn(
            "subagents", self.locations(self.file("001-brief.md", without))
        )
        self.assertIn(
            "answers", self.locations(self.file("002-claim.md",
                                                self.result_fields()))
        )
        with_subagents = self.claim_fields()
        with_subagents.insert(5, ("subagents", "1"))
        self.assertIn(
            "subagents",
            self.locations(self.file("002-claim.md", with_subagents)),
        )
        self.assertIn(
            "answers",
            self.locations(self.file("002-result.md", self.claim_fields())),
        )

    def test_another_protocol_version_is_reported(self) -> None:
        fields = [
            (name, "relay-v4" if name == "protocol" else value)
            for name, value in self.claim_fields()
        ]
        self.assertIn(
            "protocol", self.locations(self.file("002-claim.md", fields))
        )

    def test_front_matter_must_come_first(self) -> None:
        path = self.directory / "002-claim.md"
        path.write_text(
            "# a heading\n" + turnfile.render(self.claim_fields()),
            encoding="utf-8",
        )
        self.assertEqual(self.locations(path), ["1"])


class CommandLineTests(unittest.TestCase):
    """What the command line itself promises: codes and single lines."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.valid = self.directory / "002-claim.md"
        self.valid.write_text(
            turnfile.render(
                [
                    ("protocol", PROTOCOL_VERSION),
                    ("run", RUN),
                    ("turn", "002"),
                    ("role", "executor"),
                    ("agent", "claude-code"),
                    ("branch", BRANCH),
                    ("base", SHA),
                ]
            ),
            encoding="utf-8",
        )

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_a_mismatched_protocol_refuses_to_run(self) -> None:
        code, out, err = self.run_cli(
            "lint", "--protocol", "relay-v4", str(self.valid)
        )
        self.assertEqual(code, 3)
        # A version mismatch is a stop this tool names, not one the
        # protocol's blocked channel does, so it must not be spelled the
        # way a relayable token is.
        self.assertEqual(out, "stopped: protocol-mismatch\n")
        self.assertIn("relay-v4", err)

    def test_only_protocol_tokens_are_spelled_as_blocked(self) -> None:
        # The user relays one line and nothing else, so a token the
        # planner's table cannot explain must never reach that line.
        for token in errors.RELAYED_TOKENS:
            self.assertTrue(errors.Blocked(token, "x").relayed, token)
        for token in errors.INTERNAL_TOKENS:
            self.assertFalse(errors.Blocked(token, "x").relayed, token)
        self.assertEqual(
            set(errors.RELAYED_TOKENS) & set(errors.INTERNAL_TOKENS), set()
        )

    def test_the_relayed_tokens_are_the_documented_ones(self) -> None:
        # The protocol document is the authority; a token this build can
        # emit that the document does not name would strand a planner.
        document = (
            Path(__file__).resolve().parent.parent / "relay" / "PROTOCOL.md"
        ).read_text(encoding="utf-8")
        # Only the blocked channel's own table; the turn-file table above
        # it is a different set of backticked names entirely.
        section = document.split("## Blocked channel", 1)[1].split("\n## ")[0]
        documented = set(re.findall(r"^\| `([a-z-]+)` \| ", section, re.M))
        self.assertEqual(set(errors.RELAYED_TOKENS), documented)

    def test_the_matching_protocol_runs(self) -> None:
        code, out, _ = self.run_cli(
            "lint", "--protocol", PROTOCOL_VERSION, str(self.valid)
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, f"ok: {self.valid}\n")

    def test_findings_exit_five(self) -> None:
        broken = self.directory / "002-result.md"
        broken.write_text(
            self.valid.read_text(encoding="utf-8"), encoding="utf-8"
        )
        code, out, _ = self.run_cli("lint", str(broken))
        self.assertEqual(code, 5)
        self.assertTrue(out.startswith(f"{broken}:"))

    def test_a_missing_argument_is_a_usage_error(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stderr(io.StringIO()):
                cli.main(["sync"])
        self.assertEqual(raised.exception.code, 2)

    def test_version_prints_the_version_and_nothing_else(self) -> None:
        out = io.StringIO()
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(out):
                cli.main(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(out.getvalue(), f"{PROTOCOL_VERSION}\n")


class HandoffTests(WithOrigin):
    """The launch handoff: its pointer, its brief, and its prompt."""

    def publish_brief(self, text: str) -> str:
        """Commit a brief on the branch and return the commit's sha."""
        path = self.work / brief_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.git(self.work, "add", brief_path())
        self.git(self.work, "commit", "--quiet", "-m", "brief 001")
        return self.git(self.work, "rev-parse", "HEAD")

    def valid_brief(self, **overrides: str) -> str:
        fields = {
            "protocol": PROTOCOL_VERSION,
            "run": RUN,
            "turn": "001",
            "role": "planner",
            "agent": "claude-web",
            "subagents": "0",
            "branch": BRANCH,
            "base": "0" * 40,
        }
        fields.update(overrides)
        rendered = "".join(
            f"{name}: {value}\n" for name, value in fields.items()
        )
        return f"---\n{rendered}---\n\nObjective: a checkable outcome.\n"

    def test_a_pointer_is_a_repository_and_a_full_sha(self) -> None:
        pointer = handoff.parse_pointer(f"spincyc/dotfiles@{'a' * 40}")
        self.assertEqual(pointer.repository, "spincyc/dotfiles")
        self.assertEqual(pointer.sha, "a" * 40)

    def test_a_pointer_carrying_a_shell_metacharacter_is_refused(self) -> None:
        # The charset is the whole safety argument for the form: a token
        # that could reach a shell as anything but a word is not one this
        # protocol emitted.
        for spelling in (
            f"spincyc/dot;rm@{'a' * 40}",
            f"spincyc/$(id)@{'a' * 40}",
            f"spincyc/dotfiles@{'a' * 39}",
            "spincyc/dotfiles",
            f"dotfiles@{'a' * 40}",
        ):
            with self.assertRaises(RelayError):
                handoff.parse_pointer(spelling)

    def test_the_brief_is_read_from_the_commit_that_published_it(self) -> None:
        sha = self.publish_brief(self.valid_brief())
        brief = handoff.read_brief(self.work, sha)
        self.assertEqual(brief.run, RUN)
        self.assertEqual(brief.turn, "001")
        # The claim is the next turn number, still three digits wide.
        self.assertEqual(brief.claim, "002")
        self.assertEqual(brief.branch, BRANCH)
        self.assertEqual(brief.path, brief_path())

    def test_a_commit_publishing_no_brief_is_refused(self) -> None:
        self.write(self.work, "OTHER.md", "not a brief\n")
        self.git(self.work, "add", "OTHER.md")
        self.git(self.work, "commit", "--quiet", "-m", "other")
        sha = self.git(self.work, "rev-parse", "HEAD")
        with self.assertRaises(RelayError):
            handoff.read_brief(self.work, sha)

    def test_a_brief_on_another_version_stops_the_launch(self) -> None:
        sha = self.publish_brief(self.valid_brief(protocol="relay-v0"))
        with self.assertRaises(RelayError) as raised:
            handoff.read_brief(self.work, sha)
        self.assertIn("relay-v0", str(raised.exception))

    def test_front_matter_and_path_must_agree_about_the_run(self) -> None:
        sha = self.publish_brief(self.valid_brief(run="2026-01-01-09"))
        with self.assertRaises(RelayError):
            handoff.read_brief(self.work, sha)

    def test_the_prompt_points_at_the_brief_and_repeats_none(self) -> None:
        sha = self.publish_brief(self.valid_brief())
        brief = handoff.read_brief(self.work, sha)
        pointer = handoff.parse_pointer(f"spincyc/dotfiles@{sha}")
        text = handoff.prompt(brief, pointer, "spincyc/dotfiles")
        self.assertIn(PROTOCOL_URL, text)
        self.assertIn(f"git show {sha}:{brief_path()}", text)
        self.assertIn("claim turn 002", text)
        # The brief is the authority; a launcher that summarised it would
        # be a second, unpinned brief.
        self.assertNotIn("checkable outcome", text)


class PublishedUrlTests(unittest.TestCase):
    """The URL the package hands out is the one the document publishes."""

    def test_the_url_names_this_version_and_the_document_agrees(self) -> None:
        self.assertIn(PROTOCOL_VERSION, PROTOCOL_URL)
        document = (REPO_ROOT / "relay" / "PROTOCOL.md").read_text()
        self.assertIn(PROTOCOL_URL, document)


if __name__ == "__main__":
    unittest.main()
