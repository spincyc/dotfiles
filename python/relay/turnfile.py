"""Turn-file front matter: parse, render, and the lint rules.

A turn file is permanent history in the work repository, and the protocol
fixes its field set, the order those fields appear in, and which role may
carry which of them. Every one of those is decidable without git, so the
whole check lives here and `relay lint` is a static command.

Findings are `(location, message)` pairs, where the location is a field
name when one is to blame and a line number when nothing else is.
"""

import re
from pathlib import Path

from . import PROTOCOL_VERSION

DELIMITER = "---"

# The protocol's order. `subagents` immediately follows `agent` in a
# brief; `answers` and `abandons` close the block.
FIELD_ORDER = (
    "protocol",
    "run",
    "turn",
    "role",
    "agent",
    "subagents",
    "branch",
    "base",
    "answers",
    "abandons",
)

# Required of every turn file whatever its role.
REQUIRED_FIELDS = (
    "protocol",
    "run",
    "turn",
    "role",
    "agent",
    "branch",
    "base",
)

# Which role word each filename carries, and which role it implies.
ROLE_BY_WORD = {
    "brief": "planner",
    "close": "planner",
    "claim": "executor",
    "result": "executor",
}

# Fields whose presence depends on the role word: the field, the one word
# that requires it, and whether it is required there or merely allowed.
ROLE_FIELDS = (
    ("answers", "result", True),
    ("subagents", "brief", True),
    ("abandons", "brief", False),
)

SHA_FIELDS = ("base",)
PATH_FIELDS = ("answers",)

FILENAME = re.compile(r"^(?P<turn>\d+)-(?P<word>[a-z]+)\.md$")
SHA = re.compile(r"^[0-9a-f]{40}$")
TURN = re.compile(r"^\d{3}$")
COUNT = re.compile(r"^\d+$")
FIELD_LINE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9_-]*):(?:[ \t](?P<value>.*))?$"
)

Finding = tuple[str, str]
Field = tuple[str, str]


def parse(text: str) -> tuple[list[Field], str, list[Finding]]:
    """Split a turn file into its fields, its body, and what went wrong.

    The fields come back in the order the file wrote them, because that
    order is itself one of the things the protocol constrains.
    """
    lines = text.splitlines()
    problems: list[Finding] = []
    if not lines or lines[0].strip() != DELIMITER:
        problems.append(
            ("1", f"front matter must open with {DELIMITER} on line 1")
        )
        return [], text, problems
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == DELIMITER:
            closing = index
            break
    if closing is None:
        problems.append(
            ("1", f"front matter is never closed by a {DELIMITER} line")
        )
        return [], text, problems
    fields: list[Field] = []
    for index in range(1, closing):
        raw = lines[index]
        number = str(index + 1)
        if not raw.strip():
            problems.append((number, "blank line inside the front matter"))
            continue
        match = FIELD_LINE.match(raw)
        if match is None:
            problems.append(
                (number, f"not a `name: value` field: {raw.strip()!r}")
            )
            continue
        value = (match.group("value") or "").strip()
        fields.append((match.group("name"), value))
    return fields, "\n".join(lines[closing + 1:]), problems


def mapping(fields: list[Field]) -> dict[str, str]:
    """The fields as a dict; the first spelling of a name wins."""
    found: dict[str, str] = {}
    for name, value in fields:
        found.setdefault(name, value)
    return found


def render(fields: list[Field]) -> str:
    """The front-matter block for fields, delimiters included."""
    lines = [DELIMITER]
    lines.extend(f"{name}: {value}" for name, value in fields)
    lines.append(DELIMITER)
    return "\n".join(lines) + "\n"


def _check_order(fields: list[Field]) -> list[Finding]:
    """Known fields must appear in the protocol's relative order.

    Unknown fields are left alone: the protocol says a turn file opens
    with *at least* these fields, so an extra one is not a finding, and
    ordering something the protocol never ordered would be an invention.
    """
    findings: list[Finding] = []
    highest = -1
    highest_name = ""
    for name, _ in fields:
        if name not in FIELD_ORDER:
            continue
        index = FIELD_ORDER.index(name)
        if index < highest:
            findings.append(
                (
                    name,
                    f"out of order: {name} must appear before "
                    f"{highest_name}",
                )
            )
        else:
            highest, highest_name = index, name
    return findings


