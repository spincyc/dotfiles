from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
from typing import Any
import uuid


SCHEMA_VERSION = 1


class JournalError(RuntimeError):
    """Journal operation failed."""


@dataclass(frozen=True)
class JournalScope:
    kind: str
    root: Path
    scope_id: str
    journal_path: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "root": str(self.root),
            "scope_id": self.scope_id,
            "journal_path": str(self.journal_path),
        }


@dataclass(frozen=True)
class IngestResult:
    message_id: str
    event_id: str
    sequence: int
    state: str
    created: bool
    scope: JournalScope

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["scope"] = self.scope.to_dict()
        return result


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS journal_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS messages (
  message_id TEXT PRIMARY KEY,
  received_at TEXT NOT NULL,
  source TEXT NOT NULL,
  content TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  idempotency_key TEXT UNIQUE,
  session_id TEXT,
  turn_id TEXT,
  cwd TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  message_id TEXT REFERENCES messages(message_id),
  task_id TEXT,
  payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE INDEX IF NOT EXISTS events_message_sequence
  ON events(message_id, sequence);

CREATE TRIGGER IF NOT EXISTS messages_no_update
BEFORE UPDATE ON messages
BEGIN
  SELECT RAISE(ABORT, 'messages are append-only');
END;

CREATE TRIGGER IF NOT EXISTS messages_no_delete
BEFORE DELETE ON messages
BEGIN
  SELECT RAISE(ABORT, 'messages are append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
  SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
  SELECT RAISE(ABORT, 'events are append-only');
END;
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _path_id(path: Path) -> str:
    digest = hashlib.sha256(os.fsencode(path)).hexdigest()[:16]
    name = "".join(character if character.isalnum() else "-" for character in path.name)
    return f"{name or 'root'}-{digest}"


def _git_path(cwd: Path, argument: str) -> Path:
    result = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", argument],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        raise JournalError(f"{cwd} is not inside a Git repository")
    return Path(result.stdout.strip()).resolve()


def _state_home() -> Path:
    configured = os.environ.get("XDG_STATE_HOME")
    if configured:
        state_home = Path(configured)
        if not state_home.is_absolute():
            raise JournalError("XDG_STATE_HOME must be an absolute path")
        return state_home
    return Path.home() / ".local" / "state"


def resolve_scope(
    scope_kind: str = "auto",
    *,
    cwd: Path | None = None,
    agent_root: Path | None = None,
) -> JournalScope:
    current_directory = (cwd or Path.cwd()).resolve()
    resolved_agent_root = (
        agent_root or Path(__file__).resolve().parent.parent
    ).resolve()

    if scope_kind not in {"auto", "repo", "agent-root"}:
        raise JournalError(f"unsupported journal scope: {scope_kind}")

    if scope_kind in {"auto", "repo"}:
        try:
            common_directory = _git_path(current_directory, "--git-common-dir")
        except JournalError:
            if scope_kind == "repo":
                raise
        else:
            return JournalScope(
                kind="repo",
                root=common_directory,
                scope_id=_path_id(common_directory),
                journal_path=common_directory / "aiq" / "journal.sqlite3",
            )

    root_id = _path_id(resolved_agent_root)
    return JournalScope(
        kind="agent-root",
        root=resolved_agent_root,
        scope_id=root_id,
        journal_path=_state_home()
        / "aiq"
        / "roots"
        / root_id
        / "journal.sqlite3",
    )


def _configure(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA synchronous = FULL")


def _metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return dict(connection.execute("SELECT key, value FROM journal_metadata"))


def _validate_metadata(
    connection: sqlite3.Connection,
    scope: JournalScope,
) -> None:
    metadata = _metadata(connection)
    expected = {
        "schema_version": str(SCHEMA_VERSION),
        "scope_kind": scope.kind,
        "scope_root": str(scope.root),
        "scope_id": scope.scope_id,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise JournalError(
                f"journal metadata mismatch for {key}: "
                f"expected {value!r}, found {metadata.get(key)!r}"
            )


def initialize_journal(scope: JournalScope) -> Path:
    scope.journal_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    scope.journal_path.parent.chmod(0o700)

    original_umask = os.umask(0o077)
    try:
        connection = sqlite3.connect(scope.journal_path, timeout=10)
        try:
            _configure(connection)
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA_SQL)
            metadata = {
                "schema_version": str(SCHEMA_VERSION),
                "scope_kind": scope.kind,
                "scope_root": str(scope.root),
                "scope_id": scope.scope_id,
            }
            connection.executemany(
                "INSERT OR IGNORE INTO journal_metadata(key, value) VALUES (?, ?)",
                metadata.items(),
            )
            connection.commit()
            _validate_metadata(connection, scope)
        finally:
            connection.close()
    finally:
        os.umask(original_umask)

    scope.journal_path.chmod(0o600)
    return scope.journal_path


def _connect(scope: JournalScope) -> sqlite3.Connection:
    initialize_journal(scope)
    connection = sqlite3.connect(scope.journal_path, timeout=10)
    connection.row_factory = sqlite3.Row
    _configure(connection)
    _validate_metadata(connection, scope)
    return connection


def ingest_message(
    scope: JournalScope,
    content: str,
    *,
    source: str = "user",
    idempotency_key: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    cwd: str | None = None,
) -> IngestResult:
    if content == "":
        raise JournalError("message content must not be empty")
    if not source:
        raise JournalError("message source must not be empty")

    content_hash = hashlib.sha256(content.encode()).hexdigest()
    effective_key = idempotency_key
    if effective_key is None and session_id and turn_id:
        effective_key = f"{source}:{session_id}:{turn_id}"

    connection = _connect(scope)
    try:
        connection.execute("BEGIN IMMEDIATE")
        if effective_key:
            existing = connection.execute(
                """
                SELECT
                  m.message_id,
                  m.content_sha256,
                  e.event_id,
                  e.sequence
                FROM messages AS m
                JOIN events AS e
                  ON e.message_id = m.message_id
                 AND e.event_type = 'message.received'
                WHERE m.idempotency_key = ?
                """,
                (effective_key,),
            ).fetchone()
            if existing:
                if existing["content_sha256"] != content_hash:
                    raise JournalError(
                        "idempotency key already belongs to different content"
                    )
                connection.commit()
                return IngestResult(
                    message_id=existing["message_id"],
                    event_id=existing["event_id"],
                    sequence=existing["sequence"],
                    state="received",
                    created=False,
                    scope=scope,
                )

        received_at = _utc_now()
        message_id = _identifier("msg")
        event_id = _identifier("evt")
        connection.execute(
            """
            INSERT INTO messages(
              message_id,
              received_at,
              source,
              content,
              content_sha256,
              idempotency_key,
              session_id,
              turn_id,
              cwd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                received_at,
                source,
                content,
                content_hash,
                effective_key,
                session_id,
                turn_id,
                cwd,
            ),
        )
        cursor = connection.execute(
            """
            INSERT INTO events(
              event_id,
              occurred_at,
              event_type,
              message_id,
              payload_json
            ) VALUES (?, ?, 'message.received', ?, ?)
            """,
            (event_id, received_at, message_id, "{}"),
        )
        connection.commit()
        return IngestResult(
            message_id=message_id,
            event_id=event_id,
            sequence=cursor.lastrowid,
            state="received",
            created=True,
            scope=scope,
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def list_inbox(
    scope: JournalScope,
    *,
    limit: int = 20,
    include_content: bool = False,
) -> list[dict[str, Any]]:
    if limit < 1:
        raise JournalError("inbox limit must be positive")
    if not scope.journal_path.exists():
        return []
    connection = _connect(scope)
    try:
        content_column = ", m.content" if include_content else ""
        rows = connection.execute(
            f"""
            WITH latest AS (
              SELECT
                event_id,
                sequence,
                event_type,
                message_id,
                ROW_NUMBER() OVER (
                  PARTITION BY message_id
                  ORDER BY sequence DESC
                ) AS rank
              FROM events
              WHERE message_id IS NOT NULL
            )
            SELECT
              m.message_id,
              m.received_at,
              m.source,
              m.content_sha256,
              m.session_id,
              m.turn_id,
              m.cwd,
              latest.event_type,
              latest.sequence
              {content_column}
            FROM messages AS m
            JOIN latest
              ON latest.message_id = m.message_id
             AND latest.rank = 1
            WHERE latest.event_type IN (
              'message.received',
              'message.processing',
              'message.failed'
            )
            ORDER BY latest.sequence
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                **dict(row),
                "state": row["event_type"].removeprefix("message."),
            }
            for row in rows
        ]
    finally:
        connection.close()


def create_snapshot(
    scope: JournalScope,
    *,
    keep: int = 5,
) -> dict[str, Any]:
    if keep < 1:
        raise JournalError("snapshot retention must be positive")
    if not scope.journal_path.exists():
        raise JournalError(f"journal does not exist: {scope.journal_path}")

    check_journal(scope)
    backup_directory = scope.journal_path.parent / "backups"
    backup_directory.mkdir(mode=0o700, exist_ok=True)
    backup_directory.chmod(0o700)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_path = backup_directory / f"journal-{timestamp}-{uuid.uuid4().hex}.sqlite3"
    temporary_path = backup_directory / f".{snapshot_path.name}.tmp"

    original_umask = os.umask(0o077)
    try:
        source = sqlite3.connect(scope.journal_path, timeout=10)
        destination = sqlite3.connect(temporary_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        temporary_path.chmod(0o600)
        temporary_path.replace(snapshot_path)
    finally:
        os.umask(original_umask)
        if temporary_path.exists():
            temporary_path.unlink()

    snapshots = sorted(backup_directory.glob("journal-*.sqlite3"), reverse=True)
    removed: list[str] = []
    for expired_snapshot in snapshots[keep:]:
        expired_snapshot.unlink()
        removed.append(str(expired_snapshot))

    return {
        "status": "created",
        "snapshot_path": str(snapshot_path),
        "removed": removed,
        "retained": min(len(snapshots), keep),
        "scope": scope.to_dict(),
    }


def check_journal(scope: JournalScope) -> dict[str, Any]:
    if not scope.journal_path.exists():
        raise JournalError(f"journal does not exist: {scope.journal_path}")

    connection = sqlite3.connect(scope.journal_path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        _configure(connection)
        _validate_metadata(connection, scope)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise JournalError(f"SQLite integrity check failed: {integrity}")
        message_count = connection.execute(
            "SELECT COUNT(*) FROM messages"
        ).fetchone()[0]
        event_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        connection.close()

    mode = stat.S_IMODE(scope.journal_path.stat().st_mode)
    if mode != 0o600:
        raise JournalError(
            f"journal permissions are {mode:04o}; expected 0600"
        )

    return {
        "status": "ok",
        "schema_version": SCHEMA_VERSION,
        "messages": message_count,
        "events": event_count,
        "snapshots": len(
            list((scope.journal_path.parent / "backups").glob("journal-*.sqlite3"))
        ),
        "scope": scope.to_dict(),
    }
