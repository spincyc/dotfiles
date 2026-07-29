from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from aiq.journal import check_journal, resolve_scope


REPO_ROOT = Path(__file__).resolve().parent.parent


def run_git(cwd: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class CodexHookTest(unittest.TestCase):
    def test_hook_configuration_is_valid(self) -> None:
        configuration = json.loads((REPO_ROOT / "codex" / "hooks.json").read_text())
        prompt_hooks = configuration["hooks"]["UserPromptSubmit"]

        self.assertEqual(len(prompt_hooks), 1)
        self.assertNotIn("matcher", prompt_hooks[0])
        self.assertEqual(prompt_hooks[0]["hooks"][0]["type"], "command")

    def test_prompt_hook_captures_message_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            home = root / "home"
            repository = root / "repository"
            bin_directory = home / ".local" / "bin"
            bin_directory.mkdir(parents=True)
            repository.mkdir()
            run_git(repository, "init", "-b", "main")
            (bin_directory / "aiq").symlink_to(REPO_ROOT / "bin" / "aiq")
            hook_input = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session",
                "turn_id": "turn",
                "cwd": str(repository),
                "prompt": "persist this prompt",
            }
            environment = os.environ.copy()
            environment["HOME"] = str(home)

            result = subprocess.run(
                [str(REPO_ROOT / "hooks" / "codex-user-prompt-submit")],
                cwd=repository,
                env=environment,
                input=json.dumps(hook_input),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            scope = resolve_scope("repo", cwd=repository)
            self.assertEqual(check_journal(scope)["messages"], 1)

    def test_prompt_hook_blocks_when_aiq_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = os.environ.copy()
            environment["HOME"] = temporary_directory

            result = subprocess.run(
                [str(REPO_ROOT / "hooks" / "codex-user-prompt-submit")],
                env=environment,
                input="{}",
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("is missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
