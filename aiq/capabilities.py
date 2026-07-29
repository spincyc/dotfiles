from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiq.journal import JournalError


CAPABILITIES: dict[str, dict[str, Any]] = {
    "message.ingest": {
        "purpose": "Persist one exact message before affected work.",
        "command": "aiq ingest --message TEXT",
    },
    "inbox.claim": {
        "purpose": "Lease one unapplied message and return its exact content.",
        "command": "aiq inbox claim [MESSAGE_ID] --owner OWNER --json",
    },
    "inbox.list": {
        "purpose": "List message state without loading raw content.",
        "command": "aiq inbox list --json",
    },
    "inbox.apply": {
        "purpose": "Atomically turn one claimed message into durable task effects.",
        "command": (
            "aiq inbox apply MESSAGE_ID --claim CLAIM_ID --effects FILE|- --json"
        ),
        "contract": {
            "v": 1,
            "document": {
                "required": ["v", "expect", "effects"],
                "optional": ["reason"],
                "expect": {"TASK-ID": "current revision"},
                "empty_effects": "requires reason",
            },
            "operations": {
                "create": [
                    "create",
                    "$alias",
                    {
                        "title": "required",
                        "objective": "optional",
                        "priority": "optional integer",
                        "parent": "optional task reference",
                        "requires": ["optional task references"],
                    },
                ],
                "update": [
                    "update",
                    "task reference",
                    {
                        "title": "optional",
                        "objective": "optional or null",
                        "priority": "optional integer",
                        "parent": "optional or null",
                    },
                ],
                "transition": [
                    "transition",
                    "task reference",
                    "state",
                    {
                        "reason": "required for blocked/canceled/superseded",
                        "by": "required replacement for superseded",
                        "claim": "required current task claim for done",
                    },
                ],
                "require": ["require", "dependent task", "prerequisite task"],
                "unrequire": ["unrequire", "dependent task", "prerequisite task"],
            },
            "rules": [
                "Existing referenced tasks must appear in expect.",
                "Local aliases must be created before later effects use them.",
                "Create starts queued; readiness is derived from dependencies.",
                "Active state comes only from a queue claim.",
                "The complete document commits or rolls back as one transaction.",
            ],
        },
    },
    "inbox.needs-input": {
        "purpose": "Park a claimed message until the user provides missing input.",
        "command": (
            "aiq inbox needs-input MESSAGE_ID --claim CLAIM_ID --reason TEXT --json"
        ),
    },
    "inbox.fail": {
        "purpose": "Close a claimed message that cannot be processed.",
        "command": "aiq inbox fail MESSAGE_ID --claim CLAIM_ID --reason TEXT --json",
    },
    "task.list": {
        "purpose": "Read compact current task state without raw message content.",
        "command": "aiq task list --json",
    },
    "task.show": {
        "purpose": "Load one task's complete current state.",
        "command": "aiq task show TASK-ID --json",
    },
    "queue.peek": {
        "purpose": "Preview eligible tasks without reserving them.",
        "command": "aiq queue peek --json",
    },
    "queue.next": {
        "purpose": "Atomically lease the highest-priority eligible task.",
        "command": "aiq queue next --owner OWNER --json",
    },
    "claim.release": {
        "purpose": "Release a message or task lease without completing it.",
        "command": "aiq claim release CLAIM_ID --json",
    },
    "journal.check": {
        "purpose": "Verify storage integrity and semantic event history.",
        "command": "aiq journal check --json",
    },
}


def list_capabilities() -> list[dict[str, str]]:
    return [
        {"id": capability_id, "purpose": capability["purpose"]}
        for capability_id, capability in CAPABILITIES.items()
    ]


def show_capability(capability_id: str) -> dict[str, Any]:
    try:
        capability = CAPABILITIES[capability_id]
    except KeyError as error:
        raise JournalError(f"capability not found: {capability_id}") from error
    return {"id": capability_id, **deepcopy(capability)}