def _check_paths(found: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    for name in PATH_FIELDS:
        value = found.get(name)
        if value is not None:
            findings.extend(_path_findings(name, value))
    abandons = found.get("abandons")
    if abandons is not None and not TURN.match(abandons):
        # `abandons` names either the turn number it burns or the path of
        # the turn file it supersedes; only the second is a path.
        findings.extend(_path_findings("abandons", abandons))
    return findings


def _path_findings(name: str, value: str) -> list[Finding]:
    if not value:
        findings = [(name, "is empty")]
    elif value.startswith("/"):
        findings = [(name, f"is an absolute path: {value}")]
    elif value.startswith("~"):
        findings = [(name, f"is a home-relative path: {value}")]
    else:
        findings = []
    return findings


def lint_text(text: str, filename: str) -> list[Finding]:
    """Every finding for one turn file's text, given its filename."""
    fields, _, findings = parse(text)
    findings = list(findings)
    if not fields and findings:
        # The front matter could not be read at all. Every field is then
        # "missing", and printing seven of those would bury the one
        # finding that explains them.
        return findings
    found = mapping(fields)

    seen: set[str] = set()
    for name, _ in fields:
        if name in seen:
            findings.append((name, "appears more than once"))
        seen.add(name)

    findings.extend(_check_order(fields))

    for name in REQUIRED_FIELDS:
        if name not in found:
            findings.append((name, "is required and missing"))
        elif not found[name]:
            findings.append((name, "is empty"))

    protocol = found.get("protocol")
    if protocol is not None and protocol != PROTOCOL_VERSION:
        findings.append(
            (
                "protocol",
                f"is {protocol}; this build implements "
                f"{PROTOCOL_VERSION}",
            )
        )

    for name in SHA_FIELDS:
        value = found.get(name)
        if value is not None and not SHA.match(value):
            findings.append(
                (
                    name,
                    f"is {value!r}, not a full 40-character lowercase "
                    f"hex sha",
                )
            )

    findings.extend(_check_paths(found))

    subagents = found.get("subagents")
    if subagents is not None and not COUNT.match(subagents):
        findings.append(
            ("subagents", f"is {subagents!r}, not a nonnegative integer")
        )

    role = found.get("role")
    if role is not None and role not in ("planner", "executor"):
        findings.append(
            ("role", f"is {role!r}, not planner or executor")
        )

    turn = found.get("turn")
    if turn is not None and not TURN.match(turn):
        findings.append(
            ("turn", f"is {turn!r}, not a three-digit turn number")
        )

    findings.extend(_check_filename(filename, found))
    return findings


def _check_filename(filename: str, found: dict[str, str]) -> list[Finding]:
    """The filename is part of the record, so it must agree with it."""
    findings: list[Finding] = []
    name = Path(filename).name
    match = FILENAME.match(name)
    if match is None:
        findings.append(
            (
                "filename",
                f"{name!r} is not <nnn>-<brief|claim|result|close>.md",
            )
        )
        return findings
    word = match.group("word")
    if word not in ROLE_BY_WORD:
        findings.append(
            (
                "filename",
                f"role word {word!r} is not one of "
                f"{', '.join(sorted(ROLE_BY_WORD))}",
            )
        )
        return findings
    turn = found.get("turn")
    if turn is not None and turn != match.group("turn"):
        findings.append(
            (
                "turn",
                f"is {turn!r} but the filename says "
                f"{match.group('turn')!r}",
            )
        )
    role = found.get("role")
    expected = ROLE_BY_WORD[word]
    if role is not None and role != expected:
        findings.append(
            ("role", f"is {role!r} but a {word} is written by the {expected}")
        )
    for field, owner, required in ROLE_FIELDS:
        present = field in found
        if word == owner:
            if required and not present:
                findings.append((field, f"is required on a {word}"))
        elif present:
            findings.append((field, f"is not permitted on a {word}"))
    return findings


def lint_file(path: str | Path) -> list[str]:
    """Findings for one file, formatted `<file>:<location>: <message>`."""
    location = Path(path)
    try:
        text = location.read_text(encoding="utf-8")
    except OSError as error:
        return [f"{path}:1: cannot be read: {error.strerror or error}"]
    except UnicodeDecodeError:
        return [f"{path}:1: is not UTF-8 text"]
    return [
        f"{path}:{where}: {message}"
        for where, message in lint_text(text, str(location))
    ]
