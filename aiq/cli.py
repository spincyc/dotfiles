from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

from aiq import __version__
from aiq.capabilities import list_capabilities, show_capability
from aiq.journal import (
    JournalError,
    check_journal,
    create_snapshot,
    ingest_message,
    initialize_journal,
    list_inbox,
    resolve_scope,
)
from aiq.queue import (
    EFFECT_DOCUMENT_MAX_BYTES,
    TASK_STATES,
    apply_effects,
    claim_message,
    claim_next_tasks,
    dispose_message,
    list_tasks,
    next_tasks,
    parse_effect_document,
    release_claim,
    show_task,
)

MESSAGE_INPUT_MAX_BYTES = 1048576


def _add_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scope",
        choices=("auto", "repo", "agent-root"),
        default="auto",
    )
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--agent-root", type=Path)
    parser.add_argument("--json", action="store_true")


def _scope(arguments: argparse.Namespace, *, cwd: Path | None = None):
    return resolve_scope(
        arguments.scope,
        cwd=cwd or arguments.cwd,
        agent_root=arguments.agent_root,
    )


def _emit(payload: Any, *, as_json: bool, quiet: bool = False) -> None:
    if quiet:
        return
    if as_json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return
    if isinstance(payload, str):
        print(_single_line(payload))
        return
    for key, value in payload.items():
        if isinstance(value, str):
            value = _single_line(value)
        print(f"{key}\t{value}")


def _single_line(value: str) -> str:
    return "".join(
        character
        if character.isprintable() and character not in {"\t", "\r", "\n"}
        else f"\\u{ord(character):04x}"
        for character in value
    )


