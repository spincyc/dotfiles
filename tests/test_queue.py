from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from aiq.journal import (
    JournalError,
    check_journal,
    ingest_message,
    list_inbox,
    resolve_scope,
)
from aiq.queue import (
    TRANSITIONS,
    apply_effects,
    claim_message,
    claim_next_tasks,
    claim_task,
    dispose_message,
    list_tasks,
    next_tasks,
    parse_effect_document,
    release_claim,
    show_task,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_TRANSITIONS = {
    "queued": {"ready", "blocked", "canceled", "superseded"},
    "ready": {"queued", "active", "blocked", "canceled", "superseded"},
    "active": {"queued", "ready", "blocked", "done", "canceled", "superseded"},
    "blocked": {"queued", "ready", "canceled", "superseded"},
    "done": set(),
    "canceled": set(),
    "superseded": set(),
}


class QueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.environment = patch.dict(
            os.environ,
            {"XDG_STATE_HOME": str(self.root / "state")},
        )
        self.environment.start()
        agent_root = self.root / "agent"
        agent_root.mkdir()
        self.scope = resolve_scope(
            "agent-root",
            cwd=self.root,
            agent_root=agent_root,
        )
        self.message_claims: dict[str, str] = {}

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary_directory.cleanup()

    def ingest(self, content: str):
        return ingest_message(self.scope, content, cwd=str(self.root))

    def apply(self, message_id: str, document: dict):
        claim_id = self.message_claims.get(message_id)
        if claim_id is None:
            claim = claim_message(
                self.scope,
                owner_id="queue-test",
                message_id=message_id,
            )
            assert claim is not None
            claim_id = claim["claim_id"]
            self.message_claims[message_id] = claim_id
        return apply_effects(
            self.scope,
            message_id,
            document,
            claim_id=claim_id,
        )

    def test_create_dependency_and_queue_readiness(self) -> None:
        message = self.ingest("Create implementation and documentation tasks")
        result = self.apply(
            message.message_id,
            {
                "v": 1,
                "expect": {},
                "effects": [
                    ["create", "$implementation", {"title": "Implement queue"}],
                    [
                        "create",
                        "$docs",
                        {
                            "title": "Document queue",
                            "priority": 100,
                            "requires": ["$implementation"],
                        },
                    ],
                ],
            },
        )

        implementation = result["aliases"]["$implementation"]
        documentation = result["aliases"]["$docs"]
        self.assertEqual(
            [task["task_id"] for task in next_tasks(self.scope)],
            [implementation],
        )
        self.assertEqual(show_task(self.scope, documentation)["state"], "queued")
        self.assertEqual(list_inbox(self.scope), [])

        claimed = [claim_task(self.scope, implementation, owner_id="worker")]
        self.assertEqual(claimed[0]["task"]["task_id"], implementation)
        task_claim_id = claimed[0]["claim"]["claim_id"]

        done_message = self.ingest("Implementation verified")
        self.apply(
            done_message.message_id,
            {
                "v": 1,
                "expect": {implementation: 1},
                "effects": [
                    [
                        "transition",
                        implementation,
                        "done",
                        {"claim": task_claim_id},
                    ]
                ],
            },
        )

        self.assertEqual(
            [task["task_id"] for task in next_tasks(self.scope)],
            [documentation],
        )

    def test_priority_orders_only_ready_tasks(self) -> None:
        message = self.ingest("Create prioritized work")
        result = self.apply(
            message.message_id,
            {
                "v": 1,
                "expect": {},
                "effects": [
                    ["create", "$low", {"title": "Low", "priority": -5}],
                    ["create", "$high", {"title": "High", "priority": 20}],
                ],
            },
        )

        ordered = next_tasks(self.scope, limit=2)

        self.assertEqual(
            [task["task_id"] for task in ordered],
            [result["aliases"]["$high"], result["aliases"]["$low"]],
        )

    def test_application_retry_and_conflict(self) -> None:
        message = self.ingest("Create one task")
        document = {
            "v": 1,
            "expect": {},
            "effects": [["create", "$one", {"title": "One"}]],
        }

        first = self.apply(message.message_id, document)
        second = self.apply(message.message_id, document)

        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["aliases"], second["aliases"])
        self.assertEqual(len(list_tasks(self.scope)), 1)

        with self.assertRaisesRegex(
            JournalError,
            "different effects application",
        ):
            self.apply(
                message.message_id,
                {
                    "v": 1,
                    "expect": {},
                    "effects": [["create", "$other", {"title": "Other"}]],
                },
            )
        self.assertEqual(len(list_tasks(self.scope)), 1)

    def test_invalid_late_effect_rolls_back_entire_batch(self) -> None:
        message = self.ingest("This batch must be atomic")
        with self.assertRaisesRegex(JournalError, "task not found"):
            self.apply(
                message.message_id,
                {
                    "v": 1,
                    "expect": {},
                    "effects": [
                        ["create", "$valid", {"title": "Would be valid"}],
                        ["update", "TASK-999", {"title": "Missing"}],
                    ],
                },
            )

        self.assertEqual(list_tasks(self.scope), [])
        self.assertEqual(list_inbox(self.scope)[0]["message_id"], message.message_id)

        result = self.apply(
            message.message_id,
            {
                "v": 1,
                "expect": {},
                "effects": [["create", "$valid", {"title": "Now valid"}]],
            },
        )
        self.assertEqual(result["aliases"]["$valid"], "TASK-1")

    def test_revision_fence_and_dependency_cycle(self) -> None:
        message = self.ingest("Create two tasks")
        result = self.apply(
            message.message_id,
            {
                "v": 1,
                "expect": {},
                "effects": [
                    ["create", "$a", {"title": "A"}],
                    ["create", "$b", {"title": "B"}],
                ],
            },
        )
        task_a = result["aliases"]["$a"]
        task_b = result["aliases"]["$b"]

        stale_message = self.ingest("Use a stale revision")
        with self.assertRaisesRegex(JournalError, "revision changed"):
            self.apply(
                stale_message.message_id,
                {
                    "v": 1,
                    "expect": {task_a: 99},
                    "effects": [["update", task_a, {"priority": 1}]],
                },
            )

        cycle_message = self.ingest("Create a cycle")
        with self.assertRaisesRegex(JournalError, "dependency cycle"):
            self.apply(
                cycle_message.message_id,
                {
                    "v": 1,
                    "expect": {task_a: 1, task_b: 1},
                    "effects": [
                        ["require", task_a, task_b],
                        ["require", task_b, task_a],
                    ],
                },
            )
        self.assertEqual(show_task(self.scope, task_a)["revision"], 1)
        self.assertEqual(show_task(self.scope, task_b)["revision"], 1)

    def test_transition_matrix_rejects_every_undeclared_edge(self) -> None:
        self.assertEqual(TRANSITIONS, EXPECTED_TRANSITIONS)
        for source, destinations in EXPECTED_TRANSITIONS.items():
            for destination in EXPECTED_TRANSITIONS:
                if destination in destinations or destination == source:
                    continue
                with self.subTest(source=source, destination=destination):
                    message = self.ingest(f"Create {source} to {destination}")
                    create_effects = (
                        [
                            ["create", "$prerequisite", {"title": "Prerequisite"}],
                            [
                                "create",
                                "$task",
                                {
                                    "title": "Transition",
                                    "requires": ["$prerequisite"],
                                },
                            ],
                        ]
                        if source == "queued"
                        else [
                            ["create", "$task", {"title": "Transition"}],
                            *(
                                [["create", "$replacement", {"title": "Replacement"}]]
                                if source == "superseded"
                                else []
                            ),
                        ]
                    )
                    result = self.apply(
                        message.message_id,
                        {
                            "v": 1,
                            "expect": {},
                            "effects": create_effects,
                        },
                    )
                    task_id = result["aliases"]["$task"]

                    def move(to_state: str, metadata: dict | None = None) -> None:
                        setup_message = self.ingest(f"Move fixture to {to_state}")
                        current_revision = show_task(self.scope, task_id)["revision"]
                        expectations = {task_id: current_revision}
                        if metadata and metadata.get("by"):
                            replacement_id = metadata["by"]
                            expectations[replacement_id] = show_task(
                                self.scope,
                                replacement_id,
                            )["revision"]
                        setup_effect = ["transition", task_id, to_state]
                        if metadata:
                            setup_effect.append(metadata)
                        self.apply(
                            setup_message.message_id,
                            {
                                "v": 1,
                                "expect": expectations,
                                "effects": [setup_effect],
                            },
                        )

                    if source == "active":
                        claim_task(
                            self.scope,
                            task_id,
                            owner_id="fixture",
                        )
                    elif source == "blocked":
                        move("blocked", {"reason": "fixture"})
                    elif source == "done":
                        task_claim = claim_task(
                            self.scope,
                            task_id,
                            owner_id="fixture",
                        )["claim"]["claim_id"]
                        move("done", {"claim": task_claim})
                    elif source == "canceled":
                        move("canceled", {"reason": "fixture"})
                    elif source == "superseded":
                        move(
                            "superseded",
                            {
                                "reason": "fixture",
                                "by": result["aliases"]["$replacement"],
                            },
                        )
                    transition_message = self.ingest("Reject transition")
                    current = show_task(self.scope, task_id)
                    metadata = (
                        {"reason": "invalid", "by": task_id}
                        if destination == "superseded"
                        else {"reason": "invalid"}
                        if destination in {"blocked", "canceled"}
                        else {}
                    )
                    effect = ["transition", task_id, destination]
                    if metadata:
                        effect.append(metadata)
                    with self.assertRaises(JournalError):
                        self.apply(
                            transition_message.message_id,
                            {
                                "v": 1,
                                "expect": {task_id: current["revision"]},
                                "effects": [effect],
                            },
                        )

    def test_effect_parser_is_strict_and_bounded(self) -> None:
        with self.assertRaisesRegex(JournalError, "duplicate JSON key"):
            parse_effect_document('{"v":1,"v":1,"expect":{},"effects":[]}')
        with self.assertRaisesRegex(JournalError, "unknown keys"):
            parse_effect_document(
                '{"v":1,"expect":{},"effects":[],"reason":"none","extra":1}'
            )
        with self.assertRaisesRegex(JournalError, "exceeds"):
            parse_effect_document(" " * 65537)
        with self.assertRaisesRegex(JournalError, "unknown operation"):
            parse_effect_document(
                '{"v":1,"expect":{},"effects":[[["not-a-string"]]]}'
            )

    def test_failed_dependency_cannot_be_activated(self) -> None:
        message = self.ingest("Create dependent work")
        result = self.apply(
            message.message_id,
            {
                "v": 1,
                "expect": {},
                "effects": [
                    ["create", "$dependency", {"title": "Dependency"}],
                    [
                        "create",
                        "$dependent",
                        {
                            "title": "Dependent",
                            "requires": ["$dependency"],
                        },
                    ],
                ],
            },
        )
        dependency = result["aliases"]["$dependency"]
        dependent = result["aliases"]["$dependent"]
        cancel_message = self.ingest("Cancel dependency")
        self.apply(
            cancel_message.message_id,
            {
                "v": 1,
                "expect": {dependency: 1},
                "effects": [
                    [
                        "transition",
                        dependency,
                        "canceled",
                        {"reason": "cannot proceed"},
                    ]
                ],
            },
        )
        self.assertEqual(
            claim_next_tasks(self.scope, owner_id="worker"),
            [],
        )
        self.assertEqual(show_task(self.scope, dependent)["state"], "blocked")

    def test_supersession_cycle_is_rejected_atomically(self) -> None:
        message = self.ingest("Create alternatives")
        result = self.apply(
            message.message_id,
            {
                "v": 1,
                "expect": {},
                "effects": [
                    ["create", "$a", {"title": "A"}],
                    ["create", "$b", {"title": "B"}],
                ],
            },
        )
        task_a = result["aliases"]["$a"]
        task_b = result["aliases"]["$b"]
        cycle_message = self.ingest("Supersede each other")
        with self.assertRaisesRegex(JournalError, "supersession cycle"):
            self.apply(
                cycle_message.message_id,
                {
                    "v": 1,
                    "expect": {task_a: 1, task_b: 1},
                    "effects": [
                        [
                            "transition",
                            task_a,
                            "superseded",
                            {"reason": "B replaces A", "by": task_b},
                        ],
                        [
                            "transition",
                            task_b,
                            "superseded",
                            {"reason": "A replaces B", "by": task_a},
                        ],
                    ],
                },
            )
        self.assertEqual(show_task(self.scope, task_a)["revision"], 1)
        self.assertEqual(show_task(self.scope, task_b)["revision"], 1)

    def test_append_only_replace_is_rejected_and_audit_passes(self) -> None:
        message = self.ingest("immutable")
        connection = sqlite3.connect(self.scope.journal_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT OR REPLACE INTO messages
                    SELECT
                      message_id,
                      received_at,
                      source,
                      'replaced',
                      content_sha256,
                      idempotency_key,
                      session_id,
                      turn_id,
                      cwd
                    FROM messages
                    WHERE message_id = ?
                    """,
                    (message.message_id,),
                )
        finally:
            connection.close()
        self.assertEqual(check_journal(self.scope)["status"], "ok")

    def test_audit_detects_revision_that_disagrees_with_effect(self) -> None:
        message = self.ingest("Create auditable work")
        self.apply(
            message.message_id,
            {
                "v": 1,
                "expect": {},
                "effects": [["create", "$work", {"title": "Original"}]],
            },
        )
        connection = sqlite3.connect(self.scope.journal_path)
        try:
            connection.executescript(
                """
                DROP TRIGGER task_revisions_no_update;
                UPDATE task_revisions SET title = 'Corrupted';
                CREATE TRIGGER task_revisions_no_update
                BEFORE UPDATE ON task_revisions
                BEGIN
                  SELECT RAISE(ABORT, 'task_revisions are append-only');
                END;
                """
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(JournalError, "creation revision mismatch"):
            check_journal(self.scope)

    def test_message_claim_race_has_one_winner(self) -> None:
        message = self.ingest("Claim exactly once")
        barrier = threading.Barrier(8)

        def compete(index: int):
            barrier.wait()
            try:
                return claim_message(
                    self.scope,
                    owner_id=f"owner-{index}",
                    message_id=message.message_id,
                )
            except JournalError:
                return None

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(compete, range(8)))

        winners = [result for result in results if result is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]["message"]["content"], "Claim exactly once")

    def test_message_disposition_is_parked_and_retryable(self) -> None:
        message = self.ingest("Needs a decision")
        claim = claim_message(
            self.scope,
            owner_id="worker",
            message_id=message.message_id,
        )
        assert claim is not None

        first = dispose_message(
            self.scope,
            message.message_id,
            claim_id=claim["claim_id"],
            disposition="needs_input",
            reason="Choose a backend",
        )
        second = dispose_message(
            self.scope,
            message.message_id,
            claim_id=claim["claim_id"],
            disposition="needs_input",
            reason="Choose a backend",
        )

        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(list_inbox(self.scope)[0]["state"], "needs_input")
        with self.assertRaisesRegex(JournalError, "not claimable"):
            claim_message(
                self.scope,
                owner_id="other",
                message_id=message.message_id,
            )
        self.assertEqual(check_journal(self.scope)["status"], "ok")

    def test_claim_release_is_retryable(self) -> None:
        message = self.ingest("Release this claim")
        claim = claim_message(
            self.scope,
            owner_id="worker",
            message_id=message.message_id,
        )
        assert claim is not None

        first = release_claim(self.scope, claim["claim_id"])
        second = release_claim(self.scope, claim["claim_id"])

        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["sequence"], second["sequence"])
        self.assertEqual(list_inbox(self.scope)[0]["state"], "received")
        self.assertEqual(check_journal(self.scope)["status"], "ok")

    def test_task_claim_race_has_one_winner(self) -> None:
        message = self.ingest("Create contested work")
        result = self.apply(
            message.message_id,
            {
                "v": 1,
                "expect": {},
                "effects": [["create", "$work", {"title": "Contested work"}]],
            },
        )
        task_id = result["aliases"]["$work"]
        barrier = threading.Barrier(8)

        def compete(index: int):
            barrier.wait()
            try:
                return claim_task(
                    self.scope,
                    task_id,
                    owner_id=f"owner-{index}",
                )
            except JournalError:
                return None

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(compete, range(8)))

        self.assertEqual(sum(result is not None for result in results), 1)

    def test_task_claim_expiry_recovery_fences_stale_claim(self) -> None:
        message = self.ingest("Create expiring work")
        result = self.apply(
            message.message_id,
            {
                "v": 1,
                "expect": {},
                "effects": [["create", "$work", {"title": "Expiring work"}]],
            },
        )
        task_id = result["aliases"]["$work"]
        start_us = time.time_ns() // 1000
        first = claim_task(
            self.scope,
            task_id,
            owner_id="first",
            lease_seconds=1,
            now_us=start_us,
        )["claim"]
        second = claim_task(
            self.scope,
            task_id,
            owner_id="second",
            lease_seconds=1,
            now_us=start_us + 1_000_001,
        )["claim"]

        self.assertGreater(second["fence"], first["fence"])
        with self.assertRaisesRegex(JournalError, "not active"):
            release_claim(
                self.scope,
                first["claim_id"],
                now_us=start_us + 1_000_002,
            )
        self.assertEqual(
            show_task(self.scope, task_id)["claim"]["claim_id"],
            second["claim_id"],
        )

    def test_apply_requires_matching_message_claim(self) -> None:
        message = self.ingest("Do not mutate without a claim")
        with self.assertRaisesRegex(JournalError, "claim"):
            apply_effects(
                self.scope,
                message.message_id,
                {"v": 1, "expect": {}, "effects": [], "reason": "no task"},
                claim_id="clm_" + "0" * 32,
            )
        self.assertEqual(list_inbox(self.scope)[0]["message_id"], message.message_id)

    def test_cli_applies_stdin_and_lists_tasks_as_json(self) -> None:
        message = self.ingest("Exercise the CLI")
        base = [
            sys.executable,
            str(REPO_ROOT / "bin" / "aiq"),
        ]
        scope_arguments = [
            "--scope",
            "agent-root",
            "--cwd",
            str(self.root),
            "--agent-root",
            str(self.root / "agent"),
            "--json",
        ]
        environment = os.environ.copy()
        document = {
            "v": 1,
            "expect": {},
            "effects": [["create", "$cli", {"title": "CLI task"}]],
        }
        claim = claim_message(
            self.scope,
            owner_id="cli-test",
            message_id=message.message_id,
        )
        assert claim is not None

        applied = subprocess.run(
            [
                *base,
                "inbox",
                "apply",
                message.message_id,
                "--effects",
                "-",
                "--claim",
                claim["claim_id"],
                *scope_arguments,
            ],
            input=json.dumps(document),
            env=environment,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        listed = subprocess.run(
            [*base, "task", "list", *scope_arguments],
            env=environment,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(json.loads(applied.stdout)["status"], "applied")
        self.assertEqual(json.loads(listed.stdout)["tasks"][0]["title"], "CLI task")

    def test_human_cli_escapes_terminal_control_characters(self) -> None:
        ingest_message(
            self.scope,
            "content\u001b[31m",
            source="source\u001b[2J",
            cwd=str(self.root),
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "aiq"),
                "inbox",
                "list",
                "--include-content",
                "--scope",
                "agent-root",
                "--cwd",
                str(self.root),
                "--agent-root",
                str(self.root / "agent"),
            ],
            env=os.environ.copy(),
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertNotIn("\u001b", completed.stdout)
        self.assertIn("\\u001b", completed.stdout)


if __name__ == "__main__":
    unittest.main()
