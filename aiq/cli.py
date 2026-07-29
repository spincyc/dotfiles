from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

from aiq import __version__
from aiq.journal import (
    JournalError,
    check_journal,
    create_snapshot,
    ingest_message,
    initialize_journal,
    list_inbox,
    resolve_scope,
)


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
        print(payload)
        return
    for key, value in payload.items():
        print(f"{key}\t{value}")


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
        content = sys.stdin.read()
    else:
        hook_input = json.load(sys.stdin)
        if hook_input.get("hook_event_name") != "UserPromptSubmit":
            raise JournalError("hook input is not a UserPromptSubmit event")
        content = hook_input.get("prompt")
        if not isinstance(content, str):
            raise JournalError("hook input has no string prompt")
        source = "user"
        session_id = hook_input.get("session_id")
        turn_id = hook_input.get("turn_id")
        hook_cwd = hook_input.get("cwd")
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
            f"{message['received_at']}\t{message['source']}"
        )
        if arguments.include_content:
            print(message["content"])
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
                    {"error": str(error), "status": "error"},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                file=sys.stderr,
            )
        else:
            print(f"aiq: {error}", file=sys.stderr)
        return 1