def _read_stdin_bounded(maximum_bytes: int, *, label: str) -> str:
    data = sys.stdin.buffer.read(maximum_bytes + 1)
    if len(data) > maximum_bytes:
        raise JournalError(f"{label} exceeds {maximum_bytes} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise JournalError(f"{label} is not valid UTF-8") from error


def _read_file_bounded(path: Path, maximum_bytes: int, *, label: str) -> str:
    with path.open("rb") as input_file:
        data = input_file.read(maximum_bytes + 1)
    if len(data) > maximum_bytes:
        raise JournalError(f"{label} exceeds {maximum_bytes} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise JournalError(f"{label} is not valid UTF-8") from error


def _journal_path(arguments: argparse.Namespace) -> int:
    scope = _scope(arguments)
    _emit(scope.to_dict() if arguments.json else str(scope.journal_path), as_json=arguments.json)
    return 0


def _journal_init(arguments: argparse.Namespace) -> int:
    scope = _scope(arguments)
    path = initialize_journal(scope)
    payload = {"status": "initialized", "scope": scope.to_dict()}
    _emit(payload if arguments.json else str(path), as_json=arguments.json)
    return 0


def _journal_check(arguments: argparse.Namespace) -> int:
    result = check_journal(_scope(arguments))
    _emit(result, as_json=arguments.json)
    return 0


def _journal_snapshot(arguments: argparse.Namespace) -> int:
    result = create_snapshot(_scope(arguments), keep=arguments.keep)
    _emit(result, as_json=arguments.json)
    return 0


def _ingest(arguments: argparse.Namespace) -> int:
    source = arguments.source
    session_id = arguments.session_id
    turn_id = arguments.turn_id
    cwd = arguments.cwd

    if arguments.message is not None:
        content = arguments.message
    elif arguments.stdin:
        content = _read_stdin_bounded(
            MESSAGE_INPUT_MAX_BYTES,
            label="message input",
        )
    else:
        hook_input = json.loads(
            _read_stdin_bounded(
                MESSAGE_INPUT_MAX_BYTES,
                label="hook input",
            )
        )
        if not isinstance(hook_input, dict):
            raise JournalError("hook input must be a JSON object")
        if hook_input.get("hook_event_name") != "UserPromptSubmit":
            raise JournalError("hook input is not a UserPromptSubmit event")
        content = hook_input.get("prompt")
        if not isinstance(content, str):
            raise JournalError("hook input has no string prompt")
        source = "user"
        session_id = hook_input.get("session_id")
        turn_id = hook_input.get("turn_id")
        hook_cwd = hook_input.get("cwd")
        for field_name, field_value in (
            ("session_id", session_id),
            ("turn_id", turn_id),
            ("cwd", hook_cwd),
        ):
            if field_value is not None and not isinstance(field_value, str):
                raise JournalError(f"hook input {field_name} must be a string")
        if hook_cwd:
            cwd = Path(hook_cwd)

    scope = _scope(arguments, cwd=cwd)
    result = ingest_message(
        scope,
        content,
        source=source,
        idempotency_key=arguments.idempotency_key,
        session_id=session_id,
        turn_id=turn_id,
        cwd=str(cwd.resolve()),
    )
    _emit(result.to_dict(), as_json=arguments.json, quiet=arguments.quiet)
    return 0


def _inbox_list(arguments: argparse.Namespace) -> int:
    messages = list_inbox(
        _scope(arguments),
        limit=arguments.limit,
        include_content=arguments.include_content,
    )
    if arguments.json:
        _emit({"messages": messages}, as_json=True)
        return 0
    for message in messages:
        print(
            f"{message['message_id']}\t{message['state']}\t"
            f"{message['received_at']}\t{_single_line(message['source'])}"
        )
        if arguments.include_content:
            print(_single_line(message["content"]))
    return 0


def _inbox_apply(arguments: argparse.Namespace) -> int:
    if str(arguments.effects) == "-":
        raw = _read_stdin_bounded(
            EFFECT_DOCUMENT_MAX_BYTES,
            label="effects document",
        )
    else:
        raw = _read_file_bounded(
            arguments.effects,
            EFFECT_DOCUMENT_MAX_BYTES,
            label="effects document",
        )
    result = apply_effects(
        _scope(arguments),
        arguments.message_id,
        parse_effect_document(raw),
        claim_id=arguments.claim,
    )
    _emit(result, as_json=arguments.json)
    return 0


def _inbox_claim(arguments: argparse.Namespace) -> int:
    claim = claim_message(
        _scope(arguments),
        owner_id=arguments.owner,
        lease_seconds=arguments.lease_seconds,
        message_id=arguments.message_id,
    )
    payload = {"claim": claim}
    _emit(payload, as_json=arguments.json)
    return 0


def _inbox_dispose(arguments: argparse.Namespace) -> int:
    result = dispose_message(
        _scope(arguments),
        arguments.message_id,
        claim_id=arguments.claim,
        disposition=arguments.disposition,
        reason=arguments.reason,
    )
    _emit(result, as_json=arguments.json)
    return 0


def _claim_release(arguments: argparse.Namespace) -> int:
    result = release_claim(_scope(arguments), arguments.claim_id)
    _emit(result, as_json=arguments.json)
    return 0


def _task_list(arguments: argparse.Namespace) -> int:
    tasks = list_tasks(
        _scope(arguments),
        states=set(arguments.state) if arguments.state else None,
        limit=arguments.limit,
    )
    if arguments.json:
        summaries = [
            {
                key: task[key]
                for key in (
                    "task_id",
                    "revision",
                    "state",
                    "priority",
                    "title",
                    "blocked_by",
                    "waiting_on",
                )
            }
            for task in tasks
        ]
        _emit({"tasks": summaries}, as_json=True)
        return 0
    for task in tasks:
        print(
            f"{task['task_id']}\t{task['state']}\t"
            f"r{task['revision']}\t{task['priority']}\t"
            f"{_single_line(task['title'])}"
        )
    return 0


def _task_show(arguments: argparse.Namespace) -> int:
    task = show_task(_scope(arguments), arguments.task_id)
    _emit(task, as_json=arguments.json)
    return 0


def _queue_next(arguments: argparse.Namespace) -> int:
    tasks = claim_next_tasks(
        _scope(arguments),
        owner_id=arguments.owner,
        lease_seconds=arguments.lease_seconds,
        limit=arguments.limit,
    )
    if arguments.json:
        _emit({"tasks": tasks}, as_json=True)
        return 0
    for item in tasks:
        task = item["task"]
        claim = item["claim"]
        print(
            f"{task['task_id']}\t{task['state']}\t"
            f"r{task['revision']}\t{task['priority']}\t"
            f"{claim['claim_id']}\t{_single_line(task['title'])}"
        )
    return 0


def _queue_peek(arguments: argparse.Namespace) -> int:
    tasks = next_tasks(_scope(arguments), limit=arguments.limit)
    if arguments.json:
        _emit({"tasks": tasks}, as_json=True)
        return 0
    for task in tasks:
        print(
            f"{task['task_id']}\t{task['state']}\t"
            f"r{task['revision']}\t{task['priority']}\t"
            f"{_single_line(task['title'])}"
        )
    return 0


def _capability_list(arguments: argparse.Namespace) -> int:
    capabilities = list_capabilities()
    if arguments.json:
        _emit({"capabilities": capabilities}, as_json=True)
        return 0
    for capability in capabilities:
        print(f"{capability['id']}\t{capability['purpose']}")
    return 0


def _capability_show(arguments: argparse.Namespace) -> int:
    capability = show_capability(arguments.capability_id)
    if arguments.json:
        _emit(capability, as_json=True)
    else:
        print(json.dumps(capability, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aiq")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    journal = commands.add_parser("journal")
    journal_commands = journal.add_subparsers(dest="journal_command", required=True)

    journal_path = journal_commands.add_parser("path")
    _add_scope_arguments(journal_path)
    journal_path.set_defaults(handler=_journal_path)

    journal_init = journal_commands.add_parser("init")
    _add_scope_arguments(journal_init)
    journal_init.set_defaults(handler=_journal_init)

    journal_check = journal_commands.add_parser("check")
    _add_scope_arguments(journal_check)
    journal_check.set_defaults(handler=_journal_check)

    journal_snapshot = journal_commands.add_parser("snapshot")
    _add_scope_arguments(journal_snapshot)
    journal_snapshot.add_argument("--keep", type=int, default=5)
    journal_snapshot.set_defaults(handler=_journal_snapshot)

    ingest = commands.add_parser("ingest")
    _add_scope_arguments(ingest)
    input_group = ingest.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--message")
    input_group.add_argument("--stdin", action="store_true")
    input_group.add_argument("--hook-json", action="store_true")
    ingest.add_argument("--source", default="user")
    ingest.add_argument("--idempotency-key")
    ingest.add_argument("--session-id")
    ingest.add_argument("--turn-id")
    ingest.add_argument("--quiet", action="store_true")
    ingest.set_defaults(handler=_ingest)

    inbox = commands.add_parser("inbox")
    inbox_commands = inbox.add_subparsers(dest="inbox_command", required=True)
    inbox_list = inbox_commands.add_parser("list")
    _add_scope_arguments(inbox_list)
    inbox_list.add_argument("--limit", type=int, default=20)
    inbox_list.add_argument("--include-content", action="store_true")
    inbox_list.set_defaults(handler=_inbox_list)

    inbox_apply = inbox_commands.add_parser("apply")
    _add_scope_arguments(inbox_apply)
    inbox_apply.add_argument("message_id")
    inbox_apply.add_argument(
        "--effects",
        type=Path,
        required=True,
        help="effects JSON file, or - for stdin",
    )
    inbox_apply.add_argument("--claim", required=True)
    inbox_apply.set_defaults(handler=_inbox_apply)

    inbox_claim = inbox_commands.add_parser("claim")
    _add_scope_arguments(inbox_claim)
    inbox_claim.add_argument("message_id", nargs="?")
    inbox_claim.add_argument("--owner", required=True)
    inbox_claim.add_argument("--lease-seconds", type=int, default=900)
    inbox_claim.set_defaults(handler=_inbox_claim)

    for command, disposition in (
        ("needs-input", "needs_input"),
        ("fail", "failed"),
    ):
        inbox_dispose = inbox_commands.add_parser(command)
        _add_scope_arguments(inbox_dispose)
        inbox_dispose.add_argument("message_id")
        inbox_dispose.add_argument("--claim", required=True)
        inbox_dispose.add_argument("--reason", required=True)
        inbox_dispose.set_defaults(
            handler=_inbox_dispose,
            disposition=disposition,
        )

    task = commands.add_parser("task")
    task_commands = task.add_subparsers(dest="task_command", required=True)

    task_list = task_commands.add_parser("list")
    _add_scope_arguments(task_list)
    task_list.add_argument("--state", action="append", choices=TASK_STATES)
    task_list.add_argument("--limit", type=int, default=100)
    task_list.set_defaults(handler=_task_list)

    task_show = task_commands.add_parser("show")
    _add_scope_arguments(task_show)
    task_show.add_argument("task_id")
    task_show.set_defaults(handler=_task_show)

    queue = commands.add_parser("queue")
    queue_commands = queue.add_subparsers(dest="queue_command", required=True)
    queue_next = queue_commands.add_parser("next")
    _add_scope_arguments(queue_next)
    queue_next.add_argument("--owner", required=True)
    queue_next.add_argument("--lease-seconds", type=int, default=900)
    queue_next.add_argument("--limit", type=int, default=1)
    queue_next.set_defaults(handler=_queue_next)

    queue_peek = queue_commands.add_parser("peek")
    _add_scope_arguments(queue_peek)
    queue_peek.add_argument("--limit", type=int, default=1)
    queue_peek.set_defaults(handler=_queue_peek)

    claim = commands.add_parser("claim")
    claim_commands = claim.add_subparsers(dest="claim_command", required=True)
    claim_release = claim_commands.add_parser("release")
    _add_scope_arguments(claim_release)
    claim_release.add_argument("claim_id")
    claim_release.set_defaults(handler=_claim_release)

    capability = commands.add_parser("capability")
    capability_commands = capability.add_subparsers(
        dest="capability_command",
        required=True,
    )
    capability_list = capability_commands.add_parser("list")
    capability_list.add_argument("--json", action="store_true")
    capability_list.set_defaults(handler=_capability_list)
    capability_show = capability_commands.add_parser("show")
    capability_show.add_argument("capability_id")
    capability_show.add_argument("--json", action="store_true")
    capability_show.set_defaults(handler=_capability_show)

    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        return arguments.handler(arguments)
    except (
        JournalError,
        json.JSONDecodeError,
        OSError,
        sqlite3.Error,
        ValueError,
    ) as error:
        if getattr(arguments, "json", False):
            print(
                json.dumps(
                    {
                        "code": "aiq_error",
                        "error": str(error),
                        "status": "error",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                file=sys.stderr,
            )
        else:
            print(f"aiq: {_single_line(str(error))}", file=sys.stderr)
        return 1
