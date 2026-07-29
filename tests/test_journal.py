from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from aiq.journal import (
    JournalError,
    check_journal,
    create_snapshot,
    ingest_message,
    initialize_journal,
    list_inbox,
    resolve_scope,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


def run_git(cwd: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class JournalTest(unittest.TestCase):
    def agent_scope(self, temporary_root: Path):
        state_home = temporary_root / "state"
        agent_root = temporary_root / "agent-root"
        agent_root.mkdir()
        environment = {"XDG_STATE_HOME": str(state_home)}
        with patch.dict(os.environ, environment):
            return resolve_scope(
                "agent-root",
                cwd=temporary_root,
                agent_root=agent_root,
            )

    def test_repo_scope_is_shared_by_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = root / "repository"
            worktree = root / "worktree"
            repository.mkdir()
            run_git(repository, "init", "-b", "main")
            run_git(repository, "config", "user.name", "AIQ Test")
            run_git(repository, "config", "user.email", "aiq@example.invalid")
            (repository / "tracked").write_text("initial\n")
            run_git(repository, "add", "tracked")
            run_git(repository, "commit", "-m", "Initial")
            run_git(repository, "worktree", "add", "-b", "task", str(worktree), "main")

            primary_scope = resolve_scope("repo", cwd=repository)
            worktree_scope = resolve_scope("repo", cwd=worktree)

            self.assertEqual(primary_scope.journal_path, worktree_scope.journal_path)
            self.assertEqual(
                primary_scope.journal_path,
                repository / ".git" / "aiq" / "journal.sqlite3",
            )

    def test_agent_root_scope_uses_xdg_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scope = self.agent_scope(root)

            self.assertEqual(scope.kind, "agent-root")
            self.assertTrue(
                scope.journal_path.is_relative_to(root / "state" / "aiq" / "roots")
            )

    def test_ingest_is_exact_append_only_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scope = self.agent_scope(root)
            content = "first line\nsecond line\n"

            first = ingest_message(
                scope,
                content,
                session_id="session",
                turn_id="turn",
                cwd=str(root),
            )
            second = ingest_message(
                scope,
                content,
                session_id="session",
                turn_id="turn",
                cwd=str(root),
            )

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.message_id, second.message_id)

            connection = sqlite3.connect(scope.journal_path)
            try:
                stored = connection.execute(
                    "SELECT content FROM messages WHERE message_id = ?",
                    (first.message_id,),
                ).fetchone()[0]
                self.assertEqual(stored, content)
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "UPDATE messages SET content = 'changed' WHERE message_id = ?",
                        (first.message_id,),
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "DELETE FROM events WHERE event_id = ?",
                        (first.event_id,),
                    )
            finally:
                connection.close()

            with self.assertRaises(JournalError):
                ingest_message(
                    scope,
                    "different",
                    session_id="session",
                    turn_id="turn",
                    cwd=str(root),
                )

    def test_inbox_hides_content_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scope = self.agent_scope(root)
            ingest_message(scope, "secret content", cwd=str(root))

            hidden = list_inbox(scope)
            visible = list_inbox(scope, include_content=True)

            self.assertEqual(hidden[0]["state"], "received")
            self.assertNotIn("content", hidden[0])
            self.assertEqual(visible[0]["content"], "secret content")

    def test_journal_permissions_and_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scope = self.agent_scope(root)
            initialize_journal(scope)

            result = check_journal(scope)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(
                stat.S_IMODE(scope.journal_path.stat().st_mode),
                0o600,
            )
            self.assertEqual(
                stat.S_IMODE(scope.journal_path.parent.stat().st_mode),
                0o700,
            )

    def test_snapshot_retention_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scope = self.agent_scope(root)
            ingest_message(scope, "snapshot this", cwd=str(root))

            create_snapshot(scope, keep=2)
            create_snapshot(scope, keep=2)
            result = create_snapshot(scope, keep=2)

            snapshots = list(
                (scope.journal_path.parent / "backups").glob("journal-*.sqlite3")
            )
            self.assertEqual(len(snapshots), 2)
            self.assertEqual(result["retained"], 2)
            self.assertEqual(len(result["removed"]), 1)

    def test_hook_json_ingestion_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = root / "repository"
            repository.mkdir()
            run_git(repository, "init", "-b", "main")
            hook_input = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session",
                "turn_id": "turn",
                "cwd": str(repository),
                "prompt": "capture this exactly\n",
            }
            command = [
                sys.executable,
                str(REPO_ROOT / "bin" / "aiq"),
                "ingest",
                "--hook-json",
                "--scope",
                "repo",
                "--json",
            ]

            first = subprocess.run(
                command,
                input=json.dumps(hook_input),
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            second = subprocess.run(
                command,
                input=json.dumps(hook_input),
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )

            self.assertTrue(json.loads(first.stdout)["created"])
            self.assertFalse(json.loads(second.stdout)["created"])
            scope = resolve_scope("repo", cwd=repository)
            self.assertEqual(check_journal(scope)["messages"], 1)


if __name__ == "__main__":
    unittest.main()
